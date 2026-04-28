"""
数据获取层
- 封装 akshare 接口
- 本地 parquet 缓存,避免重复拉取
- 提供:股票列表、财务报表、行业板块、行情
"""
from __future__ import annotations
import time
import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from . import config

logger = logging.getLogger(__name__)


def _cache_path(name: str) -> Path:
    return config.CACHE_DIR / f"{name}.parquet"


def _load_cache(name: str, ttl_days: int = 1) -> Optional[pd.DataFrame]:
    """读取缓存;ttl_days 内的缓存视为有效"""
    p = _cache_path(name)
    if not p.exists():
        return None
    age_days = (time.time() - p.stat().st_mtime) / 86400
    if age_days > ttl_days:
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:
        logger.warning(f"读取缓存 {name} 失败:{e}")
        return None


def _save_cache(name: str, df: pd.DataFrame) -> None:
    try:
        df.to_parquet(_cache_path(name), index=False)
    except Exception as e:
        logger.warning(f"写入缓存 {name} 失败:{e}")


def _retry_with_backoff(fn, *args, max_retries: int = 3, base_delay: float = 0.5,
                        **kwargs):
    """
    带指数退避的重试包装器
    第 1 次失败:等 base_delay 秒
    第 2 次失败:等 base_delay*2 秒
    第 3 次失败:等 base_delay*4 秒
    最后一次失败抛出异常
    """
    last_exc = None
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.debug(f"重试 {attempt+1}/{max_retries},等待 {delay:.1f}s: {e}")
                time.sleep(delay)
    raise last_exc


# =====================================================================
# 1. 股票基础列表
# =====================================================================
def get_stock_list(use_cache: bool = True) -> pd.DataFrame:
    """
    返回沪深 A 股基础信息表

    columns: code, name, market(沪/深), list_date(上市日期), is_st
    """
    if use_cache:
        cached = _load_cache("stock_list", ttl_days=7)
        if cached is not None:
            return cached

    import akshare as ak

    # 实时行情接口包含全市场最新名单(含名称、是否ST标识),带重试保护
    try:
        df_spot = _retry_with_backoff(
            ak.stock_zh_a_spot_em, max_retries=3, base_delay=1.0
        )
    except Exception as e:
        logger.error(f"获取股票列表失败(已重试 3 次):{e}")
        # 降级:用旧缓存(即使过期)
        cache_path = _cache_path("stock_list")
        if cache_path.exists():
            fallback = pd.read_parquet(cache_path)
            logger.warning(f"使用过期的股票列表缓存({len(fallback)} 只)")
            return fallback
        raise
    # 字段示例:代码、名称、最新价、涨跌幅 ...
    df = df_spot[["代码", "名称"]].copy()
    df.columns = ["code", "name"]

    # 市场归属
    def _market(code: str) -> str:
        if code.startswith(("60", "68", "90")):
            return "上海"
        if code.startswith(("00", "30", "20")):
            return "深圳"
        if code.startswith(("8", "4")):
            return "北京"
        return "其他"

    df["market"] = df["code"].apply(_market)
    df["is_st"] = df["name"].str.contains("ST", case=False, na=False)

    # 上市日期(单独接口,数据量大,这里仅在需要时拉取)
    try:
        df_info = ak.stock_info_a_code_name()  # 包含 code, name
        # 上市日期需要遍历,代价高,采用懒加载策略
    except Exception:
        pass

    if config.EXCLUDE_BJ:
        df = df[df["market"] != "北京"].reset_index(drop=True)

    _save_cache("stock_list", df)
    logger.info(f"股票列表加载完成,共 {len(df)} 只")
    return df


# =====================================================================
# 2. 财务报表
# =====================================================================
def get_financial_report(code: str, use_cache: bool = True) -> pd.DataFrame:
    """
    获取单只股票的财务报表(年报+季报),返回长表

    columns: code, report_date, report_type(年报/中报/三季报/一季报),
             eps, revenue, gross_margin, net_profit
    """
    cache_name = f"fin_{code}"
    if use_cache:
        cached = _load_cache(cache_name, ttl_days=7)
        if cached is not None:
            return cached

    import akshare as ak

    try:
        # 财务摘要(包含 EPS、营收、毛利率、净利润等关键指标)
        df = ak.stock_financial_abstract(symbol=code)
    except Exception as e:
        logger.warning(f"[{code}] 获取财报失败:{e}")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    # akshare 返回的表是宽表:行=指标,列=各报告期
    # 我们要把它转为长表
    df = _normalize_financial_abstract(df, code)
    _save_cache(cache_name, df)
    time.sleep(config.REQUEST_SLEEP)
    return df


def _normalize_financial_abstract(df_raw: pd.DataFrame, code: str) -> pd.DataFrame:
    """
    将 akshare 返回的财务摘要(宽表)转换为统一长表

    akshare stock_financial_abstract 输出形态:
        指标 | 选项 | 20250930 | 20250630 | 20250331 | 20241231 | ...

    映射:
        每股收益(元)         -> eps
        营业总收入            -> revenue
        销售毛利率            -> gross_margin
        归母净利润 / 净利润   -> net_profit
    """
    # 指标列名通常叫 "指标" 或 "选项",兼容处理
    name_col = None
    for c in df_raw.columns:
        if c in ("指标", "选项"):
            name_col = c
            break
    if name_col is None:
        # 第一列就是指标名
        name_col = df_raw.columns[0]

    # 关键指标关键词映射(akshare 的字段可能略有差异,做模糊匹配)
    target_map = {
        "eps":           ["每股收益", "基本每股收益"],
        "revenue":       ["营业总收入", "主营业务收入", "营业收入"],
        "gross_margin":  ["销售毛利率", "毛利率"],
        "net_profit":    ["归母净利润", "归属于母公司股东的净利润", "净利润"],
    }

    rows = []
    date_cols = [c for c in df_raw.columns if str(c).isdigit() and len(str(c)) == 8]

    for canonical, keywords in target_map.items():
        # 找到匹配关键词的第一行
        match = None
        for kw in keywords:
            mask = df_raw[name_col].astype(str).str.contains(kw, na=False)
            if mask.any():
                match = df_raw[mask].iloc[0]
                break
        if match is None:
            continue
        for d in date_cols:
            val = match[d]
            try:
                val = float(val)
            except (TypeError, ValueError):
                val = None
            rows.append({
                "code": code,
                "report_date": pd.to_datetime(d, format="%Y%m%d"),
                "indicator": canonical,
                "value": val,
            })

    long_df = pd.DataFrame(rows)
    if long_df.empty:
        return long_df

    # 透视回宽表:每行一个报告期
    wide = long_df.pivot_table(
        index=["code", "report_date"],
        columns="indicator",
        values="value",
        aggfunc="first",
    ).reset_index()

    # 标记报告类型
    def _rtype(d):
        m, day = d.month, d.day
        if (m, day) == (12, 31):
            return "年报"
        if (m, day) == (9, 30):
            return "三季报"
        if (m, day) == (6, 30):
            return "中报"
        if (m, day) == (3, 31):
            return "一季报"
        return "其他"

    wide["report_type"] = wide["report_date"].apply(_rtype)
    wide["year"] = wide["report_date"].dt.year
    return wide.sort_values("report_date").reset_index(drop=True)


# =====================================================================
# 3. 行业板块归类
# =====================================================================
def get_sector_mapping(use_cache: bool = True) -> pd.DataFrame:
    """
    返回 code -> sector 映射表

    增强行为:
    - 缓存有效期延长到 30 天(板块归类很少变化)
    - 板块成分股请求带自动重试(3 次,指数退避)
    - 单个板块失败不影响其他板块,**部分成功也会入库**
    - 即使本次拉取失败,会自动降级到上一次的缓存(即使已过期)

    columns: code, sector
    """
    cache_path = _cache_path("sector_map")

    if use_cache:
        # 板块归类变化很慢,30 天内的缓存视为新鲜
        cached = _load_cache("sector_map", ttl_days=30)
        if cached is not None and not cached.empty:
            logger.info(f"使用板块缓存(共 {len(cached)} 只股票,"
                        f"{cached['sector'].nunique()} 个行业)")
            return cached

    import akshare as ak

    rows = []
    sectors_df = None

    # ---- 1. 拉取所有行业板块名称(也带重试)----
    try:
        sectors_df = _retry_with_backoff(
            ak.stock_board_industry_name_em, max_retries=3, base_delay=1.0
        )
    except Exception as e:
        logger.error(f"获取行业板块列表失败(已重试 3 次):{e}")
        # 降级:用旧缓存(即使过期)
        if cache_path.exists():
            try:
                fallback = pd.read_parquet(cache_path)
                logger.warning(f"使用过期的板块缓存({len(fallback)} 只股票),"
                               f"建议稍后重跑刷新")
                return fallback
            except Exception:
                pass
        return pd.DataFrame(columns=["code", "sector"])

    n_total = len(sectors_df)
    n_ok = 0
    n_fail = 0

    # ---- 2. 逐个拉取板块成分股,单个失败不影响整体 ----
    for i, row in enumerate(sectors_df.itertuples(index=False), 1):
        sector_name = getattr(row, "板块名称", None)
        if sector_name is None:
            continue
        try:
            cons = _retry_with_backoff(
                ak.stock_board_industry_cons_em,
                symbol=sector_name,
                max_retries=3, base_delay=0.5,
            )
            for _, c in cons.iterrows():
                rows.append({"code": str(c["代码"]), "sector": sector_name})
            n_ok += 1
            if i % 20 == 0:
                logger.info(f"板块进度 {i}/{n_total} (成功 {n_ok},失败 {n_fail})")
        except Exception as e:
            n_fail += 1
            logger.warning(f"行业 [{sector_name}] 成分股获取失败(已重试):{e}")
        # 适度间隔,降低限流概率
        time.sleep(max(config.REQUEST_SLEEP, 0.5))

    if not rows:
        # 全部失败,尝试用旧缓存兜底
        logger.error(f"所有 {n_total} 个板块都获取失败")
        if cache_path.exists():
            try:
                fallback = pd.read_parquet(cache_path)
                logger.warning(f"使用过期的板块缓存({len(fallback)} 只股票)")
                return fallback
            except Exception:
                pass
        return pd.DataFrame(columns=["code", "sector"])

    df = pd.DataFrame(rows).drop_duplicates(subset=["code"])

    # 即使部分失败也要保存(下次跑可以接着用,不用重头再来)
    _save_cache("sector_map", df)
    logger.info(f"行业板块映射完成:{df['sector'].nunique()} 个行业,"
                f"{len(df)} 只股票"
                f"(成功 {n_ok}/{n_total} 个板块,失败 {n_fail} 个)")
    return df


# =====================================================================
# 4. 批量构建财务全景表
# =====================================================================
def build_financial_universe(
    stock_codes: list[str],
    progress: bool = True,
) -> pd.DataFrame:
    """
    批量获取所有股票的财务数据,返回长表

    columns: code, year, report_date, report_type,
             eps, revenue, gross_margin, net_profit
    """
    frames = []
    n = len(stock_codes)
    for i, code in enumerate(stock_codes, 1):
        if progress and i % 50 == 0:
            logger.info(f"财务数据进度 {i}/{n}")
        try:
            df = get_financial_report(code)
            if not df.empty:
                frames.append(df)
        except Exception as e:
            logger.warning(f"[{code}] 异常:{e}")
            continue

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)
