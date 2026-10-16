# R02-零售抓手分析报表（MAIA）工作流 plan

- 报表 key：`r02_gripper_maia`（spec 路径，指引 `.claude/skills/anta-bi/references/r02_gripper_maia.md`）
- BI 页面：https://datav.anta.com/page/jcee6539f2fcd4706a3ec543
- 接入：2026-10-16，验证账号 2024070158（MAIA 同事）
- 模板用法：复制 `templates/*.yaml` 后只改 `dynamic_params` 日期与 `filters`，整份 YAML 传 MCP `export_report`
  的 `template_yaml`（`report_spec` 块原样保留）

## 参数表

| 参数 | 取值 | 说明 |
|---|---|---|
| MAIA报表开始时间 / 结束时间 | YYYY-MM-DD | 本期窗口；缺省宏 `yesterday`，建议显式传 |
| MAIA报表同期开始时间 / 同期结束时间 | YYYY-MM-DD | 同比类指标必传；缺省宏 `yesterday-1 years` |
| 区域 | 玛伊娅-东区/北区/南区/安徽/山西/总部/河北/浙江/电商/重庆/陕西/黑龙江 | 可多选 |
| 其余筛选 | 见指引「筛选字段」 | 均可多选 |

## 已验证查询（2026-10-16，账号 2024070158）

| 模板 | rows | metrics（CSV 列名） | 验证结果 |
|---|---|---|---|
| store_daily.yaml | 店铺名称 | 本期零售金额、本期零售数量、本期小票数、本期客单价、本期连带率、本期折扣率 | 88 店，表头完整 |
| region_summary.yaml | 区域+店铺名称 | 本期零售金额、本期零售数量、本期预算目标达成 | 表头完整；区域筛选另实测精确生效（88→32 店） |

注意：客单价/连带率/折扣率/预算目标达成 等基础指标 CSV 列名带「本期」前缀（alias），完整映射见指引。

## 自检清单（每次 run 后核对）

- [ ] CSV 表头与请求 metrics 逐字一致——先按指引「列名映射」把请求名换算成列名再比对
- [ ] 同比类指标的同期两个日期参数已显式传
- [ ] 行数量级合理（门店 ~90、区域 12；异常放大先查筛选是否生效）

## 资产路径

- 指引：`.claude/skills/anta-bi/references/r02_gripper_maia.md`
- 页面元数据与连接 truth 留档：`captures/maia_onboard/`（page_R02_*.json、spec_truth_R02_*.json）
- history/<run>/：每次导出的 CSV（gitignore，只新建不覆盖）
