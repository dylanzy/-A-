"""
Skill 1:筛选近3年(2023/2024/2025年报)+ 2026Q1(可选展示)
4 个核心指标(EPS、营收、毛利率、净利润)同比增长率均 ≥ 35%,且逐年增长。
"""
from __future__ import annotations
import logging
import pandas as pd

from . import config

logger = logging.getLogger(__name__)


def compute_yoy(df_long: pd.DataFrame) -> pd.DataFrame:
    """
    计算同比增长率,只关心年报数据(report_type=年报)

    输入 df_long columns: code, year, report_date, report_type,
                          eps, revenue, gross_margin, net_profit
    输出: 加上 *_yoy 列
    """
    if df_long.empty:
        return df_long

    annual = df_long[df_long["report_type"] == "年报"].copy()
    annual = annual.sort_values(["code", "year"]).reset_index(drop=True)

    for ind in config.SKILL1_INDICATORS:
        if ind not in annual.columns:
            annual[ind] = pd.NA
            continue
        annual[f"{ind}_yoy"] = (
            annual.groupby("code")[ind]
                  .pct_change()
                  .replace([float("inf"), float("-inf")], pd.NA)
        )

    return annual


def screen_skill1(
    annual_yoy: pd.DataFrame,
    required_years: list[int] = None,
    min_growth: float = None,
) -> pd.DataFrame:
    """
    Skill1 筛选规则:

    4 项指标(EPS / 营收 / 毛利率 / 净利润)的连续 N-1 年同比增长率均 ≥ min_growth
    例如 required_years=[2023,2024,2025] 时,需要 2024、2025 两年的同比增速
    都 ≥ 35%。

    返回:每只入选股票一行,含各年增长率/水平值明细
    """
    if required_years is None:
        required_years = config.SKILL1_REQUIRED_YEARS
    if min_growth is None:
        min_growth = config.SKILL1_MIN_GROWTH

    if annual_yoy.empty:
        return pd.DataFrame()

    # 同比增长判定的年份:第二年开始(因为第一年没有 yoy)
    growth_years = required_years[1:]   # 例如 [2024, 2025]

    # 4 项指标全部按"同比增速 ≥ min_growth"判定
    growth_indicators = config.SKILL1_INDICATORS  # eps, revenue, gross_margin, net_profit

    qualified_codes = []

    for code, g in annual_yoy.groupby("code"):
        g = g.set_index("year")
        # 1. 必须包含所有 required_years 的年报
        if not set(required_years).issubset(g.index):
            continue

        ok = True
        detail = {"code": code}

        for ind in growth_indicators:
            ycol = f"{ind}_yoy"
            if ycol not in g.columns:
                ok = False
                break
            for y in growth_years:
                v = g.loc[y, ycol] if y in g.index else None
                if pd.isna(v) or v < min_growth:
                    ok = False
                detail[f"{ind}_yoy_{y}"] = v
            # 记录最新年水平值(供 Skill3 排序)
            if ind in g.columns and required_years[-1] in g.index:
                detail[ind] = g.loc[required_years[-1], ind]

        if ok:
            qualified_codes.append(detail)

    if not qualified_codes:
        return pd.DataFrame()

    return pd.DataFrame(qualified_codes)


def attach_2026q1(
    qualified: pd.DataFrame,
    df_long: pd.DataFrame,
) -> pd.DataFrame:
    """如开启,将 2026Q1 的指标值附加到结果中(仅展示用,不参与筛选)"""
    if not config.SKILL1_INCLUDE_2026Q1 or qualified.empty:
        return qualified

    q1 = df_long[
        (df_long["report_type"] == "一季报")
        & (df_long["year"] == 2026)
    ].copy()
    if q1.empty:
        return qualified

    keep_cols = ["code"] + [c for c in config.SKILL1_INDICATORS if c in q1.columns]
    q1 = q1[keep_cols].rename(columns={c: f"{c}_2026Q1" for c in keep_cols if c != "code"})
    return qualified.merge(q1, on="code", how="left")
