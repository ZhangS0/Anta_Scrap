# ER04-推广效果分析报表（MAIA）工作流 plan

- 报表 key：`er04_promotion_maia`（spec 路径，指引 `.claude/skills/anta-bi/references/er04_promotion_maia.md`）
- BI 页面：https://datav.anta.com/page/s4b872716d99c43d7b22dc17
- 接入：2026-10-16，验证账号 2024070158（MAIA 同事）
- 模板用法：复制 `templates/promotion_full.yaml` 后只改 dynamic_params/filters，整份传 MCP `export_report` 的 `template_yaml`

## 要点

无日期参数：全量导出（2026-03-01 起 229 行@日期粒度）+ 本地切片；计划/词名粒度行数会大

## 自检清单（每次 run 后核对）

- [ ] CSV 表头与请求字段一致——先按指引「列名映射」换算再比对（本报表有别名）
- [ ] 日期参数显式传（缺省是宏 yesterday / yesterday-1 years，跨日漂移）
- [ ] 行数量级合理（异常放大先查筛选是否生效/是否误用维度表字段名）

## 资产路径

- 指引：`.claude/skills/anta-bi/references/er04_promotion_maia.md`
- 页面元数据与连接 truth 留档：`captures/maia_onboard/`
- history/<run>/：每次导出的 CSV（gitignore，只新建不覆盖）
