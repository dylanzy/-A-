# 沪深 A 股股票筛选系统

一个基于 **akshare + Jupyter Notebook** 的轻量级 A 股筛选项目,实现三个递进的筛选 Skill,最终生成排序后的 Markdown 报告。

## 核心功能

### Skill 1 · 成长性筛选
扫描 2023/2024/2025 三个完整年报,4 项核心指标(每股收益、主营业务收入、毛利率、净利润)的**同比增长率连续两年(2024、2025)≥ 35%** 的股票入选。若 2026 年一季报已发布,附加展示。

### Skill 2 · 板块归类
将 Skill1 入选的股票按东方财富行业板块归类。

### Skill 3 · 同板块对比
每个板块内对 4 项指标分别排名,**至少 2 项进入板块前 50%** 即视为"占优势",入选。

### Skill 4 · 周K 线技术共振(可选)
对 Skill3 入选的股票做技术面叠加,基准为**最近一根已收盘的完整周K**:
- 该周是阳线(close > open)
- 该周成交量较上一根完整周K 增幅 ≥ 70%
- 周线 MA5 > MA10 > MA20 > MA30 > MA60(完美多头排列)
- 周收盘价 > MA5

按"领先项数 → 综合得分"降序输出 Markdown 报告,Skill4 通过的股票单独标记为"⭐ 技术面共振"。

## 目录结构

```
stock_screener_proj/
├── src/
│   ├── config.py               全局配置(阈值、年份、缓存等)
│   ├── data_fetcher.py         akshare 封装 + 本地缓存
│   ├── skill1_growth.py        Skill1 同比增长筛选
│   ├── skill2_sector.py        Skill2 板块归类
│   ├── skill3_compare.py       Skill3 板块内对比 + Markdown 报告
│   ├── skill4_weekly.py        Skill4 周K线技术筛选(阳线+放量+均线多头)
│   ├── auxiliary_filters.py    基本面/技术面/资金面附加过滤
│   └── pipeline.py             串联所有 Skill 的主流水线
├── notebooks/
│   └── main_screening.ipynb    主入口 Notebook(交互式)
├── data/cache/                 财报、板块映射的本地缓存
├── reports/                    生成的 Markdown 报告输出
├── requirements.txt
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动 Notebook

```bash
jupyter notebook notebooks/main_screening.ipynb
```

按 Notebook 内的步骤逐格执行即可。**强烈建议先用 `sample_size=50` 跑通**(约 5 分钟),验证后再放开全市场。

### 3. 命令行直接运行(可选)

```bash
# 调试:只跑前 100 只
python -m src.pipeline --sample 100

# 全市场
python -m src.pipeline
```

报告会输出到 `reports/screening_report_<时间戳>.md` 和同名 `.csv`。

## 关键参数说明

所有可调参数集中在 `src/config.py`:

| 参数 | 含义 | 默认值 |
| --- | --- | --- |
| `SKILL1_MIN_GROWTH` | 4 项指标同比增速下限 | `0.35`(即 35%) |
| `SKILL1_REQUIRED_YEARS` | 必须有完整年报的年份 | `[2023,2024,2025]` |
| `SKILL1_INCLUDE_2026Q1` | 是否附加展示 2026Q1 | `True` |
| `SKILL3_LEADING_THRESHOLD` | Skill3 至少领先的指标项数 | `2` |
| `SKILL3_TOP_PERCENTILE` | Skill3 "领先"定义为板块前 X% | `0.5` |
| `SKILL3_MIN_PEERS` | 同板块至少 N 只才进行对比 | `3` |
| `SKILL4_ENABLED` | 是否启用 Skill4 周K线技术筛选 | `True` |
| `SKILL4_MIN_VOL_GROWTH` | Skill4 周成交量同比增幅下限 | `0.70`(即 70%) |
| `SKILL4_MA_PERIODS` | Skill4 多头排列要求的均线周期 | `(5,10,20,30,60)` |
| `EXCLUDE_ST` | 是否排除 ST/*ST | `True` |
| `EXCLUDE_BJ` | 是否排除北交所 | `True` |
| `REQUEST_SLEEP` | 接口调用间隔(防限流) | `0.3 秒` |

## 设计要点与已知行为

- **缓存**:财报、板块映射、股票列表均在 `data/cache/` 落地为 parquet,默认 7 天有效期,大幅减少重复请求。
- **数据源稳定性**:akshare 依赖第三方网站,偶发抓取失败时会跳过该股(日志会有 warning),不会中断流程。
- **小板块行为**:Skill3 在板块成员 < 3 只时跳过该板块对比(避免 "1 只股票自己跟自己比"),阈值可在 config 调整。
- **同比增长率计算**:基于年报值同比上一年(`pct_change`),指标为负值时返回 `NaN`,自动排除该股。
- **毛利率指标**:与 EPS/营收/净利润 一样,看同比增长率(连续两年 ≥ 35%)。akshare 返回的毛利率单位是百分点,同比变化即"毛利率本身的相对变化"。

## 风险与免责声明

- 本项目仅作为**数据分析与学习工具**,不构成投资建议。
- 数据来自公开渠道(akshare 抓取),不保证 100% 准确,重要决策请以官方公告为准。
- 投资决策需自行判断、自负盈亏。

## 后续可扩展方向

- 引入 Tushare Pro 作为财务数据备份源(数据质量更高,需注册积分)
- 增加历史回测:对策略在过去 N 年的表现进行验证
- 添加 ECharts 可视化:K线、资金流向、回测净值曲线
- 自动定时调度:盘后自动运行并通过邮件推送报告
