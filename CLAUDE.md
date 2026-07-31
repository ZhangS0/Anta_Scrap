# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

`anta-scrap` 是安踏 BI（`datav.anta.com`）的数据抓取库，可导入使用，也提供 `anta-cli` 命令行。首个报表：零售运营分析-日报（page `ne63f6cf08bbb40c28b814e8` / card `q72769bce32b04f91873eeee`）。

## 常用命令

```bash
# 安装（开发模式，editable）
pip install -e .

# 登录（写凭证到 ~/.anta_scrap/credentials.json）
python scripts/anta_login.py
# 或
anta-cli login

# 列字段 / 查询 / 导出
anta-cli fields
anta-cli query -t retail_daily.default
anta-cli query --all
anta-cli export --format xlsx
anta-cli export --format csv

# 注意：当前 shell 默认可能指向 hermes-agent 的 venv Python，跑 CLI 要显式用系统 Python：
"C:/Users/ZHANGSONG/AppData/Local/Programs/Python/Python312/python.exe" -m anta_scrap.cli <cmd>
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
- `auth/` 不依赖任何报表概念；只负责 CAS+OAuth2 登录、凭证持久化、Session。
- `client.py` 不依赖任何报表；只负责带 header 的 HTTP 原语 + 通用轮询。
- `reports/base.py:BaseReport` 是抽象基类；`reports/<name>.py` 子类提供 `page_id`/`card_id`/`default_template()`。
- `paging.py` / `export.py` / `templates.py` / `io_utils.py` 都接受 `BaseReport` 实例，不感知具体报表。
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

### 8. JWT 14 天有效期
登录后 `exp` 是签发时间 +14 天（1209600 秒）。`auth/login.py:_decode_jwt_exp` 从 JWT payload 解出 `exp` 存入 `Credentials.expires_at`。当前未实现 refresh_token 续期；过期直接重跑 `anta_login`。

### 9. 登录链路（auth/login.py）
CAS + OAuth2 混合：
```
GET  登录页（带 service 参数）→ 抓 execution（CAS Webflow token）
POST 表单（username/password/execution/loginTraceId/...）→ 302 带 ticket
GET  /oauth2.0/callbackAuthorize?ticket=...  → 302 到 datav
GET  datav.anta.com/?access_token=AT-xxx&refresh_token=RT-xxx  → set-cookie: uIdToken=<JWT>
```
JWT 在 cookie `uIdToken` 里（httponly），不在 HTML 或响应体。`loginTraceId` 抓不到时用随机 32 位 hex 兜底；`execution` 抓不到时用 `e1s1` 兜底。

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

- **查询数据 DataFrame 列名是 `col_0/col_1/...`**：`raw-backend-response` 响应的 data 单元格是 `{v:val}` 结构，无列名。导出的 xlsx/csv 由服务端生成有正确列名，所以只影响 CLI 终端展示。修复需从 `chartMain.column` 解析列名映射。
- **`fetch_max_pages` 的 summary 文案**：当 max-pages > 1 时仍显示"当前仅读取第 1 页"，应按实际页数动态生成。
- **无 refresh_token 续期**：JWT 过期前没有自动刷新，过期后必须重跑 `anta_login`。
