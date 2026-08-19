"""迪桑特品牌报表：零售客流分析 (page ld70cb7b48fed47ae980abf9 / card ee2c1006faac541f3aa7f227)。

特别说明（来自 HAR）：
1. 20250116之后默认去重客流、之前默认非去重客流；客流人次：非去重客流
2. 日区间自定义报表中2025-02-28对应的同期数据为2天（2024-02-28、2024-02-29）
3. 时段经过了+1处理，即"时段=10"代表 9:00~10:00之间的客流数
4. 客流数据限制 时段>=10且<=23
"""

from __future__ import annotations

from anta_scrap.models import DynamicParam, FieldDef, FilterItem, QueryParams
from anta_scrap.reports.base import BaseReport


class RetailTrafficDescenteReport(BaseReport):
    page_id = "ld70cb7b48fed47ae980abf9"
    card_id = "ee2c1006faac541f3aa7f227"
    name = "零售客流分析-迪桑特"
    # 从 HAR 抓取：数据集 ID
    default_ds_id = "b6ec68756a21646aa92f7edc"

    # 动态参数定义（HAR 抓取）：包含时段起止、日期范围
    # 起始小时/终止小时对应时段筛选（限制 10-23）
    DYNAMIC_PARAMS = {
        "起始小时": {
            "dpId": "s4d03508b087b49a8bb7ff1e",
            "valueType": "NUMBER",
            "sourceCdId": "m9141a23de06d4ffcb0911be",
        },
        "终止小时": {
            "dpId": "mfb0dc87547774569a6a0906",
            "valueType": "NUMBER",
            "sourceCdId": "l63a33b3d29cf4f56815b1ce",
        },
        "开始日期-户外-R02": {
            "dpId": "o944f3df227424be599bf18f",
            "valueType": "DATE",
            "sourceCdId": "f64ae6e09966f4e1b84ecbee",
        },
        "结束日期-户外-R02": {
            "dpId": "k66f14015af12438c86fe041",
            "valueType": "DATE",
            "sourceCdId": "vb6fd5ed7169e4a438919ade",
        },
    }

    # 字段 → filter 的 sourceCdId 映射（HAR 抓取）
    FIELD_SOURCE_CDID = {
        "品牌大区": "w4a443c48222c4437947bc2b",
        "区域": "v7037dbc0701340599835442",
        "城市_映射": "f3af0be61ab114f5aa16a1f0",
        "办事处": "h8284b4182164440b8e7654c",
        "店铺编码": "p87d7c407ceb94ae9918836c",
        "店铺名称": "rfd8f2cad94a749b3be9665c",
        "零售经理": "gb4cfa78f8a04425fb1c34fe",
        "店铺类型明细": "v1a790266eacb4b94843565a",
        "门店性质": "i89929abc02724375a31a439",
        "门店类型": "k15ccba6a2c32443cb018364",
        "店铺等级编码": "j743ad081491e45ddb11acc4",
        "经营类型": "nf0750019c9934987ab9095e",
        "集合店属性": "a15bd7d82d8ef4432953bcb8",
    }

    def default_template(self) -> QueryParams:
        """HAR 验证过的基础字段配置（按日客流统计）。"""
        rows = [
            self.field("日历日期"),
            self.field("区域"),
            self.field("店铺名称"),
        ]
        metrics = [
            self.field("流水"),
            self.field("流水同期"),
            self.field("流水同比"),
            self.field("店外客流"),
            self.field("进店客流"),
            self.field("店外客流同期"),
            self.field("进店客流同期"),
            self.field("进店率"),
        ]
        filters = [
            self._filter("区域", ["迪桑特-华东区", "迪桑特-华北区"]),
        ]
        dynamic_params = [
            self._dp("起始小时", "10"),
            self._dp("终止小时", "23"),
            self._dp("开始日期-户外-R02", "2026-08-01"),
            self._dp("结束日期-户外-R02", "2026-08-07"),
        ]
        return QueryParams(
            rows=rows,
            metrics=metrics,
            filters=filters,
            dynamic_params=dynamic_params,
            limit=50,
            offset=0,
            card_name=self.name,
        )

    def _filter(self, name: str, values: list) -> FilterItem:
        """构造 filter 并自动从 FIELD_SOURCE_CDID 注入 sourceCdId。"""
        fd = self.field(name)
        fd.source_cd_id = self.FIELD_SOURCE_CDID.get(name)
        return FilterItem(field=fd, values=values)

    def _dp(self, name: str, value: str) -> DynamicParam:
        """按名字取动态参数定义；名字必须在 DYNAMIC_PARAMS 里。"""
        if name not in self.DYNAMIC_PARAMS:
            avail = list(self.DYNAMIC_PARAMS.keys())
            raise KeyError(f"未找到动态参数 '{name}'，可选: {avail}")
        cfg = self.DYNAMIC_PARAMS[name]
        return DynamicParam(
            dp_id=cfg["dpId"],
            name=name,
            value=value,
            value_type=cfg.get("valueType", "DATE"),
            source_cd_id=cfg.get("sourceCdId"),
        )
