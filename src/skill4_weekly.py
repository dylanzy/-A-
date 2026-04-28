"""
Skill 4 · 周K 线技术面筛选

判定基准:**最近一根已收盘的完整周K** (避免本周尚未结束带来的不稳定结果)

筛选条件(全部满足才入选):
    1. 该周是阳线:close > open
    2. 该周成交量 >= 上一根完整周K成交量 * (1 + min_vol_growth)  默认增幅 >= 70%
    3. 周线均线多头排列:MA5 > MA10 > MA20 > MA30 > MA60
    4. 周收盘价 > MA5(题目原文要求)

数据源:akshare stock_zh_a_hist(period='weekly', adjust='qfq')

输出列(每只股票一行):
    code, last_week_date, last_close, last_open, last_vol,
    prev_vol, vol_growth,
    ma5, ma10, ma20, ma30, ma60,
    is_yang, vol_passed, ma_aligned, close_above_ma5,
    skill4_pass
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

from . import config

logger = logging.getLogger(__name__)


# 默认参数(也可在 config.py 中维护;为避免 Skill4 过度污染 config,默认值在此)
DEFAULT_MIN_VOL_GROWTH = 0.70   # 成交量同比上一周增幅下限
WEEKLY_HISTORY_DAYS = 600       # 拉多少天的日线后再聚合,保证 MA60 周(≈420 个交易日 + 缓冲)
WEEKLY_MA_PERIODS = (5, 10, 20, 30, 60)


# =====================================================================
# 1. 日线 -> 周线
# =====================================================================
def get_weekly_kline(code: str, use_cache: bool = True) -> pd.DataFrame:
    """
    获取周 K 线数据,直接调用 akshare 的 weekly 接口
    返回 columns: date(周收盘日), open, high, low, close, vol, amount
    """
    from . import data_fetcher

    cache_name = f"weekly_{code}"
    if use_cache:
        cached = data_fetcher._load_cache(cache_name, ttl_days=1)
        if cached is not None:
            return cached

    import akshare as ak
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=WEEKLY_HISTORY_DAYS)).strftime("%Y%m%d")

    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="weekly",
            start_date=start,
            end_date=end,
            adjust="qfq",
        )
    except Exception as e:
        logger.warning(f"[{code}] 周线获取失败: {e}")
        return pd.DataFrame()

    if df is None or df.empty:
        return pd.DataFrame()

    rename = {"日期": "date", "开盘": "open", "收盘": "close",
              "最高": "high", "最低": "low",
              "成交量": "vol", "成交额": "amount"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    data_fetcher._save_cache(cache_name, df)
    time.sleep(config.REQUEST_SLEEP)
    return df


def _last_completed_week(df_weekly: pd.DataFrame) -> pd.DataFrame:
    """
    取"最近一根已收盘"的完整周K。
    akshare weekly 接口返回的"日期"通常已是周内最后一个交易日,
    但如果当周还没收盘,接口会把当周尚未结束的数据也聚合返回 —— 我们要排除它。

    判定方式:
        最后一行的 date 必须 < 本周一(也就是说,这一行属于"上周或更早结束")
    """
    if df_weekly.empty:
        return df_weekly

    today = pd.Timestamp(datetime.now().date())
    # 本周一
    monday_this_week = today - pd.Timedelta(days=today.weekday())

    # 把所有日期 >= 本周一的数据丢掉(这部分属于"本周未完成")
    completed = df_weekly[df_weekly["date"] < monday_this_week].copy()
    return completed.reset_index(drop=True)


# =====================================================================
# 2. 单股 Skill4 判定
# =====================================================================
def evaluate_skill4(
    code: str,
    df_weekly: Optional[pd.DataFrame] = None,
    min_vol_growth: float = DEFAULT_MIN_VOL_GROWTH,
) -> dict:
    """
    对单只股票评估 Skill4 各条件,返回结果字典(无论是否通过)
    """
    if df_weekly is None:
        df_weekly = get_weekly_kline(code)

    if df_weekly.empty:
        return {"code": code, "skill4_pass": False, "reason": "周线数据为空"}

    df = _last_completed_week(df_weekly)

    # 至少需要 60 周数据才能算 MA60
    if len(df) < max(WEEKLY_MA_PERIODS) + 1:
        return {
            "code": code,
            "skill4_pass": False,
            "reason": f"周线数据不足 {max(WEEKLY_MA_PERIODS)+1} 周(实际 {len(df)} 周)",
        }

    # 计算各周线均线
    close = df["close"]
    ma_values = {}
    for n in WEEKLY_MA_PERIODS:
        ma_values[f"ma{n}"] = float(close.rolling(n).mean().iloc[-1])

    last = df.iloc[-1]
    prev = df.iloc[-2]

    last_close = float(last["close"])
    last_open = float(last["open"])
    last_vol = float(last["vol"])
    prev_vol = float(prev["vol"])

    # 条件 1:阳线
    is_yang = last_close > last_open

    # 条件 2:成交量增幅 >= min_vol_growth
    if prev_vol <= 0:
        vol_growth = None
        vol_passed = False
    else:
        vol_growth = (last_vol - prev_vol) / prev_vol
        vol_passed = vol_growth >= min_vol_growth

    # 条件 3:均线多头排列 MA5 > MA10 > MA20 > MA30 > MA60
    ma5, ma10, ma20, ma30, ma60 = (
        ma_values["ma5"], ma_values["ma10"], ma_values["ma20"],
        ma_values["ma30"], ma_values["ma60"],
    )
    ma_aligned = (ma5 > ma10) and (ma10 > ma20) and (ma20 > ma30) and (ma30 > ma60)

    # 条件 4:close > MA5
    close_above_ma5 = last_close > ma5

    skill4_pass = bool(is_yang and vol_passed and ma_aligned and close_above_ma5)

    return {
        "code": code,
        "last_week_date": last["date"],
        "last_open": last_open,
        "last_close": last_close,
        "last_vol": last_vol,
        "prev_vol": prev_vol,
        "vol_growth": vol_growth,
        **ma_values,
        "is_yang": is_yang,
        "vol_passed": vol_passed,
        "ma_aligned": ma_aligned,
        "close_above_ma5": close_above_ma5,
        "skill4_pass": skill4_pass,
    }


# =====================================================================
# 3. 批量评估
# =====================================================================
def screen_skill4(
    codes: list[str],
    min_vol_growth: float = DEFAULT_MIN_VOL_GROWTH,
    progress: bool = True,
) -> pd.DataFrame:
    """
    对一批股票批量评估 Skill4,返回每只股票的判定明细
    (含未通过的,便于上层做诊断;只取通过的可在外面 .query("skill4_pass"))
    """
    rows = []
    n = len(codes)
    for i, code in enumerate(codes, 1):
        if progress and i % 50 == 0:
            logger.info(f"Skill4 周线进度 {i}/{n}")
        try:
            res = evaluate_skill4(code, min_vol_growth=min_vol_growth)
            rows.append(res)
        except Exception as e:
            logger.warning(f"[{code}] Skill4 评估异常: {e}")
            rows.append({"code": code, "skill4_pass": False, "reason": str(e)})

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # 通过的排前面
    if "skill4_pass" in df.columns:
        df = df.sort_values("skill4_pass", ascending=False).reset_index(drop=True)
    return df
