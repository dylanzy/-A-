"""
辅助筛选条件(可选,用于在 Skill1-3 流水线之前/之后附加过滤)
- 基本面:PE / PB / 市值
- 技术面:MA 多头排列 / MACD 金叉 / RSI
- 资金面:换手率 / 量比
- 板块过滤:仅保留指定板块或排除特定板块
"""
from __future__ import annotations
import logging
import pandas as pd

logger = logging.getLogger(__name__)


# =====================================================================
# 基本面快照(实时行情接口里就有 PE/PB/市值)
# =====================================================================
def get_fundamental_snapshot(use_cache: bool = True) -> pd.DataFrame:
    """
    返回沪深 A 股实时基本面快照
    columns: code, name, latest, change_pct, pe_ttm, pb, mkt_cap, turnover_rate, volume_ratio
    """
    import akshare as ak

    df = ak.stock_zh_a_spot_em()
    keep_map = {
        "代码": "code",
        "名称": "name",
        "最新价": "latest",
        "涨跌幅": "change_pct",
        "市盈率-动态": "pe_ttm",
        "市净率": "pb",
        "总市值": "mkt_cap",
        "换手率": "turnover_rate",
        "量比": "volume_ratio",
    }
    cols = [c for c in keep_map if c in df.columns]
    df = df[cols].rename(columns=keep_map)
    return df


# =====================================================================
# 基本面过滤
# =====================================================================
def filter_fundamentals(
    df: pd.DataFrame,
    pe_min: float | None = None,
    pe_max: float | None = None,
    pb_min: float | None = None,
    pb_max: float | None = None,
    mkt_cap_min: float | None = None,
    mkt_cap_max: float | None = None,
) -> pd.DataFrame:
    """对包含 pe_ttm/pb/mkt_cap 列的 df 进行过滤"""
    out = df.copy()
    if pe_min is not None and "pe_ttm" in out.columns:
        out = out[out["pe_ttm"].fillna(-1) >= pe_min]
    if pe_max is not None and "pe_ttm" in out.columns:
        out = out[(out["pe_ttm"].notna()) & (out["pe_ttm"] <= pe_max)]
    if pb_min is not None and "pb" in out.columns:
        out = out[out["pb"].fillna(-1) >= pb_min]
    if pb_max is not None and "pb" in out.columns:
        out = out[(out["pb"].notna()) & (out["pb"] <= pb_max)]
    if mkt_cap_min is not None and "mkt_cap" in out.columns:
        out = out[out["mkt_cap"].fillna(0) >= mkt_cap_min]
    if mkt_cap_max is not None and "mkt_cap" in out.columns:
        out = out[(out["mkt_cap"].notna()) & (out["mkt_cap"] <= mkt_cap_max)]
    return out.reset_index(drop=True)


# =====================================================================
# 技术指标(基于历史日线计算)
# =====================================================================
def get_daily_kline(code: str, days: int = 250) -> pd.DataFrame:
    """获取最近 N 天日线;前复权"""
    import akshare as ak
    from datetime import datetime, timedelta
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days * 2)).strftime("%Y%m%d")
    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start,
            end_date=end,
            adjust="qfq",
        )
    except Exception as e:
        logger.warning(f"[{code}] 日线获取失败:{e}")
        return pd.DataFrame()
    if df is None or df.empty:
        return df
    rename = {"日期": "date", "开盘": "open", "收盘": "close",
              "最高": "high", "最低": "low", "成交量": "vol", "成交额": "amount"}
    df = df.rename(columns=rename)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def compute_technical(df_kline: pd.DataFrame) -> dict:
    """计算最新一日的 MA/MACD/RSI 关键技术指标快照"""
    if df_kline.empty or len(df_kline) < 60:
        return {}
    close = df_kline["close"]

    def ema(s, n):
        return s.ewm(span=n, adjust=False).mean()

    ma5 = close.rolling(5).mean().iloc[-1]
    ma10 = close.rolling(10).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    ma60 = close.rolling(60).mean().iloc[-1]

    ema12, ema26 = ema(close, 12), ema(close, 26)
    dif = ema12 - ema26
    dea = ema(dif, 9)
    macd = (dif - dea) * 2

    delta = close.diff()
    up = delta.clip(lower=0).rolling(14).mean()
    down = -delta.clip(upper=0).rolling(14).mean()
    rs = up / down.replace(0, 1e-9)
    rsi14 = 100 - 100 / (1 + rs)

    return {
        "close": float(close.iloc[-1]),
        "ma5": float(ma5),
        "ma10": float(ma10),
        "ma20": float(ma20),
        "ma60": float(ma60),
        "ma_bull": ma5 > ma10 > ma20 > ma60,
        "macd_golden_cross_5d": bool(
            ((dif.shift(1) < dea.shift(1)) & (dif > dea)).iloc[-5:].any()
        ),
        "rsi14": float(rsi14.iloc[-1]),
    }


# =====================================================================
# 板块过滤
# =====================================================================
def filter_by_sector(
    df: pd.DataFrame,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> pd.DataFrame:
    """按 sector 字段做包含/排除过滤"""
    if "sector" not in df.columns:
        return df
    out = df.copy()
    if include:
        out = out[out["sector"].isin(include)]
    if exclude:
        out = out[~out["sector"].isin(exclude)]
    return out.reset_index(drop=True)
