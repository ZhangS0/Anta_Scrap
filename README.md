# anta-scrap

安踏 BI（`datav.anta.com`）抓取库：按 YAML 模板导出 CSV。可导入使用，也提供 CLI。

## 安装

```bash
cd <PROJECT_ROOT>
pip install -e .
```

复制 `.env.example` 为 `.env`，填入账号密码：

```
ANTA_USERNAME=<工号A>
ANTA_PASSWORD=your_password
```

## 使用

### 1. 导出 CSV（凭证全自动，无需手动登录）

```bash
anta-cli export -t retail_daily_descente.default
anta-cli export -t retail_daily_kolon.default --name kolon_daily -o ./out
```

导出前自动校验凭证（本地过期时间 + 服务端 validate-token）；失效时依次自动恢复：
refresh_token 续期 → 失败则用 `.env` 账号密码走完整 CAS 登录（覆写凭证）。
全程零人工干预，前提是 `.env` 配置了账号密码。

手动登录命令仍可用（`anta-cli login`），仅用于首次验证账号或排查登录问题。

### 2. 作为库

```python
from pathlib import Path

from anta_scrap import AntaSession
from anta_scrap.config import get_report_class
from anta_scrap.export import export_csv
from anta_scrap.templates import load_template, template_to_params

with AntaSession.ensure() as sess:  # 内部自动校验/续期凭证
    cls = get_report_class("retail_daily_descente")
    rpt = cls(sess.client)
    params = template_to_params(rpt, load_template("retail_daily_descente.default"))
    out = export_csv(rpt, params, out_dir=Path("./out"))
    print(out)
```

## MCP 服务（对外 agent 调用）

对外提供 MCP 服务 `anta-mcp`（streamable-http），登录在服务端完成、返回 CSV 全文。报表/字段说明见 `anta-bi` skill，MCP 只暴露一个导出工具。

### 启动

```bash
anta-mcp --host 0.0.0.0 --port 8002
# 或双击 start_anta_mcp.bat（未设密钥时会交互式提示输入）
```

- 端点：`http://<host>:8002/mcp`
- 唯一工具：`export_report(username, template_yaml, password="", dom_id="", output_name="")`
- 鉴权：设环境变量 `ANTA_MCP_API_KEY` 后，调用须带 `Authorization: Bearer <key>`

### Agent 接入（项目根 `.mcp.json`）

```json
{
  "mcpServers": {
    "anta-bi": {
      "type": "http",
      "url": "http://REDACTED-MCP-HOST:8002/mcp",
      "headers": { "Authorization": "Bearer REDACTED-OLD-API-KEY" }
    }
  }
}
```

### 多用户凭证

- `~/.anta_scrap/credentials.json`：按账号存 JWT（map 格式）
- `~/.anta_scrap/accounts.json`：按账号存密码（明文 0600）
- 首次登录传 `password`，之后日常只传 `username`，服务端自动复用缓存/用已存密码重登

### 内网穿透（frp，纯 IP）

本地 8002 → frp tcp 转发 → 公网 8002：

```ini
; frpc.ini（本地）
[common]
server_addr = <frps 公网 IP>
server_port = 7000
token = <token>

[anta-bi]
type = tcp
local_ip = 127.0.0.1
local_port = 8002
remote_port = 8002
```

```ini
; frps.ini（VPS）
[common]
bind_port = 7000
token = <token>
```

> 纯 IP 只能明文 HTTP；要 HTTPS 需域名 + `type = https` + `https2http` 插件（证书放 frpc 侧）。

## 模板

`templates/*.yaml` 是可读的查询配置。修改字段/条件/日期无需改代码：

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

## 模块化扩展（新增报表）

1. 在 `anta_scrap/reports/xxx.py` 新建 `XxxReport(BaseReport)`，设置 `page_id` / `card_id` / `name`，实现 `default_template()`。
2. 在 `anta_scrap/config.py` 的 `get_report_registry()` 注册。
3. 加一份 `templates/xxx.default.yaml`。

## 目录约定

| 路径 | 用途 |
|---|---|
| `.env` | 账号密码（**不进库**） |
| `~/.anta_scrap/credentials.json` | 登录后的 token，按账号存（**不进库**） |
| `~/.anta_scrap/accounts.json` | 多用户密码，明文 0600（**不进库**） |
| `.mcp.json` | MCP 接入配置（Claude Code 等） |
| `start_anta_mcp.bat` | MCP 服务启动脚本（端口 8002） |
| `templates/` | YAML 模板 |
| `out/` | 导出文件默认目录 |

## 已知风险

- **`loginTraceId` / `execution`**：CAS 表单的这两个 token 实施时如自动抓取失败，可能需要手动从浏览器复制一次或用 Playwright 兜底。
- **登录页改版/验证码**：若触发（异地登录、多次失败），需在 `auth/login.py` 加 hook。
- **refresh 续期路径未验证**：refresh_token 换新 token 还没有成功样本；不重要，失败会自动落到完整重登（已实测成功）。
