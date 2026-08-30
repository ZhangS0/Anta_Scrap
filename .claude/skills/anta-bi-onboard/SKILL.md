---
name: anta-bi-onboard
description: anta-bi skill 的辅助维护 skill，专门为其添加新的可查询报表。当用户提供完整查询 HAR / 查询参数 / 指标说明（可选），要求把某个安踏 BI 报表接入 anta-bi 查询体系时使用。产出报表子类、注册、库级模板与字段指引。
---

# anta-bi-onboard：为 anta-bi 添加新报表

把用户交付的 BI 报表（完整查询 HAR + 查询参数 + 指标说明可选）接入 anta-bi 查询体系。
**这是仓库工程任务**：在项目仓库 checkout 内执行（无 checkout 先 `git clone` 并**保留**目录）；
产物以 git 提交交付项目所有者，服务端部署重启后生效。

## 输入清单（缺项先向用户索要）

| 输入 | 必需 | 用途 |
|---|---|---|
| 完整查询过程 HAR | ✅ | 页面/卡片/数据集 ID、配置态字段、响应形态 truth |
| 查询参数 txt（请求负载） | ✅ | DYNAMIC_PARAMS、FIELD_SOURCE_CDID、payload 结构 |
| 指标说明 xlsx/md | 可选 | 字段业务口径，写进 skill 指引 |

## 七步流程

1. **解析抓取**：从 HAR/参数文件抠出——`page_id`（页面 URL `ne…/we…` 段）、`card_id`、
   主数据集 `default_ds_id`、`DYNAMIC_PARAMS`（dpId/valueType/sourceCdId）、
   `FIELD_SOURCE_CDID`（filter 字段名 → 选择器卡片 ID）、配置态字段清单
   （chartMain.zoneData + dsInfos.columns）。存 `anta_scrap/reports/<name>_har_fields.json`。
2. **写报表子类** `anta_scrap/reports/<name>.py`：抄现有子类结构（page_id/card_id/name/
   default_ds_id/DYNAMIC_PARAMS/FIELD_SOURCE_CDID/default_template + `_filter`/`_dp` helper）。
   页面字段池同名冲突风险高（如多维销存报表）时重写 `_index_fields()`：HAR 字段最高优先。
3. **注册**：`anta_scrap/config.py:get_report_registry()` 加 import + 一行映射。
4. **库级模板**：根 `templates/<name>.default.yaml`（最小可用查询）+
   `<name>.reference.yaml`（全字段注释态，含 fdId）。注意这是**库级**模板，与 workspace 报告任务无关。
5. **skill 指引**：`anta-bi` skill 增 `references/<name>.md`（字段清单/筛选/日期参数/已知缺陷）
   + 其 SKILL.md 报表路由表加一行。
6. **冒烟验证**：MCP `export_report` 或 `anta-cli export -t <name>.default` 跑最小查询；
   核对返回 CSV 表头与请求 metrics 一致（防静默丢列）、行数量级合理。
7. **交付**：git 提交（建议 `feat: add <name> report`），告知所有者部署重启；
   指引条目同步给用户侧 skill 分发。随后调 MCP `submit_feedback` 报 `report_note`：
   新报表的特殊约定（筛选依赖/静默丢指标/日期参数口径），供维护者更新字段指引。

## 上下文纪律

- 关键 BI 约定（Base64 header、referer、sourceCdId 必配、三种响应形态、静默丢指标）
  只在报错或不确定时 Read `references/onboard-cheatsheet.md`。
- 解析不出某 ID（如 sourceCdId 在 HAR 里找不到）→ 停下来问项目所有者，不要编造。

## 验收标准

新报表出现在 registry、默认模板能导出非空 CSV、表头完整、anta-bi 指引可让另一个 agent
不看代码就编出正确模板。
