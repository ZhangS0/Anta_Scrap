---
name: anta-bi
description: 安踏 BI（datav.anta.com）数据查询与导出。当用户要查询或导出零售日报、迪桑特(DESCENTE)/可隆(KOLON)品牌的流水、目标达成、客流、试衣等经营数据时使用。
---

# anta-bi：安踏 BI 报表查询

查询通过 **MCP 工具 `export_report`** 完成（MCP 服务在项目 `anta-scrap` 内，`anta-mcp` 常驻 streamable-http）。登录在服务端完成、返回 CSV 全文文本。
本 skill 只做两件事：**报表/字段说明**（本目录 `references/`）+ **MCP 使用说明**。不含任何脚本。

## 报表路由（按需求选一个，只 Read 对应指引）

| registry key | 报表 | 适用场景 | 指引 |
|---|---|---|---|
| `retail_daily_descente` | 零售运营分析-日报-迪桑特 | DESCENTE/迪桑特品牌的流水、目标、客流 | `references/retail_daily_descente.md` |
| `retail_daily_kolon` | 零售运营分析-日报-KOLON | KOLON/可隆品牌，含试衣指标、店效分级 | `references/retail_daily_kolon.md` |
| `retail_traffic_descente` | 零售客流分析-迪桑特 | DESCENTE 品牌客流专项（时段/进店率） | `references/retail_traffic_descente.md` |
| — | 指标含义字典（流水/达成/连带率/试衣率怎么算） | 用户问指标定义、需甄别相近指标时 **Grep 查** | `references/metrics-glossary.md` |

两报表共享同一 BI 页面，字段体系相同；区别：DESCENTE 有商品品牌筛选、客流更全；KOLON 多试衣指标、挑战目标、店效分级维度。

## 查询工作流（4 步）

1. **路由**：按品牌/需求从上表选报表，Read 对应指引（单次最多读 1 个）。
2. **编制模板**：按指引选维度/指标/筛选/日期，拼一个 YAML 字符串（**内联传给工具，不落盘**）。字段名必须与指引**逐字一致**（中文全名）。格式见指引，示例：
   ```yaml
   report: retail_daily_kolon
   rows: [日历日期]
   metrics: [流水, 流水同期, 流水同比]
   filters:
     - { name: 渠道品牌, values: [KOLON] }
   dynamic_params:
     开始日期-户外-R02: "2026-08-03"
     结束日期-户外-R02: "2026-08-09"
   ```
3. **调用 MCP 工具 `export_report`**：日常**只传 `username`（工号）+ `template_yaml`**。`password` 仅在该账号**首次登录或登录失败**时补传（首次可向用户索取，之后服务端记住密码并自动复用）；`dom_id`/`output_name` 一般不传。
4. **返回结果**：工具直接返回 **CSV 全文文本**（导出是异步任务，数秒~1分钟）。直接解析并以 markdown 表格/摘要向用户呈现关键数据；数据量大时先汇总再展示。

## 排错对照（对应工具返回的错误串）

- `需要密码: ...` → 该账号首次登录或凭证失效且无本地密码，向用户索取后补传 `password`
- `登录失败...账号密码可能错误或触发验证码` → 账密错或触发验证码，向用户确认后重试
- `模板错误: ...缺少 report 字段` → template_yaml 里漏了 `report`
- `模板错误: 未知报表 'xxx'` → report 名写错，可选值见路由表 registry key
- `字段未找到...` → 字段名与 BI 不一致，核对该报表 reference 清单
- `查询/导出失败: 卡片查询错误，错误详情: None.get` → metric 名写错或该字段不在卡片配置态
- `查询/导出失败: 导出任务失败` → 多为选了该卡片不可导出的指标（KOLON 常见，见各报表指引「已知缺陷」）；逐个减指标定位坏指标
- **返回表头少于请求的 metrics** → 缺的指标被服务端**静默丢弃**（不报错！）。每次导出后必须核对 CSV 表头与请求 metrics 一致，缺列就换指标（KOLON 常见，如同比类/客流类）
- **怀疑日期筛选没生效** → 临时把 rows 改成 `[日历日期]` 查一次，直接看返回的日期范围
- `未授权...` → 调 MCP 时没带 `Authorization: Bearer <ANTA_MCP_API_KEY>`（服务端已启用令牌时）

## 上下文纪律（重要）

- **禁止整读** `references/metrics-glossary.md`（指标定义很长）；查指标用 Grep 关键词定位。
- 报表指引每次查询只读需要的 1 个；SKILL.md 本身不展开字段清单。

## 备注

- MCP 服务与字段解析（fdId）在项目 `anta-scrap`（`anta-mcp`）内，本 skill 无需关心。
- 本地调试用项目内 `anta-cli`（非本 skill 范畴）。
