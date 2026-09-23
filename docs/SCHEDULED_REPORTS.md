# 例行/定时报表任务运维手册

2026-09 起系统进入例行化运营，现有 5 个定时/例行任务。本手册汇总各任务要素与
故障 SOP，故障处置遵循一条铁律：**数据链路与推送链路解耦**——采集/聚合/HTML
生成成功即算任务主体完成，推送失败单独补推，不重跑查询。

## 任务矩阵

| 任务 | 频率/时间 | 报告 id | BI 查询量 | 依赖账号 | 交付渠道 |
|---|---|---|---|---|---|
| 经营预警日报（biz_early_warning_a7k3） | 每日 09:0x | a7k3 | 18-20 次（两品牌日报三窗口+区域+店铺 + R03库存 + 售罄） | 2015030199 | 钉盘 HTML + 钉钉个人/群会话推送 |
| 可隆华东月报每日刷新（kolon_east_monthly_report_8a3f） | 每日 09:30 | 8a3f | 20-31 次（可隆日报/月报/客流/鞋占比 + 迪桑特双筛日报/月报） | 2023090512（可隆）+ 1385118（迪桑特双筛） | workspace history 归档 + 根目录 HTML |
| KOLON MTD 日报（kolon_daily_sales_amqk） | 每日 12:0x | amqk | 2-4 次 | 1385118 | HTML + CSV → `D:\AI构建\KL日报`（同报告日已存在则跳过） |
| 迪桑特周报（descente-weekly-report skill） | 每周 | — | 21-31 次（流水达成 + R03 销存 + 售罄率三部分合订） | 全国口径账号 | 合订 HTML（三锚点目录） |
| 周会-兄弟品牌达成对比（ne_retail_ach） | 每周一 09:00（定时任务 id 960549243671556096） | a8f3 | 4 次 | 全国口径账号 | HTML；窗口=当月1日~上周日 |

## 三类高频故障 SOP

### 1. 会话未注册 anta-bi MCP（历史最高频：9/4、9/6、9/7、9/16 四次）

- **现象**：`No MCP server is registered for the current chat` / `Unknown MCP server: anta-bi` / `server not found`
- **根因**：MCP 按会话注册；`message_schedule` 定时会话不注入 `mcp_servers.json`（平台侧 client_config 来源问题），部分交互会话也只注入了 integrated_code_mode
- **处置**：改用直连通道 `python scripts/anta_mcp_call.py <tool> --args '{...}'`（端点自动读 `.mcp.json`，等价 MCP 调用，见 anta-bi skill 工作流第 0 步）；治本需平台侧在定时会话的 client_config 注入 mcp_servers.json（平台配置项，非本仓库代码）
- **上报**：报 issue，title 加 `[补推]` 前缀

### 2. Bearer 鉴权阻断（9/4-9/7 连续 3 期）

- **现象**：所有调用返回 `未授权：缺少或错误的 Authorization 头`；`mcp_servers.json` 里 Authorization 为字面量 `${ANTA_MCP_API_KEY}` 未替换，或本地仅存 `smenc:` 密文无明文
- **处置**：真实 key 必须走 `env-manager set_env` 持久化（个人级即可），**绝不把 key 写进报告、模板或对外输出**；服务端现已对占位符/密文形态启动即拒（`mcp_server.py:_api_key_config_error`，2026-09-23 起）
- **注意**：重启 MCP 服务端前确认 key 为真实明文，否则服务拒启（这是有意设计）

### 3. dws 钉钉登录态过期（9/12/13/14/20 四次，推送阻塞最长 9 天）

- **现象**：`dws drive upload` 报 `旧版登录态无法由当前认证服务刷新`；`dws auth status` 为 `authenticated:false / token_refresh_failed`
- **处置**：设备流授权码约 5 分钟超时，**2 轮授权码无人确认即停止重试**（无人值守环境确认无意义），上报并等人工授权；授权后仅补「上传+推送」两步，**不重跑查询**
- **预防**：每日任务自检加 `dws auth status`；到期前 3 天在推送消息文本中提醒人工授权（授权有效期历史约 1-2 周，需按实际观察更新）

## [补推] 约定

任务当期失败、事后恢复补跑时，feedback 的 title 统一加 `[补推]` 前缀（例：
`[补推] 8月版v6.13修订交付（…）`），body 写明补跑的口径窗口与最终交付物，
context 带 `run`。这样维护者分析日志时能把「当期失败」与「补交付」对上，
不会误判数据断档。

## 任务自检清单（每个例行任务通用）

1. 采集前：`dws auth status` 检查（有推送环节的任务）
2. 采集后：核对 CSV 表头与请求 metrics 一致（静默丢列，见各报表指引「已知缺陷」）
3. 迪桑特日报类查询：确认含 `商品品牌=迪桑特` 双筛（漏筛翻倍，2026-09-04 定时任务复发过）
4. 聚合后：与上一 run 交叉核对重叠日数值（BI 回流修正在 ±0.1% 内正常，以最新为准）
5. 交付后：`submit_feedback` 报结果；失败按上面 SOP 处置并 `[补推]` 回填

## 版本更新检查（check 可定时，更新永远需人确认）

机制：`python scripts/update.py check [--json]`（只读，不碰工作区）对比本地 `VERSION` 与
GitHub 上游（origin/main），输出分叉检测（本地定制提交/脏文件/自加内容）与影响范围分桶
（🔴 需重启 / 🟡 需动作 / 🟢 无感）。执行更新用 `apply`，必须人工确认——**不做静默自动更新**。

定时接入两例：

- **agent 平台（远程环境）**：message_schedule 每日一次
  `python scripts/update.py check --json`，解析 JSON 的 `behind` 字段——`>0` 才向用户播报
  影响范围并询问是否 `apply`；`==0` 静默结束。
- **Windows 本地**：双击 `scripts\check_update.bat` 手动查；要定时就把它挂进任务计划程序
  （程序：`c:\path\to\Anta_Scrap\scripts\check_update.bat`，触发器：每日任意时间）。
