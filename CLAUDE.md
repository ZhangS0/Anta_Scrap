# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

本项目是**完整的 agent 配置项目**，由三部分组成：

1. **Agent 身份定义与功能描述** — `agent_setup/AGENTS.md`：「BI报告专员」身份 + 全局硬约束 + 任务路由表（~23 行，常驻；流程细节全在 skills）。配套 `agent_setup/USAGE.md`（使用者日常说明）与 `INIT_PROMPT.md`（安装引导，本地不入库）。
2. **anta-bi MCP 服务器** — `anta_scrap/` 包（`anta-mcp` 入口）：登录安踏 BI（`datav.anta.com`），按 YAML 模板异步导出 CSV，通过 MCP 对外提供查询；`anta-cli` 仅本地调试。
3. **配套 skills** — `.claude/skills/` 五个：`anta-bi`（报表查询与字段指引）、`hamilton-report`（Hamilton DAG 数据加工）、`bi-report-build`（报告构建全流程）、`bi-report-rerun`（按 plan 参数化重跑）、`anta-bi-onboard`（为 anta-bi 新增报表，维护用）。任务路由入口在 `agent_setup/AGENTS.md`。

面向使用者的说明在 `README.md`；本文件面向在本仓库写代码的场景。

报表矩阵：迪桑特(DESCENTE) / 可隆(KOLON) 两品牌 × 三类报表，共 6 个 registry key（`config.py:get_report_registry()`）：

| registry key | 品牌 | BI 报表 |
|---|---|---|
| `retail_daily_descente` | 迪桑特 | 零售运营分析-日报 |
| `retail_daily_kolon` | 可隆 | 零售运营分析-日报 |
| `channel_monthly_descente` | 迪桑特 | 渠道运营分析-月报 |
| `channel_monthly_kolon` | 可隆 | 渠道运营分析-月报 |
| `r03_sales_stock_descente` | 迪桑特 | R03-任意时间段销存结构分析 |
| `r03_sales_stock_kolon` | 可隆 | R03-任意时间段销存结构分析 |

每个报表的字段清单与查询指引在 `anta-bi` skill（`.claude/skills/anta-bi/references/`，每报表一个 md + `metrics-glossary.md` 指标字典）；MCP 不携带字段知识，由调用方 skill 提供。

## MCP 服务（对外查询主入口）

- **启动**：`anta-mcp --host 0.0.0.0 --port 8000`（streamable-http，端点 `/mcp`；默认端口 8000，可用 `MCP_HTTP_PORT` 覆盖。本地部署用 `start_anta_mcp.bat`，跑在 **8002**）。常驻供 agent 调用。
- **两工具**：
  - `export_report(username, template_yaml, password="", dom_id="", output_name="")`：登录在服务端完成，返回 CSV 全文文本。`password` 仅首次登录/登录失败时传，日常只传 `username`。
  - `submit_feedback(username, category, title, body="", context_json="")`：agent 使用反馈回传（category 白名单 `skill_call`/`field_note`/`report_note`/`issue`；body 32k 截断；写入前按 accounts.json 脱敏密码）。按天追加到项目 `feedback/YYYY-MM-DD.jsonl`（gitignore），供维护者改进 skills 与字段指引；调用约定写在 AGENTS.md「反馈义务」与各 skill 检查点。
- **接入**：`claude mcp add --transport http anta-bi http://<host>:<port>/mcp`（或项目 `.mcp.json`，已 gitignore）。
- **鉴权**：外网暴露须设 `ANTA_MCP_API_KEY`（调用带 `Authorization: Bearer <key>`）并走 HTTPS。
- **多用户凭证**：`~/.anta_scrap/credentials.json`（按账号存 JWT，map 格式）+ `~/.anta_scrap/accounts.json`（按账号存密码，明文 0600）。`auth/session.py:resolve_credentials()` 负责缓存优先/失效重登，MCP 路径用它；CLI 路径用 `AntaSession.ensure()`。

## 常用命令

```bash
# 安装（开发模式，editable）
pip install -e .

# 登录（写凭证到 ~/.anta_scrap/credentials.json）
python scripts/anta_login.py
# 或
anta-cli login

# 导出 CSV（report 可省略，默认取模板里的 report 字段）
anta-cli export -t retail_daily_descente.default
anta-cli export -t retail_daily_kolon.default --name kolon_daily
# 不带 -t 时默认模板 retail_daily_descente.default
```

无单元测试套件；验证方式是跑 CLI/MCP 看真实接口返回。`captures/` 目录存 BI 查询过程留档（HAR 抓包、请求负载 txt、指标说明 xlsx；`*.har` 不进库），是字段/接口行为的验证 truth 来源。

项目自带 `.venv`（Python 3.13）已 editable 安装本包。PowerShell 里先激活：`.\.venv\Scripts\Activate.ps1`，激活后 `anta-cli`/`anta-mcp` 直接可用（或用完整路径 `.\.venv\Scripts\anta-cli.exe`）。

## 架构（按调用顺序）

```
CLI (cli.py): AntaSession.ensure() → cls(client)                # 用类上的 page_id
MCP (mcp_server.py): resolve_credentials(username) → create_report_instance(name, client, username)
  ↓
BaseReport.effective_page_id  ← auth/page_discovery.py          # 多用户页面自动发现（仅 MCP 路径带 username）
  ↓
Report.fetch_meta() → /api/page/{page_id} → _index_fields()     # 字段名 → fdId
  ↓
templates.py:template_to_params（YAML → QueryParams，report.field() 解析）
  ↓
export.py: trigger_export → poll_task → download                # 异步导出三步走
```

**模块边界**：
- `auth/` 不依赖任何报表概念；只负责 CAS+OAuth2 登录、凭证持久化、Session、页面发现。
- `client.py` 不依赖任何报表；只负责带 header 的 HTTP 原语。
- `reports/base.py:BaseReport` 是抽象基类；`reports/<name>.py` 子类提供 `page_id`/`card_id`/`name`/`default_ds_id`/`DYNAMIC_PARAMS`/`FIELD_SOURCE_CDID`/`default_template()`。
- `export.py` / `templates.py` 都接受 `BaseReport` 实例，不感知具体报表。

**新增报表 4 步**：写 `reports/<name>.py` 子类 → 在 `config.py:get_report_registry()` 注册 → 加 `templates/<name>.default.yaml` → 在 `.claude/skills/anta-bi/references/` 加字段指引。若报表字段多/同名冲突风险高（R03、渠道月报 KOLON 都这么做了），从 HAR 抠出完整配置态字段存 `reports/<name>_har_fields.json` 并重写 `_index_fields()`。

## 报表子类的固定结构（抄现有子类）

- `FIELD_SOURCE_CDID`：filter 字段名 → 选择器卡片 ID（硬编码，从 HAR 抓）。
- `DYNAMIC_PARAMS`：动态参数名 → `{dpId, valueType, sourceCdId}`（硬编码，从 HAR 抓）。
- `_filter(name, values)` / `_dp(name, value)` helper：构造时自动注入 sourceCdId。
- `_index_fields()` 覆盖（可选）：先 `super()._index_fields()`，再以 `<name>_har_fields.json` 的字段为最高优先重建索引。页面字段池同名冲突风险高时必须这么做。

## 关键约定（踩坑总结，改 BI 相关代码必读）

### 1. 凭证 header 必须是 Base64 形态
- `token` = JWT 字符串（原样）
- `user-id` = `base64(username)`，如 `V0VCVVNFUg====`
- `x-dom-id` = `base64(明文)`，如 `Z3VhbmJp`（明文是 `guanbi`，**不能**直接发明文）
- 全部在 `auth/token_store.py:Credentials` 里保存，`client.py:_auth_headers()` 注入

### 2. 所有 `/api/*` 请求必须带 referer 防 CSRF
`client.py:_request()` 已自动注入 `referer: https://datav.anta.com/page/{page_id}`（通过 `_infer_page_id` 从 path 抠 `ne...` 前缀）。如果调的 API 不在 `/api/page/...` 路径上，**必须显式传 referer**：

```python
client.get_json("/api/some/path", headers={"referer": f"https://datav.anta.com/page/{rpt.page_id}"})
```

### 3. 字段元数据多源策略（reports/base.py:_index_fields）
字段定义来源，**优先级从高到低**：
1. 子类重写 `_index_fields()` 注入的 `<name>_har_fields.json`（HAR 抓的完整配置态，r03×2、channel_monthly_kolon 在用）
2. `cards[].content.meta.chartMain.zoneData.{row,column,metric}` —— 页面已配置态，含 `calculationType`/`isAggregated`/`fieldFormat` 等 metric 必备属性
3. `dsInfos[*].columns` —— 数据集字段池，回退用

**为什么**：从字段池取的 metric item 缺 `fieldFormat`，BI 后端会报 `卡片查询错误，错误详情: None.get`（5001）。配置态的 metric 必须透传 raw（`FieldDef.raw`），不能精简。

### 4. 重名字段与多数据集
同一字段名（如"渠道品牌"）在不同数据集里 fdId 不同。子类用 `default_ds_id` 指定首选数据集；`field(name, ds_id=...)` 可显式选。`_fields_by_name_and_ds` 是完整索引。

### 5. filter 和 dynamicParams 的 sourceCdId
`sourceCdId`（选择器/控件卡片 ID）**不在页面元数据里**，要硬编码到子类的 `FIELD_SOURCE_CDID` / `DYNAMIC_PARAMS`。`templates.py:template_to_params` 会按这两个映射自动注入；缺了会 None.get 报错。新增报表时从留档（`captures/*.har` 或请求负载 txt）抓这两组 ID 复制过来。

### 6. 响应结构有三种形态（client.py:_check_ok）
`_check_ok` 必须全兼容：
- 标准：`{result: "ok", response: {...}}`
- 任务接口带 raw-backend-response：`{result: "ok", response: {status, ...}}`
- 任务接口裸：`{taskId, status, result: {success, exportPath}}`（顶层无 result 字段或 result 是 dict）

`raw-backend-response: TRUE` 请求头会让服务端返回"包装态"，否则是"裸态"——同一个 `/api/task/{id}` 接口两种响应。

### 7. 异步导出三步走（export.py）
```
POST /api/write/file/{card_id}?typeOp=CSV   → {taskId}（可能包在 response 里）
GET  /api/task/{taskId}                     → {status: PROCESSING|SUCCESS|FAILED}
POST /api/export/file/common/{taskId}       → 二进制流（body 带 downloadFileName/time）
```
- 只走 CSV（`PIVOT` = Excel 通道已不用）
- 轮询响应在裸态时 `status` 在顶层，包装态时在 `response.status`，`poll_task` 两种都兼容
- 文件名从 `content-disposition` 解析（RFC 5987 `filename*` 优先）；Windows 落盘前用 `re.sub(r'[\\/:*?"<>|]', "_", name)` 替换非法字符

### 8. JWT 14 天有效期 + 全自动凭证恢复
登录后 `exp` 是签发时间 +14 天（1209600 秒）。`auth/login.py:_decode_jwt_exp` 从 JWT payload 解出 `exp` 存入 `Credentials.expires_at`。

`AntaSession.ensure()`（每次 CLI 调用入口）自动校验并恢复凭证，**无需人工重登**：
1. 校验两个维度：本地 `expires_at` + 服务端 `/api/validate-token`（会话可能被顶号/登出提前作废）
2. 任一失效 → 先 `refresh_credentials()`（CAS 标准 `POST /oauth2.0/token`，未经成功样本验证）
3. refresh 失败 → 用 `.env` 的 `ANTA_USERNAME/ANTA_PASSWORD/ANTA_DOM_ID` 走完整 `login()` 自动重登（2026-08 实测成功）
4. 都失败才抛 `SessionExpired`（如密码已改、触发验证码）

前提：`.env` 里配置了账号密码（`config.py` 启动时加载）。MCP 多用户路径的等价逻辑在 `resolve_credentials()`：该账号缓存 JWT 有效直接用；失效则用「本次传入或 accounts.json 已存」的密码重登。

### 9. 登录链路（auth/login.py，2026-08 实测）
**必须从 datav 侧发起**，不能用硬编码 state 从 CAS 侧发起（state 内嵌 datav 生成的 token，`authenticate` 端点会校验，伪造 state 会 500 `Error processing async result`）：
```
GET  datav /standard-oauth2/authenticate（无 code）
  → 303 CAS /oauth2.0/authorize?...&state=<datav 生成>  → 302 CAS 登录页
POST 表单（username/password/execution/loginTraceId/...）
  → callbackAuthorize → authorize → datav authenticate?code=...（303）
  → datav.anta.com/?access_token=AT-xxx&refresh_token=RT-xxx
GET  该 URL → set-cookie: uIdToken=<JWT>（httponly）
```
全程单一 httpx Client 共享 cookie（CAS 的 TGC 会话）。JWT 在 cookie `uIdToken` 里，不在 HTML 或响应体。`loginTraceId` 抓不到时用随机 32 位 hex 兜底；`execution` 抓不到时用 `e1s1` 兜底。

### 10. 多用户页面自动发现（auth/page_discovery.py）
不同用户可能被分配到同一报表的不同页面实例。MCP 路径经 `create_report_instance(name, client, username=...)` → `BaseReport.effective_page_id` → `PageDiscoveryService`：查缓存（`~/user_page_mappings.json`）→ 拉服务端用户页面列表逐个验证 → 试子类 `candidate_page_ids` → 兜底用默认 `page_id`。CLI 路径不传 username，直接用类上的 `page_id`。新用户报"无权访问"时：跑 `python scripts/collect_user_pages.py <工号>` 收集其页面，必要时加进子类 `candidate_page_ids`；详见 `docs/PAGE_DISCOVERY.md`。

## 模板系统（templates/）

YAML 模板里只写**可读字段名**（中文），运行时通过 `report.field(name)` 解析为 fdId。`templates.py:template_to_params` 把 YAML → `QueryParams` 对象。

```yaml
report: retail_daily_kolon
rows: [渠道品牌, 店铺名称]
metrics: [零售流水目标, 流水]
filters:
  - { name: 渠道品牌, values: [KOLON] }
dynamic_params:
  开始日期-户外-R02: 2026-07-22   # YAML 会解析成 date，templates.py 内部转回字符串
limit: 50
# card_name: 自定义导出文件名（缺省用报表 name）
```

注意：`find_template` 只在 `templates/` 根目录按文件名找；workspace 报告目录下的模板（见下节）要用 `load_template` 传绝对路径。

## 报表工作流目录约定（workspace/）

报告任务的资产与产物统一收纳在 `workspace/<报告名>_<报告id>/`（agent 侧工作流规范见 `agent_setup/AGENTS.md` 路由 + 各 `bi-report-*` skill）：

```
workspace/<报告名>_<报告id>/       # 一报告任务一目录（报告id=4位随机，创建后不变）
├── templates/                     # 该报告的查询模板（跨 run 复用，入库）
├── plan.md                        # 工作流 plan：参数表/资产路径/自检清单（入库）
├── analysis.py                    # Hamilton DAG 脚本（入库）
└── history/<run>/                 # 历史生成：CSV + 报告产物（gitignore）
```

- `<run>` 为批次号 `YYYYMMDD-HHMM`，只新建不覆盖。
- **两级分工**：本目录放报告任务资产；根 `templates/` 放库级模板（`*.default.yaml`/`*.reference.yaml`，属于报表注册体系，由 `anta-bi-onboard` skill 维护）。
- `captures/` 存 BI 查询过程留档（HAR/请求负载/指标说明，truth 来源）；`out/` 仅作 CLI 默认导出的临时目录；`feedback/` 存 agent 回传的使用反馈（submit_feedback 落盘，gitignore）。


## 已知遗留问题

- **refresh 续期路径未验证**：`refresh_credentials()` 走 CAS 标准 `POST /oauth2.0/token`，未拿到成功样本（活 refresh_token 尚未经历过到期）。不重要：失败会自动落到完整重登（已实测成功）。
- **会话中途凭证失效不自动恢复**：校验/恢复只在 `ensure()`/`resolve_credentials()` 入口；单次导出任务进行中被服务端作废（error_code 1018）会直接抛 `AntaAPIError`，重跑命令即可自动恢复。
- **KOLON 报表静默丢指标**：选了该卡片不支持的指标时服务端不报错、只在 CSV 表头里缺列；核对返回表头与请求 metrics 一致（详见各 skill reference 的「已知缺陷」）。
