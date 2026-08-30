# anta-scrap — 安踏 BI Agent 配置项目

一个完整的 agent 配置项目，由三部分组成：

| # | 组成部分 | 位置 | 作用 |
|---|---|---|---|
| ① | **Agent 身份与工作流** | `agent_setup/AGENTS.md` | 「BI报告专员」角色定义 + 「BI 查询 → 数据加工 → 报告生成」完整工作流规范 |
| ② | **anta-bi MCP 服务器** | `anta_scrap/` 包 | 登录安踏 BI（`datav.anta.com`），按 YAML 模板异步导出 CSV，通过 MCP 对外提供查询 |
| ③ | **配套 skills** | `.claude/skills/` | `anta-bi`（报表路由 + 字段指引）、`hamilton-report`（Hamilton DAG 数据加工与报告生成） |

工作流全景：agent 按 ① 的身份与流程接需求 → `anta-bi` skill 路由报表、编制模板 → ② MCP 服务器执行查询导出 CSV → `hamilton-report` skill 加工数据、生成报告 → 沉淀模板/DAG/plan 供复用。

## ① Agent 身份与工作流（`agent_setup/`）

`AGENTS.md` 是 agent 的主提示：角色（BI报告专员）、数据可信原则、项目目录规划、
需求讨论 → 采集 → 加工 → 报告 → plan 沉淀的五步工作流与决策逻辑。

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
- 唯一工具：`export_report(username, template_yaml, password="", dom_id="", output_name="")`，
  登录在服务端完成，返回 CSV 全文文本；`password` 仅首次登录/登录失败时传
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

## 目录地图

| 路径 | 用途 | 入库 |
|---|---|---|
| `agent_setup/` | agent 身份与工作流 | ✅ |
| `anta_scrap/` | MCP 服务器 + 抓取库代码 | ✅ |
| `.claude/skills/` | 配套 skills | ✅ |
| `templates/*.default.yaml` / `*.reference.yaml` | 库级查询模板 / 全字段参考模板 | ✅ |
| `templates/<报告名>/` | 工作流查询模板（跨批次复用） | ✅ |
| `analysis/` | Hamilton DAG 代码 | ✅ |
| `plans/` | 可复用工作流 plan | ✅ |
| `captures/` | BI 查询过程留档：HAR、请求负载 txt、指标说明 xlsx（字段/接口 truth 来源；`*.har` 不入库） | 部分 |
| `docs/` | 机制文档（页面发现等） | ✅ |
| `scripts/` | 登录、页面收集、多用户验证脚本 | ✅ |
| `out/<报告名>/<run>/` | 本批次原始 CSV 产物 | ❌ |
| `reports/<报告名>/<run>/` | 本批次报告产物 | ❌ |
| `.env`、`.mcp.json`、`~/.anta_scrap/` | 凭证与密钥 | ❌ |

`<run>` 为批次号 `YYYYMMDD-HHMM`，每次生成报告新建一个，禁止覆盖历史 run。

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
- 工作流模板放 `templates/<报告名>/<模板名>.yaml`（如 `templates/kolon_recent_sales/daily.yaml`）

## 新增报表（改 `anta_scrap/` 时）

1. `anta_scrap/reports/<name>.py` 新建 `XxxReport(BaseReport)`（page_id / card_id / name / default_ds_id / DYNAMIC_PARAMS / FIELD_SOURCE_CDID / default_template()）
2. `anta_scrap/config.py:get_report_registry()` 注册
3. 加 `templates/<name>.default.yaml`
4. `.claude/skills/anta-bi/references/` 加字段指引

详见 `CLAUDE.md` 的「关键约定（踩坑总结）」。
