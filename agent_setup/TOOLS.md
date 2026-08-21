---
tools:
  - list_dir
  - file_search
  - read_files
  - grep_search
  - shell_exec
  - write_file
  - edit_file
  - edit_file_range
  - multi_edit_file
  - append_to_file
  - delete_files
  - run_python_snippet
  - run_sdk_snippet
  - query_magicbase_rows
  - query_magicbase_tables
  - read_webpages_as_markdown
  - web_search
  - visual_understanding
  - call_subagent
  - wait_for_subagents
---

## 工具使用偏好

- 数据加工与初级报告优先使用 `hamilton-report` skill（Hamilton DAG：清洗 → 聚合 → 指标 → Markdown 报告），按其流程执行；`run_python_snippet` 仅用于临时数据探查与小规模验证。
- **执行环境自检**：shell 在 **Linux 沙盒**中运行，而 skill 示例兼顾 Windows 本机——执行 skill 命令前先按其「环境引导」探测解释器（`$PY`，Linux 用 `.venv/bin/python`，Windows 用 `.venv/Scripts/python.exe`），venv 不存在就先 `python3 -m venv .venv` 并装依赖；不要照抄带 `.exe` 的路径。
- 从安踏 BI 查询数据时，加载 `anta-bi` skill，按其流程执行（报表路由 → 编制 YAML 模板 → MCP 工具 `export_report` → 解析 CSV 结果），不在本文件重复技能细节。
- 查询返回的 CSV 一律落盘到 `out/<报告名>/<run>/` 目录供 DAG 读取（目录规划见 AGENTS.md），不整读进上下文（用 `head -2` 看表头即可）。
- BI 查询模板是复用资产：正式任务的模板保存到 `templates/<报告名>/`，重复执行只改参数不重编；临时探查才用内联 YAML。
- 读取 Excel/CSV 等数据文件时，先用 `read_files` 读取前若干行了解结构，再用脚本处理。
- 数据文件格式无法直接读取（如 PDF、部分格式）时，先调用 `document-converter` 技能转换。
- 报告可视化优先使用 ECharts（嵌入 HTML 报告），Python 仅用于计算，不用于绘图。
- 文件查找优先使用 `grep_search` 定位内容，`file_search` 定位路径。
- 多子报告任务：用 `call_subagent` 把每个子报告的「采集 → 加工 → 基础报告」委派给子 agent 并行执行，用 `wait_for_subagents` 等待完成并收集结果；委派的任务说明必须自包含（数据需求、加工需求、产出路径、数据可信约束）。
