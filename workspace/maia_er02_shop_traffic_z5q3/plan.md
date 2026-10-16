# ER02-电商店铺流量流水分析（MAIA）工作流 plan

- 报表 key：`er02_shop_traffic_maia`（spec 路径，指引 `.claude/skills/anta-bi/references/er02_shop_traffic_maia.md`）
- BI 页面：https://datav.anta.com/page/w7ddf5dba214e4232a00b1ee
- 接入：2026-10-16，验证账号 2024070158（MAIA 同事）
- 模板用法：复制 `templates/shop_traffic_daily.yaml` 后只改 dynamic_params/filters，整份传 MCP `export_report` 的 `template_yaml`

## 要点

单数据集；店铺数 ~10；注意 50 个指标列名映射（见指引）

## 自检清单（每次 run 后核对）

- [ ] CSV 表头与请求字段一致——先按指引「列名映射」换算再比对（本报表有别名）
- [ ] 日期参数显式传（缺省是宏 yesterday / yesterday-1 years，跨日漂移）
- [ ] 行数量级合理（异常放大先查筛选是否生效/是否误用维度表字段名）

## 资产路径

- 指引：`.claude/skills/anta-bi/references/er02_shop_traffic_maia.md`
- 页面元数据与连接 truth 留档：`captures/maia_onboard/`
- history/<run>/：每次导出的 CSV（gitignore，只新建不覆盖）
