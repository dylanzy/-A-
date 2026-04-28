"""
Skill 2:对 Skill1 入选股票按行业板块归类
"""
from __future__ import annotations
import pandas as pd


def attach_sector(
    qualified: pd.DataFrame,
    sector_map: pd.DataFrame,
) -> pd.DataFrame:
    """
    把 sector(板块)字段拼接到 qualified 上

    qualified.columns: code, ...(各指标)
    sector_map.columns: code, sector
    """
    if qualified.empty:
        return qualified
    out = qualified.merge(sector_map, on="code", how="left")
    out["sector"] = out["sector"].fillna("未分类")
    return out


def group_by_sector(qualified_with_sector: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """按 sector 字段分组,返回 {sector_name: sub_df}"""
    if qualified_with_sector.empty:
        return {}
    return {
        s: g.reset_index(drop=True)
        for s, g in qualified_with_sector.groupby("sector")
    }


def sector_summary(qualified_with_sector: pd.DataFrame) -> pd.DataFrame:
    """每个板块的入选数量统计"""
    if qualified_with_sector.empty:
        return pd.DataFrame()
    return (
        qualified_with_sector.groupby("sector")
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )
