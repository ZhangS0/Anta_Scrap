# 更新日志

本项目的用户可见变更按版本记录。版本号真源在根目录 `VERSION`（pyproject 动态读取）。
已配置的部署实例用 `python scripts/update.py check` 对比版本、`apply` 快进更新——
`check` 只读可定时跑，`apply` 需人确认；详见 `docs/SCHEDULED_REPORTS.md`「版本更新检查」。

**兼容约定（上游自律，保证各部署实例安全更新）**：

- BI 报表 key 只新增、不改名不删除；
- skill 指引文件只新增、不重命名；
- 🔴 破坏性变更必须在本文件标注并附迁移说明。

影响范围图标：🔴 需重启 MCP 服务端 ｜ 🟡 需用户动作（如重装依赖）｜ 🟢 无感（更新即生效）

## [1.0.0] - 2026-09-23

首个带版本与更新机制的发布（此前变更见 git log）。

- 🟢 新增版本与更新机制：`VERSION` + 本文件 + `scripts/update.py`（check/apply）+ `scripts/check_update.bat`
- 🟢 新增 `scripts/anta_mcp_call.py`：MCP 会话未注册 anta-bi 服务器时的 JSON-RPC 直连通道（仅标准库，端点自动读 `.mcp.json`）
- 🟢 新增 `docs/SCHEDULED_REPORTS.md`：例行/定时报表任务运维手册（5 任务矩阵 + MCP 未注册/Bearer/dws 三类故障 SOP + [补推] 约定）
- 🟢 新增 3 个新报表指引（`anta-bi/references/`）：`sell_through_rate_descente`（售罄率，6 坑）、`ecom_daily_kolon`（电商日报，5 坑）、`new_store_tracking_kolon`（新开店追踪）
- 🟢 字段坑沉淀：迪桑特日报「迪桑特」行=4 子品牌汇总（求和翻倍）、可隆月报品牌大区维度导出 FAILED（线上拆分走 R03）、同店增长基数必须用「同店流水同期」、可隆客流同比命名（`月进店客流同比` 不带"人次"）、DUALIS 系列大写精确匹配等
- 🟢 `bi-report-rerun` 交付自检新增迪桑特日报双筛断言（防漏筛翻倍复发）
- 🔴 `mcp_server.py` 启动校验 `ANTA_MCP_API_KEY`：`${...}` 占位符 / `smenc:` 密文形态**拒绝启动**（提示用 env-manager set_env 存真实 key）。**更新后需重启 MCP 生效**；占位符部署须先存真实 key 再重启
- 🔴 导出任务 FAILED 自动重试 1 次（`export.py:trigger_and_poll`，查询幂等；1004/字段错误等确定性失败不重试）。**需重启 MCP 生效**，对调用方透明
