# 工作流 Plan：KOLON 最近两周流水分析

- 报告任务：`kolon_recent_sales_3t4g`（报告名 kolon_recent_sales / 报告id 3t4g）
- 适用场景：按两周窗口生成 KOLON 品牌店 × 日颗粒流水分析：总体达成、同店对比、区域汇总、门店 Top10
- 输出格式：Markdown（`history/<run>/report.md`）；需可视化时按 bi-report-build 第⑤步升级 HTML

## 资产路径表

| 资产 | 路径 |
|---|---|
| 查询模板 | `templates/daily.yaml`（report: retail_daily_kolon） |
| DAG 脚本 | `analysis.py` |
| 原始 CSV / 报告产物 | `history/<run>/` |

## 参数表（复用时只改这里 → 套进模板再查询）

| 参数 | 说明 | 默认值 |
|---|---|---|
| start_date | 开始日期 | 2026-08-02 |
| end_date | 结束日期 | 2026-08-15 |
| brand_filter | 渠道品牌筛选 | KOLON |
| rows | 维度 | 日历日期 / 渠道品牌 / 店铺编码 / 店铺名称 / 省份 / 区域 / 门店性质 |
| metrics | 指标 | 流水 / 预算流水目标 / 流水同期 / 同店流水 / 同店流水同期 |
| limit | 导出行数上限 | 5000 |
| username | BI 工号 | 向项目所有者索取 |

## 执行步骤

1. 采集：按 `anta-bi` skill，读 `templates/daily.yaml` 只改日期参数 → 调 `export_report` → CSV 存 `history/<run>/`
2. 加工：`PYTHONIOENCODING=utf-8 $PY analysis.py --csv history/<run>/<文件>.csv`（报告写同目录 `report.md`）
3. 呈现：向用户汇总关键结论（达成率、同店同比、区域差异、Top10）

## 交付前自检清单

- [ ] 筛选条件正确（渠道品牌=KOLON）
- [ ] CSV 表头与请求 metrics 一致（防静默丢指标）
- [ ] 流水合计量级与上次 run 偏差可解释
- [ ] run 目录为新建，未覆盖历史
