# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

`anta-scrap` 是安踏 BI（`datav.anta.com`）的数据抓取库，可导入使用；也提供 **MCP 服务**（`anta-mcp`，对外 agent 调用）和 `anta-cli` 命令行（仅本地调试）。首个报表：零售运营分析-日报（page `ne63f6cf08bbb40c28b814e8` / card `q72769bce32b04f91873eeee`）。

## MCP 服务（对外查询主入口）

- **启动**：`anta-mcp --host 0.0.0.0 --port 8000`（streamable-http，端点 `/mcp`），常驻供 agent 调用。
- **唯一工具** `export_report(username, template_yaml, password="", dom_id="", output_name="")`：登录在服务端完成，返回 CSV 全文文本。`password` 仅首次登录/登录失败时传，日常只传 `username`。
- **接入**：`claude mcp add --transport http anta-bi http://<host>/mcp`（或项目 `.mcp.json`）。
- **鉴权**：外网暴露须设 `ANTA_MCP_API_KEY`（调用带 `Authorization: Bearer <key>`）并走 HTTPS。
- **多用户凭证**：`~/.anta_scrap/credentials.json`（按账号存 JWT，map 格式）+ `~/.anta_scrap/accounts.json`（按账号存密码，明文 0600）。`anta_scrap.auth.session.resolve_credentials()` 负责缓存优先/失效重登。
- 报表与字段说明在 `anta-bi` skill（`.claude/skills/anta-bi/`）的 references/ 里，MCP 不携带字段知识。

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

# 注意：项目自带的 .venv（Python 3.13）已 editable 安装本包。PowerShell 里先激活：
#   .\.venv\Scripts\Activate.ps1
# 激活后 anta-cli 直接可用；或用完整路径 .\.venv\Scripts\anta-cli.exe <cmd>
```

无单元测试套件；验证方式是跑 CLI 看真实接口返回（HAR 文件 `datav.anta.com.har` 是验证 truth 的来源，20MB 不进库）。

## 架构（按调用顺序）

```
CLI (cli.py) / scripts/anta_login.py
  ↓
AntaSession.ensure()  ← auth/session.py（加载 ~/.anta_scrap/credentials.json）
  ↓
AntaClient (client.py)  ← httpx 封装，自动注入 token/user-id/x-dom-id/referer
  ↓
Report (reports/base.py + reports/<name>.py)  ← 报表逻辑，每个报表一个子类
  ↓
BI API
```

**模块边界**：
- `auth/` 不依赖任何报表概念；只负责 CAS+OAuth2 登录、凭证持久化、Session（含导出前的凭证校验/续期）。
- `client.py` 不依赖任何报表；只负责带 header 的 HTTP 原语。
- `reports/base.py:BaseReport` 是抽象基类；`reports/<name>.py` 子类提供 `page_id`/`card_id`/`default_template()`。
- `export.py` / `templates.py` 都接受 `BaseReport` 实例，不感知具体报表。
- **新增报表的 3 步**：写 `reports/<name>.py` 子类 → 在 `config.py:get_report_registry()` 注册 → 加 `templates/<name>.default.yaml`。

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

### 3. 字段元数据双源策略（reports/base.py:_index_fields）
字段定义从两处抠，**优先级从高到低**：
1. `cards[].content.meta.chartMain.zoneData.{row,column,metric}` —— 已配置态，含 `calculationType`/`isAggregated`/`fieldFormat` 等 metric 必备属性
2. `dsInfos[*].columns` —— 数据集字段池，回退用

**为什么**：从字段池取的 metric item 缺 `fieldFormat`，BI 后端会报 `卡片查询错误，错误详情: None.get`（5001）。配置态的 metric 必须透传 raw，不能精简。

### 4. 重名字段与多数据集
同一字段名（如"渠道品牌"）在不同数据集里 fdId 不同。子类用 `default_ds_id` 指定首选数据集；`field(name, ds_id=...)` 可显式选。`_fields_by_name_and_ds` 是完整索引。

### 5. filter 和 dynamicParams 的 sourceCdId
filter 的 `sourceCdId`（选择器卡片 ID）和 dynamicParams 的 `sourceCdId`（控件 ID）**不在页面元数据里**，要硬编码到子类：

- `RetailDailyReport.FIELD_SOURCE_CDID` —— filter 名 → 选择器 ID 映射
- `RetailDailyReport.DYNAMIC_PARAMS` —— 动态参数名 → `{dpId, valueType, sourceCdId}` 映射

新增报表时从 HAR 抓这两组 ID 复制过来。

### 6. 响应结构有三种形态（client.py:_check_ok）
`_check_ok` 必须全兼容：
- 标准：`{result: "ok", response: {...}}`
- 任务接口带 raw-backend-response：`{result: "ok", response: {status, ...}}`
- 任务接口裸：`{taskId, status, result: {success, exportPath}}`（顶层无 result 字段或 result 是 dict）

`raw-backend-response: TRUE` 请求头会让服务端返回"包装态"，否则是"裸态"——同一个 `/api/task/{id}` 接口两种响应。

### 7. 异步导出三步走（export.py）
```
POST /api/write/file/{card_id}?typeOp=PIVOT|CSV  → {response: {taskId}}
GET  /api/task/{taskId}                          → {status: PROCESSING|FINISHED}
POST /api/export/file/common/{taskId}            → 二进制流
```
- `PIVOT` = Excel，`CSV` = CSV
- 轮询响应在裸态时 `status` 在顶层，包装态时在 `response.status`，`poll_task` 两种都兼容
- 文件名从 `content-disposition` 解析；Windows 落盘前用 `re.sub(r'[\\/:*?"<>|]', "_", name)` 替换非法字符

### 8. JWT 14 天有效期 + 全自动凭证恢复
登录后 `exp` 是签发时间 +14 天（1209600 秒）。`auth/login.py:_decode_jwt_exp` 从 JWT payload 解出 `exp` 存入 `Credentials.expires_at`。

`AntaSession.ensure()`（每次 CLI 调用入口）自动校验并恢复凭证，**无需人工重登**：
1. 校验两个维度：本地 `expires_at` + 服务端 `/api/validate-token`（会话可能被顶号/登出提前作废）
2. 任一失效 → 先 `refresh_credentials()`（CAS 标准 `POST /oauth2.0/token`，未经成功样本验证）
3. refresh 失败 → 用 `.env` 的 `ANTA_USERNAME/ANTA_PASSWORD/ANTA_DOM_ID` 走完整 `login()` 自动重登（2026-08 实测成功）
4. 都失败才抛 `SessionExpired`（如密码已改、触发验证码）

前提：`.env` 里配置了账号密码（`config.py` 启动时加载）。

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

## 模板系统（templates/）

YAML 模板里只写**可读字段名**（中文），运行时通过 `report.field(name)` 解析为 fdId。`templates.py:template_to_params` 把 YAML → `QueryParams` 对象。CLI 参数和模板字段同名时 CLI 优先（待实现，目前 CLI 直接走模板）。

```yaml
report: retail_daily
rows: [渠道品牌, 店铺名称]
metrics: [零售流水目标, 流水]
filters:
  - { name: 渠道品牌, values: [DESCENTE] }
dynamic_params:
  开始日期-户外-R02: 2026-07-22   # YAML 会解析成 date，templates.py 内部转回字符串
limit: 50
```

## 已知遗留问题

- **refresh 续期路径未验证**：`refresh_credentials()` 走 CAS 标准 `POST /oauth2.0/token`，未拿到成功样本（活 refresh_token 尚未经历过到期）。不重要：失败会自动落到完整重登（已实测成功）。
- **会话中途凭证失效不自动恢复**：校验/恢复只在 `ensure()` 入口（每次 CLI 调用都经过）；单次导出任务进行中被服务端作废（error_code 1018）会直接抛 `AntaAPIError`，重跑命令即可自动恢复。
