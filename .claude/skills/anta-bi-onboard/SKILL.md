---
name: anta-bi-onboard
description: anta-bi skill 的辅助维护 skill，专门为其添加新的可查询报表。当用户提供完整查询 HAR / 查询参数 / 指标说明（可选），要求把某个安踏 BI 报表接入 anta-bi 查询体系时使用。产出含「报表连接 spec」的报表指引（纯文档接入，不改服务端代码、不需重启）。
---

# anta-bi-onboard：为 anta-bi 添加新报表

把用户交付的 BI 报表（完整查询 HAR + 查询参数 + 指标说明可选）接入 anta-bi 查询体系。
**纯文档任务**：MCP 是通用执行器，新报表的连接知识由 anta-bi 指引携带、调用方模板内联
`report_spec` 块——产物只有 skill 指引（+可选字段数据文件），**服务端零改动、即时生效**；
git 提交仅为沉淀知识供后续复现，不再有"部署重启"环节。

## 输入清单（缺项先向用户索要）

| 输入 | 必需 | 用途 |
|---|---|---|
| 完整查询过程 HAR | ✅ | 页面/卡片/数据集 ID、配置态字段、响应形态 truth |
| 查询参数 txt（请求负载） | ✅ | dynamic_params、field_source_cdid、payload 结构 |
| 指标说明 xlsx/md | 可选 | 字段业务口径，写进 skill 指引 |

## 四步流程

1. **解析抓取**：从 HAR/参数文件抠出——`page_id`（页面 URL `ne…/we…` 段）、`card_id`、
   主数据集 `default_ds_id`、动态参数定义（dpId/valueType/sourceCdId）、
   `field_source_cdid`（filter 字段名 → 选择器卡片 ID）、配置态字段清单
   （chartMain.zoneData + dsInfos.columns）。字段池同名冲突风险高（如多维销存报表）时，
   把配置态字段存 `templates/specs/<key>.har_fields.json`（数据文件，查询时按请求读取、
   无需重启；缺失会明确报错而非静默退化）。
2. **写报表指引** `.claude/skills/anta-bi/references/<key>.md`：
   - 头部「报表连接 spec」小节：`report_spec` 块本体，键序 `key/card_name/page_id/
     candidate_page_ids/card_id/default_ds_id/dynamic_params/field_source_cdid/har_fields_file`，
     调用方从原样复制进模板（格式样板见 `retail_daily_kolon.md` 同名小节）；
   - 维度/度量清单、筛选字段、日期参数、已知缺陷、模板格式与示例、常用配方；
   - `anta-bi` SKILL.md 报表路由表加一行。
3. **冒烟验证**：MCP `export_report` 传含 `report_spec` 的最小查询；核对返回 CSV 表头
   与请求 metrics 一致（防静默丢列）、行数量级合理。
4. **交付**：git 提交（建议 `docs: add <key> report guide`，仅文档+可选 specs 数据文件）；
   调 MCP `submit_feedback` 报 `report_note`：新报表的特殊约定（筛选依赖/静默丢指标/
   日期参数口径），供维护者复核指引。

> 「内置子类」路径（写 `anta_scrap/reports/<name>.py` + config 注册 + 重启）仅用于维护
> 既有 6 报表；新报表一律走本纯文档流程，不改服务端。

## 上下文纪律

- 关键 BI 约定（Base64 header、referer、sourceCdId 必配、三种响应形态、静默丢指标）
  只在报错或不确定时 Read `references/onboard-cheatsheet.md`。
- 解析不出某 ID（如 sourceCdId 在 HAR 里找不到）→ 停下来问项目所有者，不要编造。

## 验收标准

指引的 spec 块可直接驱动 MCP `export_report` 导出非空 CSV、表头完整；另一个 agent
只读指引（不看代码）就能编出正确模板。
