"""
Skill 3:在每个板块内对 4 个指标进行排名,
        若某只股票至少在 N(默认 2)项指标上进入板块前 50%,
        则视为"占优势",入选并按指标领先数 + 综合得分排序输出 Markdown 报告。
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import pandas as pd

from . import config


def rank_within_sector(
    qualified_with_sector: pd.DataFrame,
    indicators: list[str] = None,
    top_pct: float = None,
    leading_threshold: int = None,
    min_peers: int = None,
) -> pd.DataFrame:
    """
    在每个 sector 内,对每个指标做排名(降序;百分位越大越优)
    返回 columns:
        code, name, sector, eps, revenue, gross_margin, net_profit,
        eps_rank, revenue_rank, gross_margin_rank, net_profit_rank,
        eps_pct, ...,
        leading_count(领先项数),
        composite_score(综合百分位均值),
        is_winner(是否领先达标)
    """
    indicators = indicators or config.SKILL1_INDICATORS
    top_pct = top_pct if top_pct is not None else config.SKILL3_TOP_PERCENTILE
    leading_threshold = leading_threshold or config.SKILL3_LEADING_THRESHOLD
    min_peers = min_peers or config.SKILL3_MIN_PEERS

    if qualified_with_sector.empty:
        return qualified_with_sector

    df = qualified_with_sector.copy()

    # 在板块内排名
    for ind in indicators:
        if ind not in df.columns:
            df[ind] = pd.NA
        df[f"{ind}_rank"] = (
            df.groupby("sector")[ind].rank(method="min", ascending=False)
        )
        # 百分位:1.0 = 最优,0.0 = 最末
        df[f"{ind}_pct"] = (
            df.groupby("sector")[ind].rank(method="average", pct=True)
        )

    # 同板块成员数,过小不参与对比
    df["peers_in_sector"] = df.groupby("sector")["code"].transform("count")

    # 计算 leading_count:在多少个指标上进入板块前 top_pct
    leading_cols = [f"{ind}_pct" for ind in indicators]
    df["leading_count"] = (df[leading_cols] >= (1 - top_pct)).sum(axis=1)

    # 综合得分(用百分位均值)
    df["composite_score"] = df[leading_cols].mean(axis=1)

    # 是否入选
    df["is_winner"] = (
        (df["leading_count"] >= leading_threshold)
        & (df["peers_in_sector"] >= min_peers)
    )

    return df.sort_values(
        ["is_winner", "leading_count", "composite_score"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


# ===========================================================
# Markdown 报告
# ===========================================================
def generate_markdown_report(
    ranked: pd.DataFrame,
    output_path: Path | str,
    name_lookup: dict[str, str] | None = None,
) -> Path:
    """
    生成 Markdown 报告:
      1. 概览统计
      2. 入选股票总表(按 leading_count 降序、综合得分降序)
      3. 按板块分组的明细对比表
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    inds = config.SKILL1_INDICATORS
    ind_names = config.SKILL1_INDICATOR_NAMES

    if name_lookup is None:
        name_lookup = {}

    def _fmt_value(v, kind):
        if pd.isna(v):
            return "—"
        if kind == "gross_margin":
            return f"{v:.2f}%"
        if kind in ("eps",):
            return f"{v:.2f}"
        if kind in ("revenue", "net_profit"):
            # 千分位,单位元(akshare 返回原值)
            if abs(v) >= 1e8:
                return f"{v/1e8:.2f}亿"
            if abs(v) >= 1e4:
                return f"{v/1e4:.2f}万"
            return f"{v:.0f}"
        return str(v)

    def _fmt_pct(v):
        return "—" if pd.isna(v) else f"{v*100:.1f}%"

    lines = []
    lines.append(f"# 沪深 A 股筛选报告\n")
    lines.append(f"**生成时间**:{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append("---\n")

    # ------- 概览 -------
    lines.append("## 一、筛选规则\n")
    lines.append(
        f"- **Skill1**:近 {len(config.SKILL1_REQUIRED_YEARS)} 年"
        f"({config.SKILL1_REQUIRED_YEARS[0]}-{config.SKILL1_REQUIRED_YEARS[-1]})年报中,"
        f"3 项指标(每股收益 / 主营业务收入 / 净利润)的"
        f"同比增长率连年 ≥ {config.SKILL1_MIN_GROWTH*100:.0f}%\n"
    )
    lines.append("- **Skill2**:按东方财富行业板块归类\n")
    lines.append(
        f"- **Skill3**:在所属板块内,{len(inds)} 项指标中至少 "
        f"{config.SKILL3_LEADING_THRESHOLD} 项进入板块前 "
        f"{config.SKILL3_TOP_PERCENTILE*100:.0f}%\n"
    )
    if "skill4_pass" in ranked.columns:
        lines.append(
            f"- **Skill4**(技术面,基于最近一根已收盘的完整周K):"
            f"该周阳线 + 成交量增幅 ≥ {config.SKILL4_MIN_VOL_GROWTH*100:.0f}% + "
            f"周线 MA5 > MA10 > MA20 > MA30 > MA60 + 收盘价 > MA5\n"
        )
    lines.append("\n---\n")

    # ------- 总览统计 -------
    n_total = len(ranked)
    n_winner = int(ranked["is_winner"].sum()) if not ranked.empty else 0
    n_sectors = ranked["sector"].nunique() if not ranked.empty else 0
    has_skill4 = "skill4_pass" in ranked.columns
    n_skill4 = int(ranked["skill4_pass"].sum()) if has_skill4 else 0

    lines.append("## 二、概览统计\n")
    lines.append(f"- Skill1 入选股票数:**{n_total}**")
    lines.append(f"- 涉及板块数:**{n_sectors}**")
    lines.append(f"- Skill3 入选(占优势):**{n_winner}**")
    if has_skill4:
        lines.append(f"- Skill4 通过(技术面共振):**{n_skill4}** ⭐\n")
    else:
        lines.append("")

    if ranked.empty:
        lines.append("\n_当前筛选条件下没有符合的股票。_\n")
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path

    # ------- 入选总表 -------
    lines.append("## 三、Skill3 入选总表(按指标领先数 / 综合得分降序)\n")
    winners = ranked[ranked["is_winner"]].copy()
    if winners.empty:
        lines.append("\n_无股票满足: 至少 2 项指标在板块内领先 的条件。_\n")
    else:
        header = (
            "| 排名 | 代码 | 名称 | 板块 | 领先项数 | 综合得分 |"
            + "".join(f" {ind_names[i]} |" for i in inds)
        )
        sep = "|" + "|".join(["---"] * (6 + len(inds))) + "|"
        lines.append(header)
        lines.append(sep)
        for rk, (_, row) in enumerate(winners.iterrows(), 1):
            name = name_lookup.get(row["code"], "")
            cells = [
                str(rk),
                row["code"],
                name,
                str(row["sector"]),
                str(int(row["leading_count"])),
                f"{row['composite_score']*100:.1f}",
            ]
            for ind in inds:
                cells.append(_fmt_value(row.get(ind), ind))
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    # ------- Skill4 共振表 -------
    if has_skill4:
        lines.append("\n## 四、⭐ Skill4 技术面共振(最终首选)\n")
        lines.append(
            "_同时满足 Skill1-3 基本面筛选 + Skill4 周K线技术面共振的股票。_\n"
        )
        skill4_winners = ranked[
            ranked["is_winner"] & ranked["skill4_pass"]
        ].copy()
        if skill4_winners.empty:
            lines.append("\n_当前无股票同时满足 Skill3 与 Skill4。_\n")
        else:
            header = (
                "| 排名 | 代码 | 名称 | 板块 | 周收盘 | 周涨跌 | "
                "成交量增幅 | MA5 | MA10 | MA20 | MA30 | MA60 |"
            )
            sep = "|" + "|".join(["---"] * 12) + "|"
            lines.append(header)
            lines.append(sep)
            # 按综合得分降序
            skill4_winners = skill4_winners.sort_values(
                ["leading_count", "composite_score"], ascending=[False, False]
            )
            for rk, (_, row) in enumerate(skill4_winners.iterrows(), 1):
                name = name_lookup.get(row["code"], "")
                last_close = row.get("last_close")
                last_open = row.get("last_open")
                pct = ((last_close - last_open) / last_open * 100
                       if last_open and not pd.isna(last_open) else None)
                vg = row.get("vol_growth")

                def _f(v, fmt="{:.2f}"):
                    return "—" if pd.isna(v) else fmt.format(v)

                cells = [
                    str(rk),
                    str(row["code"]),
                    name,
                    str(row["sector"]),
                    _f(last_close),
                    _f(pct, "{:+.2f}%"),
                    _f(vg * 100 if vg is not None and not pd.isna(vg) else None, "{:+.1f}%"),
                    _f(row.get("ma5")),
                    _f(row.get("ma10")),
                    _f(row.get("ma20")),
                    _f(row.get("ma30")),
                    _f(row.get("ma60")),
                ]
                lines.append("| " + " | ".join(cells) + " |")
            lines.append("")

    # ------- 按板块分组明细 -------
    lines.append("\n---\n## 五、各板块明细对比\n")
    for sector, g in ranked.groupby("sector"):
        g = g.sort_values(
            ["is_winner", "leading_count", "composite_score"],
            ascending=[False, False, False],
        )
        lines.append(f"### {sector}(共 {len(g)} 只)\n")

        header = (
            "| 代码 | 名称 | 入选 | 领先项 |"
            + "".join(f" {ind_names[i]}(板块排名) |" for i in inds)
        )
        sep = "|" + "|".join(["---"] * (4 + len(inds))) + "|"
        lines.append(header)
        lines.append(sep)
        for _, row in g.iterrows():
            name = name_lookup.get(row["code"], "")
            mark = "✅" if row["is_winner"] else "—"
            cells = [row["code"], name, mark, str(int(row["leading_count"]))]
            for ind in inds:
                v = _fmt_value(row.get(ind), ind)
                rk = row.get(f"{ind}_rank")
                rk_str = f"#{int(rk)}" if pd.notna(rk) else "—"
                cells.append(f"{v} ({rk_str})")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    lines.append("\n---\n")
    lines.append(
        "_本报告由量化筛选脚本自动生成,仅作数据分析参考,不构成投资建议。_\n"
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
