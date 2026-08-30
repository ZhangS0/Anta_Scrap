# BI 接入关键约定速查（onboard 报错时读）

提炼自项目 `CLAUDE.md`，只列接入新报表会踩的坑；系统细节以 CLAUDE.md 为准。

1. **凭证 header 必须是 Base64**：`user-id`/`x-dom-id` 都是 base64 值（如 `Z3VhbmJp`=guanbi），
   由 `client.py` 自动注入，子类不用管——但手工 curl 验证时必须带 Base64 形态。
2. **所有 `/api/*` 请求必须带 referer**：`client.py` 自动注入；不在 `/api/page/...` 路径上的
   接口（如 task 轮询）要显式传 `referer: https://datav.anta.com/page/{page_id}`。
3. **filter / dynamicParams 的 sourceCdId 不在页面元数据里**：必须从 HAR/请求负载硬编码进
   子类 `FIELD_SOURCE_CDID` / `DYNAMIC_PARAMS`；缺失时 BI 报 `卡片查询错误，错误详情: None.get`。
4. **配置态 metric 必须透传 raw**：`_har_fields.json` 里的字段项原样进索引（`FieldDef.raw`），
   精简掉 `fieldFormat` 等属性会触发 None.get。
5. **响应有三种形态**：标准 `{result, response}`；带 `raw-backend-response: TRUE` 头的包装态；
   任务接口裸态（`status` 在顶层）。`client._check_ok` / `poll_task` 已兼容，新代码别破坏。
6. **导出三步走**：`POST /api/write/file/{card_id}?typeOp=CSV` → 轮询 `GET /api/task/{id}` →
   `POST /api/export/file/common/{id}`（body 带 downloadFileName/time）。
7. **KOLON 系报表静默丢指标**：不支持的指标不报错、只从 CSV 表头消失；冒烟后必须核对表头。
8. **字段名逐字一致**：模板写中文字段名，运行时 `report.field(name)` 解析 fdId；
   同名异数据集用 `default_ds_id` 优先，仍歧义时 `field(name, ds_id=...)` 显式指定。
