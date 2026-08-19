---
name: hamilton-report
description: 用 Apache Hamilton 数据流（DAG）对 CSV 数据做清洗、汇总、指标计算并生成分析报告（Markdown/Excel）。当用户要做数据分析、批量算指标、生成经营/零售分析报告，或要求用 Hamilton/数据管道/DAG 组织计算时使用。默认数据源是 out/ 下安踏 BI 导出的 CSV（由 anta-bi skill 获取），也适用于任意 CSV。
allowed-tools: Read, Grep, Glob, Bash(./.venv/bin/python:*), Bash(./.venv/Scripts/python.exe:*), Bash(./.venv/Scripts/anta-cli.exe:*), Bash(python3:*)
---

# hamilton-report：Hamilton 数据分析报告

用 [Apache Hamilton](https://github.com/apache/hamilton) 把「清洗 → 聚合 → 指标 → 报告」组织成 DAG：
函数即节点、按名自动连线、只算所请求的子图。通用能力，默认场景是本项目 BI 导出 CSV。

**边界**：BI 怎么查询、字段什么含义，归 `anta-bi` skill（`.claude/skills/anta-bi/`）；
本 skill 只负责 Hamilton 数据流与报告产出，不重复字段字典。

## 环境引导（首次使用必做）

依赖不预装、不改 pyproject，按需装进项目 `.venv`。
运行环境可能是 Windows 本机或 **Linux 沙盒**，venv 解释器路径不同，先探测再统一用 `$PY`：

```bash
# 项目根目录执行（bash；Linux 下 venv 是 .venv/bin/python，Windows 是 .venv/Scripts/python.exe）
[ -x .venv/bin/python ] || [ -x .venv/Scripts/python.exe ] || python3 -m venv .venv
[ -x .venv/bin/python ] && PY=.venv/bin/python || PY=.venv/Scripts/python.exe
$PY -m pip install apache-hamilton pandas openpyxl
# 包名是 apache-hamilton；sf-hamilton 是旧名，别装错
# 验证：
$PY -c "import hamilton, pandas; print(hamilton.__version__, pandas.__version__)"
# 可选（DAG 出图，需系统 Graphviz，未装就跳过，不影响其他功能）：
# $PY -m pip install "apache-hamilton[visualization]"
# 已验证: apache-hamilton 1.90.0 + pandas 3.0.5 + openpyxl 3.1.5 @ Python 3.13.7（2026-08-16, Windows）
```

## 参考路由（按需只读一个）

| 需求 | 指引 |
|---|---|
| 第一次写 Hamilton DAG / 核心模型（函数=节点、Driver、execute） | `references/quickstart.md` |
| 节点参数化/按配置切换/输出校验（@parameterize、@config.when、@check_output…） | `references/decorators.md` |
| CSV 读入清洗、结果落盘、Markdown/Excel 报告与目录约定 | `references/data-io.md` |
| 报错排查：编码、中文列名、Windows 路径、BI CSV 数字格式、校验器报错 | `references/pitfalls.md` |
| BI 字段含义 / 如何导出新 CSV | 不在本 skill：用 `anta-bi` skill（其指标字典只 Grep） |

## 最小工作流（5 步）

1. **取数**：`out/` 已有 CSV 直接用；或调 anta-bi MCP `export_report`，把返回的 CSV 全文
   存到 `out/<名>.csv`（量大时建 `templates/<名>.yaml` 走 `anta-cli export` 直落盘）。
   动手前 `head -2` 确认表头。
2. **设计（DOT 先行）**：先用几行 DOT 画出节点与依赖（运行时输入标 `[shape=box]`），
   确认结构再动代码——写法见 `references/quickstart.md`。
3. **起草与验证**：复制 `scripts/kolon_report.py` 到 `analysis/<报告名>.py`，把 DOT 翻译成
   函数签名，先跑 `--list-nodes`（只 build 不执行）验证依赖接线，通过后再填函数体。
4. **运行**：未装依赖先按上节安装；`PYTHONIOENCODING=utf-8 $PY
   analysis/<报告名>.py`（`$PY` 按上节探测；报错先读 `references/pitfalls.md` 再改）。
5. **产物**：报告写 `reports/`，向用户呈现关键结论；数据量大时先汇总再展示。

## 可运行示例（自检 / 模板）

`scripts/kolon_report.py` 读 `out/kolon_daily*.csv`（默认最新，可 `--csv` 指定）→
清洗 → 日汇总/区域汇总/门店 Top10 → 总体达成率 → 写 `reports/kolon_report.md`：

```bash
[ -x .venv/bin/python ] && PY=.venv/bin/python || PY=.venv/Scripts/python.exe
PYTHONIOENCODING=utf-8 $PY .claude/skills/hamilton-report/scripts/kolon_report.py
$PY .claude/skills/hamilton-report/scripts/kolon_report.py --list-nodes
```

正常输出：日期区间 2026-07-22~07-29、流水合计 99,588,943.9、达成率约 102.5%、
区域汇总表 + Top10 表。跑不通说明环境坏了，先修环境再做分析。

## 上下文纪律（重要）

- 只 Read 当前需要的 **1 个** reference，禁止全读后再动手；`pitfalls.md` 仅在报错或
  处理中文列/编码问题时读。
- `out/` 下 CSV（100~300KB）**禁止整读进上下文**：用 `head -2` 看表头，数据交给 DAG 节点算。
- 字段/指标知识一律走 anta-bi skill，本 skill 不复制字段清单。
- DAG 代码放 `analysis/`（入库）；报告产物放 `reports/`（已 gitignore）。

## 备注

进阶场景（Spark/Ray 并行、LLM/RAG 工作流、Hamilton UI 追踪、Airflow/FastAPI 集成）
参考 apache/hamilton 官方插件（仓库 `.claude-plugin/`，7 个专项 skill），超出本 skill
的 BI 报告场景，不在此展开。
