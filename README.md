# anta-scrap — 安踏 BI Agent 配置项目

一个完整的 agent 配置项目，由三部分组成：

| # | 组成部分 | 位置 | 作用 |
|---|---|---|---|
| ① | **Agent 身份与路由** | `agent_setup/AGENTS.md` | 「BI报告专员」身份 + 全局硬约束 + 任务路由表（很短，全文常驻） |
| ② | **anta-bi MCP 服务器** | `anta_scrap/` 包 | 登录安踏 BI（`datav.anta.com`），按 YAML 模板异步导出 CSV，通过 MCP 对外提供查询 |
| ③ | **配套 skills** | `.claude/skills/` | `anta-bi` 查询、`hamilton-report` 加工、`bi-report-build` 报告构建、`bi-report-rerun` 按计划重跑、`anta-bi-onboard` 新增报表 |

工作流全景：agent 按 ① 的路由表把需求分类（查数 / 建报告 / 重跑 / 新增报表）→ 加载对应 skill
→ 查询走 ② MCP 导出 CSV → 加工与报告按 skill 流程执行 → 资产沉淀到 `workspace/<报告名>_<报告id>/`（模板/plan/DAG 入库，历史生成留档）。

## ① Agent 身份与路由（`agent_setup/`）

`AGENTS.md` 是路由入口（~23 行）：身份一句话、全局硬约束（数据可信原则 / workspace 目录与 run
约定 / 安全 / 反馈义务）、任务路由表。工作流细节全部在 skills 里，按路由按需加载——不占常驻上下文。
另有 `USAGE.md` 使用者日常使用说明；`INIT_PROMPT.md` 安装引导（含密钥，本地不入库）。

## ② anta-bi MCP 服务器（`anta_scrap/` 包）

### 安装

```bash
cd <PROJECT_ROOT>
pip install -e .
```

复制 `.env.example` 为 `.env`，填入账号密码（`ANTA_USERNAME` / `ANTA_PASSWORD`）。
凭证全自动：导出前自动校验（本地过期时间 + 服务端 validate-token），失效时
refresh_token 续期 → 失败则用 `.env` 账号密码完整重登，零人工干预。

### 启动

```bash
anta-mcp --host 0.0.0.0 --port 8002
# 或双击 start_anta_mcp.bat（未设密钥时会交互式提示输入）
```

- 端点：`http://<host>:<port>/mcp`（streamable-http）
- 工具两个：
  - `export_report(username, template_yaml, password="", dom_id="", output_name="")`——
    登录在服务端完成，返回 CSV 全文文本；`password` 仅首次登录/登录失败时传
  - `submit_feedback(username, category, title, body="", context_json="")`——agent 使用
    反馈回传（skill 调用/字段口径/报表要求/问题四类；body 必填一句话摘要，空 body 被拒），
    按天落 `feedback/`（不入库），
    供维护者改进 skills 与字段指引；agent 侧调用约定见 `agent_setup/AGENTS.md` 反馈义务
  - `export_report` 的 `template_yaml` 支持两种报表标识：`report`（内置报表 key）或
    `report_spec` 块（新报表连接 spec，从该报表指引复制）——**新报表接入无需改服务端代码或重启**
- 鉴权：设环境变量 `ANTA_MCP_API_KEY` 后，调用须带 `Authorization: Bearer <key>`；外网暴露必须设并走 HTTPS

### Agent 接入（项目根 `.mcp.json`，已 gitignore）

```json
{
  "mcpServers": {
    "anta-bi": {
      "type": "http",
      "url": "http://<host>:<port>/mcp",
      "headers": { "Authorization": "Bearer ${ANTA_MCP_API_KEY}" }
    }
  }
}
```

### 多用户凭证

- `~/.anta_scrap/credentials.json`：按账号存 JWT（map 格式）
- `~/.anta_scrap/accounts.json`：按账号存密码（明文 0600）
- 首次登录传 `password`，之后日常只传 `username`，服务端自动复用缓存/用已存密码重登

### CLI（仅本地调试）

```bash
anta-cli login                                    # 手动登录（排查登录问题用）
anta-cli export -t retail_daily_descente.default  # 按模板导出 CSV 到 out/
```

### 内网穿透（frp，纯 IP）

本地 8002 → frp tcp 转发 → 公网 8002（纯 IP 只能明文 HTTP；要 HTTPS 需域名 + `type = https`）。
配置样例见 git 历史或向维护者索取。

## ③ 配套 skills（`.claude/skills/`）

- **`anta-bi`**：MCP 工具使用说明 + 6 个报表（迪桑特/可隆 × 零售日报/渠道月报/R03 销存）
  的字段指引（`references/`）+ 指标字典。查询时按路由表选报表、按指引逐字取字段名。
- **`hamilton-report`**：Apache Hamilton DAG 数据加工（清洗 → 聚合 → 指标 → 报告），
  含 quickstart/装饰器/数据IO/坑点参考与模板脚本。
- **`bi-report-build`**：报告构建全流程（需求讨论与口径验证 → 计划与结构确认 → 采集 →
  加工 → 报告 → plan 沉淀），支持从 0 构建与修改/整合。
- **`bi-report-rerun`**：读 `workspace/<报告>/plan.md`，只改参数重跑（异常驱动确认）。
- **`anta-bi-onboard`**：anta-bi 的辅助维护 skill，按用户提供的 HAR/查询参数接入新报表
  （纯文档流程：解析 → 写含「报表连接 spec」的指引 → 冒烟 → 提交；不改服务端、不需重启）。

## 目录地图

| 路径 | 用途 | 入库 |
|---|---|---|
| `agent_setup/` | agent 身份与路由（AGENTS.md）、使用说明（USAGE.md）；INIT_PROMPT.md 本机专用不入库 | ✅ |
| `anta_scrap/` | MCP 服务器 + 抓取库代码 | ✅ |
| `.claude/skills/` | 配套 skills（5 个） | ✅ |
| `workspace/<报告名>_<报告id>/` | 报告任务全家桶：templates/ 查询模板、plan.md、analysis.py、history/ 历史生成 | 资产✅ / history❌ |
| `templates/*.default.yaml` / `*.reference.yaml` | 库级查询模板 / 全字段参考模板（报表注册体系，onboard 维护） | ✅ |
| `captures/` | BI 查询过程留档：HAR、请求负载 txt、指标说明 xlsx（字段/接口 truth 来源；`*.har` 不入库） | 部分 |
| `docs/` | 机制文档（页面发现等） | ✅ |
| `scripts/` | 登录、页面收集、多用户验证脚本 | ✅ |
| `out/` | CLI 默认导出的临时目录 | ❌ |
| `feedback/` | agent 回传的使用反馈（submit_feedback 按天 JSONL） | ❌ |
| `.env`、`.mcp.json`、`~/.anta_scrap/` | 凭证与密钥 | ❌ |

`<报告id>` 为创建时分配的 4 位随机 id，永久不变；`<run>` 为批次号 `YYYYMMDD-HHMM`，
每次生成报告新建一个，禁止覆盖历史 run。

## 模板

`templates/*.yaml` 是可读的查询配置，修改字段/条件/日期无需改代码：

```yaml
report: retail_daily_descente
rows: [渠道品牌]
metrics: [零售流水目标]
filters:
  - { name: 渠道品牌, values: [DESCENTE] }
dynamic_params:
  开始日期-户外-R02: 2026-07-22
  结束日期-户外-R02: 2026-07-29
limit: 50
```

- `*.default.yaml`：各报表默认查询；`*.reference.yaml`：全字段参考（注释态，含 fdId）
- 报告任务的工作流模板在 `workspace/<报告名>_<报告id>/templates/`（如
  `workspace/kolon_recent_sales_3t4g/templates/daily.yaml`），随该报告的 plan/脚本同目录管理

## 新增报表

**标准路径（纯文档，推荐）**：MCP 是通用执行器——用 `anta-bi-onboard` skill 产出含
「报表连接 spec」小节的字段指引（+可选 `templates/specs/<key>.har_fields.json` 字段数据文件），
调用方模板内联 `report_spec` 块即可查询。**不改服务端代码、不需重启。**

内置路径（仅维护既有 6 报表子类时）：写 `reports/<name>.py` 子类 →
`config.py:get_report_registry()` 注册 → 加 `templates/<name>.default.yaml` → 加字段指引；
改动需部署重启生效。详见 `CLAUDE.md` 的「新增报表两条路径」与「关键约定」。
