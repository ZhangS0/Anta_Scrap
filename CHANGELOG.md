# 更新日志

本项目的用户可见变更按版本记录。版本号真源在根目录 `VERSION`（pyproject 动态读取）。
已配置的部署实例用 `python scripts/update.py check` 对比版本、`apply` 快进更新——
`check` 只读可定时跑，`apply` 需人确认；详见 `docs/SCHEDULED_REPORTS.md`「版本更新检查」。

**兼容约定（上游自律，保证各部署实例安全更新）**：

- BI 报表 key 只新增、不改名不删除；
- skill 指引文件只新增、不重命名；
- 🔴 破坏性变更必须在本文件标注并附迁移说明。

影响范围图标：🔴 需重启 MCP 服务端 ｜ 🟡 需用户动作（如重装依赖）｜ 🟢 无感（更新即生效）

## [1.2.1] - 2026-09-24

- 🟡 **新增存量实例升级引导 `agent_setup/UPGRADE_PROMPT.md`**：早期配置的实例没有
  update_agent.py（无法自助更新），项目所有者把该文件发给存量 agent 按步执行一次
  （浅克隆→合并覆盖→写版本标记），即升级到最新并**获得自助更新能力，此后不再需要**。
  含升级前自查（自加报表指引会保留；改过 SKILL.md/AGENTS/USAGE 的先自行备份——本次
  无基线不自动备份）。已用 v1.0.0 旧布局模拟实例全链路验证（自加报表/产物保留、
  升级后 check 显示已是最新）

## [1.2.0] - 2026-09-24

自加报表（anta-bi-onboard 产出）在更新下的零丢失保障：

- 🟢 **根治路由入口丢失**：onboard 流程不再修改 anta-bi SKILL.md 路由表（上游分发文件，
  更新会被整文件覆盖）——改为 SKILL.md 新增「自加报表通用发现规则」：`references/` 下凡含
  「报表连接 spec」小节的 md 都是可查报表，按文件名路由。接入新报表 = 只新增一个文件，
  结构上不可能被更新丢失；存量已被覆盖丢失路由行的孤儿指引同样由此救活
- 🟢 **update_agent.py 新增本地修改备份**（基线快照机制）：每次 apply 后记录全部安装文件
  sha256 到 `.magic/update-baseline.json`；下次 apply 时本地 hash ≠ 基线 = 用户改过该文件
  → 覆盖前自动备份到 `.magic/update-backup/<旧版本>_<时间戳>/` 并列出，供手动合并改动。
  覆盖 SKILL.md/AGENTS.md/USAGE.md 等一切分发文件的本地定制
- 🟡 存量实例注意：首次跑新版 apply 时没有基线，**无法检测/备份此前做过的本地修改**（只建立
  基线，之后才有保护）——若你在 SKILL.md/AGENTS.md 里加过路由行或定制规则，第一次更新前
  自行留一份副本；自加报表指引是新增文件，不受此限制

## [1.1.0] - 2026-09-24

使用端视角整备：使用端 = 按 INIT_PROMPT 配置的其他 AI agent（浅克隆后只装五个 skill +
AGENTS/USAGE 到 `.magic/skills/`，纯 MCP 客户端，无 scripts/docs/.git）。

- 🟢 **直连逃生通道首次真正可达使用端**：`anta_mcp_call.py` 移入 anta-bi skill（`scripts/`）随分发；
  端点探测改为从 agent 项目根向上找 `.mcp.json`，兜底默认部署端点
- 🟢 **新增使用端更新器** `anta-bi/scripts/update_agent.py`（check/apply）：临时浅克隆通道对比
  版本标记；apply 白名单覆盖五个 skill + AGENTS/USAGE，**保护性覆盖**（上游已删而你自加的
  报表指引/skill 保留并列出）；workspace/、out/、feedback-pending.jsonl、.mcp.json、凭证零触碰
- 🟢 INIT_PROMPT 配置完成即写入版本标记（`.magic/skills/anta-bi/VERSION`）
- 🟢 SKILL.md 第 0 步直连路径与 1004/行级权限排错处置改为使用端可达口径（权限矩阵向项目所有者确认）
- 🟢 AGENTS.md 新增「工具版本与更新」小节；USAGE.md「九、版本与更新」改使用端命令
- 🟢 部署形态定位写入 CLAUDE.md（服务端部署源 + 使用端分发源两重身份，功能必须随 skill 分发）
- 🟡 **存量已配置实例**：拿不到新 INIT_PROMPT（它不入 git）——由项目所有者重新分发一次
  INIT_PROMPT，或在使用端手动 `git clone --depth 1` 拷一次 `.claude/skills/anta-bi/scripts/`
  到 `.magic/skills/anta-bi/scripts/` 并写入 VERSION 标记；之后即可自助 check/apply
- 🔴 无服务端代码变更，无需重启 MCP

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
