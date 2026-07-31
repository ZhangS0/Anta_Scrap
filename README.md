# anta-scrap

安踏 BI（`datav.anta.com`）抓取库。可导入使用，也提供 CLI。

## 安装

```bash
cd C:\Users\ZHANGSONG\Desktop\project\Anta_Scrap
pip install -e .
```

复制 `.env.example` 为 `.env`，填入账号密码：

```
ANTA_USERNAME=<工号A>
ANTA_PASSWORD=your_password
```

## 使用

### 1. 登录（首次）

```bash
python scripts/anta_login.py
# 或：anta-cli login
```

凭证写入 `~/.anta_scrap/credentials.json`，JWT 有效期约 14 天。

### 2. CLI

```bash
# 列出报表可选字段
anta-cli fields

# 按模板查询（默认只读第 1 页，会打印分页提示）
anta-cli query -t retail_daily.default

# 翻页拉全部
anta-cli query --all

# 导出
anta-cli export --format xlsx -o ./out
anta-cli export --format csv  -o ./out
```

### 3. 作为库

```python
from anta_scrap import AntaSession
from anta_scrap.reports.retail_daily import RetailDailyReport
from anta_scrap.templates import load_template, template_to_params
from anta_scrap.paging import fetch_first_page
from anta_scrap.export import export_and_download, EXPORT_CSV

with AntaSession.ensure() as sess:
    rpt = RetailDailyReport(sess.client)
    params = template_to_params(rpt, load_template("retail_daily.default"))
    page = fetch_first_page(rpt, params)
    print(page.summary)   # "共 339 行 / 7 页，当前仅读取第 1 页..."

    # 导出 CSV
    export_and_download(rpt, params, EXPORT_CSV, out_dir=Path("./out"))
```

## 模板

`templates/*.yaml` 是可读的查询配置。修改字段/条件/日期无需改代码：

```yaml
report: retail_daily
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
| `~/.anta_scrap/credentials.json` | 登录后的 token（**不进库**） |
| `templates/` | YAML 模板 |
| `out/` | 导出文件默认目录 |

## 已知风险

- **`loginTraceId` / `execution`**：CAS 表单的这两个 token 实施时如自动抓取失败，可能需要手动从浏览器复制一次或用 Playwright 兜底。
- **登录页改版/验证码**：若触发（异地登录、多次失败），需在 `auth/login.py` 加 hook。
- **token 失效**：JWT 14 天有效，过期后重新跑 `anta_login` 即可。
