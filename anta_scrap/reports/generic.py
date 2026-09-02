"""通用报表实例：由模板内联 report_spec 装配，无需服务端注册。

MCP 是通用执行器：调用方模板带 report_spec 块（连接知识来自 anta-bi skill 指引的
「报表连接 spec」小节，由 anta-bi-onboard 维护）即可查询任意报表——新增报表是纯文档
动作，不改服务端代码、不需重启。内置 6 报表仍走子类别名（report: <key>），互不影响。

spec 键（camelCase 与 HAR / 内置子类常量逐字一致，文档可直接复制抓包产物）：
    page_id* / card_id*                       必填（24 位 ID）
    key                                       缓存键 + 报错指引名（默认 generic_{page_id前8位}）
    card_name                                 卡片名（payload name / 文件名兜底，默认取 key）
    default_ds_id                             多数据集报表的默认数据集
    candidate_page_ids                        页面发现候选页列表
    dynamic_params                            参数名 → {dpId*, valueType=DATE, sourceCdId}
    field_source_cdid                         筛选字段名 → sourceCdId（选择器卡片 ID）
    har_fields | har_fields_file              配置态字段第三源（二选一；file 相对项目根）
    reference                                 报错指引文件名（默认取 key）
    default_template                          默认查询块（可选，无运行时调用方）
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional

from anta_scrap.client import AntaClient
from anta_scrap.config import PROJECT_ROOT
from anta_scrap.models import QueryParams
from anta_scrap.reports.base import BaseReport
from anta_scrap.templates import template_to_params


class SpecError(ValueError):
    """report_spec 校验失败（缺必填键 / 类型不对 / har 文件不可读等）。"""


def _req_id(spec: dict, key: str) -> str:
    """必填 ID：非空校验后 str() 强转（防 YAML 把纯数字 ID 解析成 int）。"""
    v = spec.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        raise SpecError(f"缺少必填键 '{key}'（ID，从报表指引「报表连接 spec」小节复制）")
    return str(v).strip()


def _opt_id(spec: dict, key: str) -> Optional[str]:
    v = spec.get(key)
    if v is None or v == "":
        return None
    return str(v).strip()


def _norm_dynamic_params(raw) -> Dict[str, dict]:
    """归一化 dynamic_params：每项须含非空 dpId，valueType 缺省 DATE。"""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SpecError("dynamic_params 必须是映射: 参数名 → {dpId, valueType, sourceCdId}")
    out: Dict[str, dict] = {}
    for name, cfg in raw.items():
        if not isinstance(cfg, dict):
            raise SpecError(
                f"dynamic_params['{name}'] 必须是映射（含 dpId/valueType/sourceCdId），"
                f"当前是 {type(cfg).__name__}"
            )
        dp_id = cfg.get("dpId")
        if dp_id is None or str(dp_id).strip() == "":
            raise SpecError(f"dynamic_params['{name}'] 缺少 dpId（从报表指引复制完整定义）")
        out[str(name)] = {
            "dpId": str(dp_id).strip(),
            "valueType": str(cfg.get("valueType") or "DATE"),
            "sourceCdId": (str(cfg["sourceCdId"]).strip() if cfg.get("sourceCdId") else None),
        }
    return out


def _norm_field_source(raw) -> Dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SpecError("field_source_cdid 必须是映射: 筛选字段名 → sourceCdId")
    return {str(k): str(v).strip() for k, v in raw.items() if str(v).strip()}


def _resolve_har_items(spec: dict) -> Optional[List[dict]]:
    """解析 HAR 第三源：内联数组或项目根内数据文件；缺失/越界/解析失败均非静默。"""
    inline, path = spec.get("har_fields"), spec.get("har_fields_file")
    if inline is not None and path is not None:
        raise SpecError("har_fields 与 har_fields_file 只能二选一")
    if inline is not None:
        if not isinstance(inline, list):
            raise SpecError("har_fields 必须是配置态 zone item 数组（从抓包产物复制）")
        return inline
    if path is not None:
        if not isinstance(path, str) or not path.strip():
            raise SpecError("har_fields_file 必须是非空字符串（相对项目根的路径）")
        p = (PROJECT_ROOT / path.strip()).resolve()
        if not p.is_relative_to(PROJECT_ROOT.resolve()):
            raise SpecError(f"har_fields_file 必须位于项目根内: {path}")
        if not p.is_file():
            raise SpecError(
                f"har_fields_file 不存在: {p}（数据文件按请求读取、无需重启；"
                "核对相对项目根的路径，或改用 har_fields 内联）"
            )
        try:
            items = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            raise SpecError(f"har_fields_file 解析失败: {p}: {e}")
        if not isinstance(items, list):
            raise SpecError(f"har_fields_file 内容必须是数组: {p}")
        return items
    return None


class GenericReport(BaseReport):
    """由 report_spec 装配的报表实例；实例属性遮蔽类属性，与内置子类同构。"""

    def __init__(self, client: AntaClient, spec: dict, username: Optional[str] = None):
        if not isinstance(spec, dict):
            raise SpecError(f"report_spec 必须是映射块，当前是 {type(spec).__name__}")
        # 先完整校验（fail fast，无网络副作用），再装配
        page_id = _req_id(spec, "page_id")
        card_id = _req_id(spec, "card_id")
        key = _opt_id(spec, "key") or f"generic_{page_id[:8]}"
        cands = spec.get("candidate_page_ids") or []
        if not isinstance(cands, list):
            raise SpecError("candidate_page_ids 必须是页面 ID 列表")
        dps = _norm_dynamic_params(spec.get("dynamic_params"))
        fsrc = _norm_field_source(spec.get("field_source_cdid"))
        har_items = _resolve_har_items(spec)

        super().__init__(client, username=username)
        # 注意：dict/list 一律新建，绝不共享类属性或外部可变对象
        self._spec = dict(spec)
        self.page_id = page_id
        self.card_id = card_id
        self.key = key
        self.name = _opt_id(spec, "card_name") or key
        self.default_ds_id = _opt_id(spec, "default_ds_id")
        self.candidate_page_ids = [str(c).strip() for c in cands if str(c).strip()]
        self.DYNAMIC_PARAMS = dps
        self.FIELD_SOURCE_CDID = fsrc
        self.reference_key = _opt_id(spec, "reference") or key
        self.discovery_key = key  # 页面发现缓存键（防单类共键串缓存）
        self._har_items = har_items

    def default_template(self) -> QueryParams:
        """spec.default_template 块转 QueryParams（无运行时调用方，纯完整性）。"""
        tpl = dict(self._spec.get("default_template") or {})
        tpl.setdefault("card_name", self.name)
        return template_to_params(self, tpl)

    def _index_fields(self) -> None:
        """HAR 配置态字段优先索引、页面元数据 setdefault 回补（同内置复杂子类策略）。"""
        if self._har_items is None:
            return super()._index_fields()
        super()._index_fields()
        prior_by_name = dict(self._fields_by_name)
        prior_by_pair = dict(self._fields_by_name_and_ds)
        self._fields_by_name.clear()
        self._fields_by_name_and_ds.clear()
        for item in self._har_items:
            self._add_field_from_item(item, default_ds_id=self.default_ds_id)
        for k, v in prior_by_name.items():
            self._fields_by_name.setdefault(k, v)
        for k, v in prior_by_pair.items():
            self._fields_by_name_and_ds.setdefault(k, v)
