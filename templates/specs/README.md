# specs/：新报表的 HAR 字段数据文件

`anta-bi-onboard` 产出：`<key>.har_fields.json` = 从 HAR 抠出的完整配置态 zone item 数组
（含 metric 必备的 fieldFormat），供报表指引「报表连接 spec」小节的 `har_fields_file` 引用
（相对项目根路径 `templates/specs/<key>.har_fields.json`）。数据文件按请求读取：
**加文件即生效，无需改代码或重启服务**；缺失时查询会明确报错（不静默退化）。
