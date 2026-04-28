"""
主流水线:串联 Skill1 -> Skill2 -> Skill3,生成最终 Markdown 报告
"""
from __future__ import annotations
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config, data_fetcher
from . import skill1_growth, skill2_sector, skill3_compare, skill4_weekly

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def run_pipeline(
    sample_size: int | None = None,
    output_dir: Path | str | None = None,
) -> dict:
    """
    完整流水线:
        1. 拉取沪深 A 股列表
        2. 批量拉取财报
        3. Skill1 同比增长筛选
        4. Skill2 板块归类
        5. Skill3 板块内对比
        6. 输出 Markdown 报告

    Args:
        sample_size: 调试用,只取前 N 只股票;None=全市场
        output_dir: 报告输出目录,默认 config.REPORT_DIR
    Returns:
        {"qualified": ..., "ranked": ..., "report_path": ...}
    """
    output_dir = Path(output_dir) if output_dir else config.REPORT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # ------- 1. 股票列表 -------
    logger.info("[1/7] 加载沪深 A 股列表")
    stocks = data_fetcher.get_stock_list()
    if config.EXCLUDE_ST:
        stocks = stocks[~stocks["is_st"]].reset_index(drop=True)
    name_lookup = dict(zip(stocks["code"], stocks["name"]))

    if sample_size:
        stocks = stocks.head(sample_size).reset_index(drop=True)
        logger.info(f"调试模式:仅处理前 {sample_size} 只")
    logger.info(f"共 {len(stocks)} 只候选股票")

    # ------- 2. 财报 -------
    logger.info("[2/7] 批量拉取财报(使用本地缓存)")
    fin_long = data_fetcher.build_financial_universe(stocks["code"].tolist())
    if fin_long.empty:
        logger.error("没有拉到任何财报数据,退出")
        return {"qualified": pd.DataFrame(), "ranked": pd.DataFrame(), "report_path": None}
    logger.info(f"财报记录:{len(fin_long)} 行,覆盖 {fin_long['code'].nunique()} 只股票")

    # ------- 3. Skill1 -------
    logger.info("[3/7] Skill1 同比增长筛选")
    annual_yoy = skill1_growth.compute_yoy(fin_long)
    qualified = skill1_growth.screen_skill1(annual_yoy)
    qualified = skill1_growth.attach_2026q1(qualified, fin_long)
    logger.info(f"Skill1 入选:{len(qualified)} 只")

    if qualified.empty:
        logger.warning("Skill1 未筛出任何股票,流水线终止")
        return {"qualified": qualified, "ranked": pd.DataFrame(), "report_path": None}

    # ------- 4. Skill2 -------
    logger.info("[4/7] Skill2 板块归类")
    sector_map = data_fetcher.get_sector_mapping()
    qualified_sec = skill2_sector.attach_sector(qualified, sector_map)
    summary = skill2_sector.sector_summary(qualified_sec)
    logger.info(f"Skill2 板块分布:\n{summary.to_string(index=False)}")

    # ------- 5. Skill3 -------
    logger.info("[5/7] Skill3 板块内对比排名")
    ranked = skill3_compare.rank_within_sector(qualified_sec)
    n_winner = int(ranked["is_winner"].sum())
    logger.info(f"Skill3 入选(占优势):{n_winner} 只")

    # ------- 6. Skill4 周K线技术筛选(可选) -------
    if config.SKILL4_ENABLED and not ranked.empty:
        # 只对 Skill3 入选的股票做周线评估,节省时间
        winner_codes = ranked[ranked["is_winner"]]["code"].tolist()
        if winner_codes:
            logger.info(f"[6/7] Skill4 周K线技术筛选(候选 {len(winner_codes)} 只)")
            sk4 = skill4_weekly.screen_skill4(
                winner_codes,
                min_vol_growth=config.SKILL4_MIN_VOL_GROWTH,
            )
            ranked = ranked.merge(sk4, on="code", how="left")
            ranked["skill4_pass"] = ranked["skill4_pass"].fillna(False)
            n_skill4 = int(ranked["skill4_pass"].sum())
            logger.info(f"Skill4 通过:{n_skill4} 只")
        else:
            logger.info("[6/7] Skill3 无入选,跳过 Skill4")
            ranked["skill4_pass"] = False
    else:
        ranked["skill4_pass"] = False

    # ------- 7. 报告 -------
    logger.info("[7/7] 生成 Markdown 报告")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"screening_report_{timestamp}.md"
    skill3_compare.generate_markdown_report(
        ranked, report_path, name_lookup=name_lookup
    )
    # CSV 副本(便于 Excel 打开)
    csv_path = output_dir / f"screening_report_{timestamp}.csv"
    ranked.to_csv(csv_path, index=False, encoding="utf-8-sig")

    logger.info(f"报告完成:{report_path}")
    return {
        "qualified": qualified_sec,
        "ranked": ranked,
        "report_path": report_path,
        "csv_path": csv_path,
    }


if __name__ == "__main__":
    # 命令行入口:直接执行时跑全市场
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=None,
                    help="调试用,仅处理前 N 只股票")
    ap.add_argument("--out", type=str, default=None, help="报告输出目录")
    args = ap.parse_args()
    run_pipeline(sample_size=args.sample, output_dir=args.out)
