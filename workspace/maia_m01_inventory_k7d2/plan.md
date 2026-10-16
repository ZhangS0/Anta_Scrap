# M01-库存结构分析（MAIA）工作流 plan

- 报表 key：`m01_inventory_maia`（spec 路径，指引 `.claude/skills/anta-bi/references/m01_inventory_maia.md`）
- BI 页面：https://datav.anta.com/page/r963f41695fc845bcae9333d
- 接入：2026-10-16，验证账号 2024070158（MAIA 同事）
- 模板用法：复制 `templates/inventory_by_node.yaml` 后只改 dynamic_params/filters，整份传 MCP `export_report` 的 `template_yaml`

## 要点

库存快照（只有结束时间参数，无开始时间）；行/筛选用主数据集名字（店仓名称/店仓编码）

## 自检清单（每次 run 后核对）

- [ ] CSV 表头与请求字段一致——先按指引「列名映射」换算再比对（本报表有别名）
- [ ] 日期参数显式传（缺省是宏 yesterday / yesterday-1 years，跨日漂移）
- [ ] 行数量级合理（异常放大先查筛选是否生效/是否误用维度表字段名）

## 资产路径

- 指引：`.claude/skills/anta-bi/references/m01_inventory_maia.md`
- 页面元数据与连接 truth 留档：`captures/maia_onboard/`
- history/<run>/：每次导出的 CSV（gitignore，只新建不覆盖）
