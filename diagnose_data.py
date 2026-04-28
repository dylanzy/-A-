"""诊断财报数据完整性"""
import sys
sys.path.insert(0, '.')
import pandas as pd
from src import data_fetcher, skill1_growth, config

# 1. 看看一只股票的财报抓取细节
print("=" * 60)
print("【1】单股财报示例 - 招商银行 600036")
print("=" * 60)
df = data_fetcher.get_financial_report("600036", use_cache=True)
if df.empty:
    print("⚠️ 数据为空!")
else:
    print(df[df["report_type"] == "年报"].tail(5))
    print("\n各指标非空数量:")
    for col in ["eps", "revenue", "net_profit"]:
        if col in df.columns:
            n = df[col].notna().sum()
            total = len(df)
            print(f"  {col}: {n}/{total} 非空")
        else:
            print(f"  {col}: ⚠️ 字段缺失!")

# 2. 全市场覆盖率统计
print("\n" + "=" * 60)
print("【2】全市场财报数据覆盖率")
print("=" * 60)
stocks = data_fetcher.get_stock_list()
print(f"股票总数: {len(stocks)}")

# 取前 200 只看看(避免太慢)
sample_codes = stocks["code"].head(200).tolist()
fin_long = data_fetcher.build_financial_universe(sample_codes)
print(f"\n财报记录数:{len(fin_long)}")
print(f"覆盖股票数:{fin_long['code'].nunique()} / 200")

# 各年份各指标的非空率
print("\n年报数据完整性(2023/2024/2025):")
annual = fin_long[fin_long["report_type"] == "年报"]
for year in [2023, 2024, 2025]:
    sub = annual[annual["year"] == year]
    n = sub["code"].nunique()
    print(f"\n  {year} 年报: {n} 只股票")
    for col in ["eps", "revenue", "net_profit"]:
        if col in sub.columns:
            non_null = sub[col].notna().sum()
            ratio = non_null / n * 100 if n > 0 else 0
            print(f"    {col}: {non_null}/{n} 非空 ({ratio:.0f}%)")

# 3. 计算同比后的入选数(不同阈值)
print("\n" + "=" * 60)
print("【3】不同阈值下的入选数(基于这 200 只样本)")
print("=" * 60)
yoy = skill1_growth.compute_yoy(fin_long)
print(f"年报含同比的股票数:{yoy['code'].nunique()}")

for t in [0.05, 0.10, 0.15, 0.20, 0.25, 0.35]:
    config.SKILL1_MIN_GROWTH = t
    q = skill1_growth.screen_skill1(yoy)
    print(f"  阈值 {t*100:>3.0f}%:  {len(q):>3} / 200 只入选")

# 4. 失败股票的具体原因
print("\n" + "=" * 60)
print("【4】哪些股票被排除及原因")
print("=" * 60)
config.SKILL1_MIN_GROWTH = 0.10
n_no_year = 0
n_indicator_missing = 0
n_growth_fail = 0

required_years = config.SKILL1_REQUIRED_YEARS
for code, g in yoy.groupby("code"):
    g_idx = g.set_index("year")
    if not set(required_years).issubset(g_idx.index):
        n_no_year += 1
        continue
    has_data = True
    for ind in config.SKILL1_INDICATORS:
        ycol = f"{ind}_yoy"
        if ycol not in g_idx.columns:
            has_data = False
            break
        for y in required_years[1:]:
            v = g_idx.loc[y, ycol] if y in g_idx.index else None
            if pd.isna(v):
                has_data = False
    if not has_data:
        n_indicator_missing += 1
        continue
    n_growth_fail += 1   # 数据全有,但增速没达标

print(f"  缺少完整年报(2023-2025任一年):  {n_no_year}")
print(f"  指标值有 NaN(数据抓取问题):    {n_indicator_missing}")
print(f"  数据完整但增速没达 10%:         {n_growth_fail}")