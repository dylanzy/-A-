"""
项目全局配置
"""
from pathlib import Path

# ======== 路径配置 ========
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORT_DIR = PROJECT_ROOT / "reports"
DATA_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)

CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# ======== Skill1 筛选参数 ========
# 3 个核心指标:每股收益、主营业务收入、净利润
SKILL1_INDICATORS = ["eps", "revenue", "net_profit"]
SKILL1_INDICATOR_NAMES = {
    "eps": "每股收益",
    "revenue": "主营业务收入",
    "net_profit": "净利润",
}

# 同比增长率阈值:3 个指标(EPS/营收/净利润)的同比增速必须 >= 25%,且连续达标
SKILL1_MIN_GROWTH = 0.10  # 25%

SKILL1_MAX_GROWTH = None  # 不设上限

# 财年范围:2023/2024/2025 完整年报 + 2026Q1(可选)
SKILL1_REQUIRED_YEARS = [2023, 2024, 2025]
SKILL1_INCLUDE_2026Q1 = True  # 若 2026Q1 已披露,纳入展示但不参与逐年增长判断

# ======== Skill2 板块归类 ========
# 使用东方财富行业板块作为主分类
SECTOR_SOURCE = "em_industry"  # em_industry / sw_industry / concept

# ======== Skill3 板块内对比 ========
# 入选规则:在同板块内,4 个指标中至少 N 项进入板块前 50%
SKILL3_LEADING_THRESHOLD = 2     # 至少领先 2 项
SKILL3_TOP_PERCENTILE = 0.50     # 板块内前 50%
SKILL3_MIN_PEERS = 3             # 板块内至少有 N 只票才进行对比(否则跳过)

# ======== Skill4 周K线技术筛选 ========
# 基准:最近一根已收盘的完整周 K 线
SKILL4_ENABLED = True              # 是否在主流水线中执行 Skill4
SKILL4_MIN_VOL_GROWTH = 0.70       # 周成交量同比上一根周 K 的最小增幅(70%)
SKILL4_MA_PERIODS = (5, 10, 20, 30, 60)  # 多头排列要求的均线周期

# ======== 数据源 ========
DATA_SOURCE = "akshare"   # 当前仅支持 akshare
REQUEST_SLEEP = 0.3       # 每次接口调用间隔秒数(防限流)

# ======== 排除条件 ========
EXCLUDE_ST = True              # 排除 ST/*ST
EXCLUDE_NEW_LISTING_DAYS = 365 # 排除上市不满 N 天的次新股
EXCLUDE_BJ = True              # 排除北交所(只看沪深 A 股)
