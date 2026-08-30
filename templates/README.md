# 模板目录说明

本目录只放**库级模板**（属于报表注册体系，由 `anta-bi-onboard` skill 维护）。
报告任务自己的工作流模板在 `workspace/<报告名>_<报告id>/templates/`，随该报告的 plan 与脚本管理。

## 库级模板

### `<report>.default.yaml` × 6 — 各报表默认查询

| 模板 | 报表 |
|---|---|
| `retail_daily_descente.default.yaml` | 迪桑特 零售运营分析-日报 |
| `retail_daily_kolon.default.yaml` | 可隆 零售运营分析-日报 |
| `channel_monthly_descente.default.yaml` | 迪桑特 渠道运营分析-月报 |
| `channel_monthly_kolon.default.yaml` | 可隆 渠道运营分析-月报 |
| `r03_sales_stock_descente.default.yaml` | 迪桑特 R03 销存结构分析 |
| `r03_sales_stock_kolon.default.yaml` | 可隆 R03 销存结构分析 |

用法：`anta-cli export -t retail_daily_kolon.default`（或 MCP 模板里 `report:` 对应同名 registry key）。

### `<report>.reference.yaml` × 6 — 全字段参考（注释态）

列出该报表全部维度/指标字段（含 fdId 注释），供编制模板时 Grep 定位字段名。
skill 指引（`.claude/skills/anta-bi/references/`）会指向对应文件，**勿整读，用 Grep**。

## 模板 schema

```yaml
report: retail_daily_kolon        # registry key（必填）
rows: [渠道品牌, 店铺名称]         # 维度
# columns: [...]                  # 列维度（可选）
metrics: [零售流水目标, 流水]      # 指标
filters:
  - { name: 渠道品牌, values: [KOLON] }
dynamic_params:
  开始日期-户外-R02: 2026-07-22    # YAML 解析成 date，templates.py 内部转回字符串
  结束日期-户外-R02: 2026-07-29
limit: 50
offset: 0
# card_name: 自定义导出文件名（缺省用报表 name）
```

注意：字段名必须与 BI 逐字一致（查 skill 指引或 reference 模板）；
`find_template` 只在本目录根按文件名查找，workspace 下的模板需传路径加载。
