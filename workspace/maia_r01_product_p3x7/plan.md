# R01-零售商品分析报表（MAIA）工作流 plan

- 报表 key：`r01_product_maia`（spec 路径，指引 `.claude/skills/anta-bi/references/r01_product_maia.md`）
- BI 页面：https://datav.anta.com/page/d8387bb63c75448e49decb7f
- 接入：2026-10-16，验证账号 2024070158（MAIA 同事）
- 模板用法：复制 `templates/*.yaml` 后只改 `dynamic_params` 日期与 `filters`，整份 YAML 传 MCP `export_report`
  的 `template_yaml`（`report_spec` 块原样保留）

## 参数表

| 参数 | 取值 | 说明 |
|---|---|---|
| MAIA报表开始时间 / 结束时间 | YYYY-MM-DD | 本期窗口；缺省宏 `yesterday`，建议显式传 |
| MAIA报表同期开始时间 / 同期结束时间 | YYYY-MM-DD | 同比类指标必传；缺省宏 `yesterday-1 years` |
| 大类 | 服装、配件 | 可多选 |
| 其余筛选（中类/配货季/产品季/货号等 22 个） | 见指引「筛选字段」 | 均可多选 |

## 已验证查询（2026-10-16，账号 2024070158）

| 模板 | rows | metrics | 验证结果 |
|---|---|---|---|
| sku_daily.yaml | 货号 | 本期零售金额、本期零售数量、本期折扣率 | 2209 行（limit 不截断），表头完整；负数行=退货 |
| category_structure.yaml | 大类+中类 | 本期零售金额、本期零售数量、本期件单价、件单价同比 | 大类筛选精确生效；公式型指标正常 |

## 自检清单（每次 run 后核对）

- [ ] CSV 表头与请求 metrics 逐字一致（唯一映射：销售数量同比→零售数量同比）
- [ ] 同比类指标的同期两个日期参数已显式传
- [ ] 货号/款号粒度全量数千行——落盘后本地聚合，导出前用 filters 收窄可控量

## 资产路径

- 指引：`.claude/skills/anta-bi/references/r01_product_maia.md`
- 页面元数据与连接 truth 留档：`captures/maia_onboard/`（page_R01_*.json、spec_truth_R01_*.json）
- history/<run>/：每次导出的 CSV（gitignore，只新建不覆盖）
