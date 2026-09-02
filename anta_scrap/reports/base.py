"""报表抽象基类。

新增报表只需继承 BaseReport 并设置：
    page_id、card_id、name（卡片名，HAR 里 zoneFilter 同级的 name 字段）
可选重写：
    default_template() —— 返回该报表的默认 QueryParams（作为本地 YAML 模板的兜底）

字段名 → fdId 的映射通过 fetch_meta() 拉一次页面元数据并缓存到实例。
支持多用户页面自动发现：不同用户可能被分配到不同的页面实例。
"""

from __future__ import annotations

import difflib
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from anta_scrap.client import AntaClient
from anta_scrap.models import FieldDef, QueryParams


class BaseReport(ABC):
    page_id: str = ""
    card_id: str = ""
    name: str = ""  # 卡片名（写入 payload 的 name 字段）
    default_ds_id: Optional[str] = None  # 多数据集报表的默认数据集

    # 候选页面ID列表：用于多用户页面自动发现
    # 第一个是默认页面，其余是备用页面
    candidate_page_ids: List[str] = []

    # GenericReport（模板内联 report_spec）注入用；内置子类保持 None → 走原派生逻辑
    reference_key: Optional[str] = None  # 字段报错指引文件名（不含 .md）
    discovery_key: Optional[str] = None  # 页面发现缓存键

    # 字段名后缀 → meta_type 的映射（用于解析元数据）
    META_TYPE_DIM = "DIM"
    META_TYPE_METRIC = "METRIC"

    def __init__(self, client: AntaClient, username: Optional[str] = None):
        self.client = client
        self.username = username  # 当前用户名，用于页面自动发现
        self._meta: Optional[dict] = None
        self._fields_by_name: Dict[str, FieldDef] = {}
        self._fields_by_name_and_ds: Dict[tuple, FieldDef] = {}
        self._effective_page_id: Optional[str] = None  # 实际使用的页面ID

    # ---------- 子类必须提供 ----------

    @abstractmethod
    def default_template(self) -> QueryParams:
        """该报表的默认字段+条件组合（CLI/库在不指定模板时用）。"""

    # ---------- 页面自动发现 ----------

    def _discover_page_id(self) -> str:
        """自动发现用户对当前报表的正确页面ID"""
        if not self.username:
            # 没有用户名，使用默认页面
            return self.page_id

        try:
            from anta_scrap.auth.page_discovery import get_page_discovery_service
            discovery_service = get_page_discovery_service()

            # 获取报表名称（用于缓存键）；GenericReport 用注入的 discovery_key
            report_name = self.discovery_key or self.__class__.__name__.replace("Report", "").replace("Retail", "retail_").lower()

            # 构建候选页面列表
            candidates = [self.page_id] + getattr(self, "candidate_page_ids", [])

            # 自动发现正确的页面ID
            discovered_page_id = discovery_service.discover_page_id(
                client=self.client,
                username=self.username,
                report_name=report_name,
                card_id=self.card_id,
                candidate_pages=candidates
            )

            self._effective_page_id = discovered_page_id
            return discovered_page_id

        except ImportError:
            # 如果页面发现模块不可用，使用默认页面
            return self.page_id
        except Exception as e:
            # 页面发现失败，使用默认页面
            print(f"页面发现失败，使用默认页面: {e}")
            return self.page_id

    @property
    def effective_page_id(self) -> str:
        """获取实际使用的页面ID（考虑用户特定的页面）"""
        if self._effective_page_id is None:
            self._effective_page_id = self._discover_page_id()
        return self._effective_page_id

    # ---------- 字段元数据 ----------

    def fetch_meta(self, force: bool = False) -> dict:
        """调 /api/page/{page_id} 拿页面元数据并缓存。"""
        if self._meta is None or force:
            # 使用实际发现的页面ID
            page_to_use = self.effective_page_id

            data = self.client.get_json(
                f"/api/page/{page_to_use}",
                headers={"referer": f"https://datav.anta.com/page/{page_to_use}"},
            )
            self._meta = data.get("response", data)
            self._index_fields()
        return self._meta

    def _index_fields(self) -> None:
        """建立 name → FieldDef 索引。

        字段定义来源（优先级从高到低）：
        1. card.content.meta.chartMain.zoneData.{row/column/metric}：用户在页面上配置过
           的字段，含 calculationType/isAggregated/fieldFormat 等 metric 必备属性
        2. dsInfos[*].columns：数据集字段池（含全部可选字段的 fdId/fdType/metaType）

        优先用 chartMain 里的"已配置态"，避免 metric 缺字段触发 BI 的 None.get。
        """
        self._fields_by_name.clear()
        self._fields_by_name_and_ds = {}
        meta = self._meta or {}

        # 1) 从 chartMain.zoneData.{row,column,metric} 抠已配置字段
        for c in meta.get("cards", []) or []:
            content = c.get("content") or {}
            if isinstance(content, str):
                try:
                    import json as _json
                    content = _json.loads(content)
                except Exception:
                    continue
            cm = (content.get("meta") or {}).get("chartMain") or {}
            zd = (cm.get("zoneData") or {})
            for bucket in ("row", "column", "metric"):
                for item in zd.get(bucket, []) or []:
                    self._add_field_from_item(item)

        # 2) 兜底：从 dsInfos.columns 补全（chartMain 里没的字段）
        for ds in meta.get("dsInfos", []) or []:
            ds_id = ds.get("dsId")
            for item in ds.get("columns", []) or []:
                if not isinstance(item, dict) or "fdId" not in item:
                    continue
                name = item.get("name") or item.get("alias") or item.get("nameTranslated")
                if not name or name in self._fields_by_name:
                    continue
                self._add_field_from_item(item, default_ds_id=ds_id)

    def _add_field_from_item(self, item: dict, default_ds_id: Optional[str] = None) -> None:
        if not isinstance(item, dict) or "fdId" not in item:
            return  # 占位项（如"度量名"）跳过
        name = item.get("name") or item.get("alias") or item.get("nameTranslated")
        if not name:
            return
        ds_id = item.get("dsId") or default_ds_id
        fd = FieldDef(
            fd_id=item["fdId"],
            name=name,
            fd_type=item.get("fdType", "STRING"),
            meta_type=item.get("metaType", self.META_TYPE_DIM),
            key=item.get("key"),
            aggr_type=item.get("aggrType"),
            ds_id=ds_id,
            source_cd_id=item.get("sourceCdId"),
            raw=item,
        )
        if name not in self._fields_by_name:
            self._fields_by_name[name] = fd
        self._fields_by_name_and_ds[(name, ds_id)] = fd

    def field(self, name: str, ds_id: Optional[str] = None) -> FieldDef:
        """按可读名字取字段定义；未加载到时先 fetch_meta。

        若多个数据集有同名字段，可传 ds_id 指定；否则优先用 default_ds_id，
        再退回首匹配。
        """
        if not self._fields_by_name:
            self.fetch_meta()
        ds_id = ds_id or getattr(self, "default_ds_id", None)
        if ds_id:
            fd = self._fields_by_name_and_ds.get((name, ds_id))
            if fd:
                return fd
        if name in self._fields_by_name:
            return self._fields_by_name[name]
        # 兜底：列出全部匹配的 (ds_id, fdId)
        cands = [(ds, fd.fd_id) for (n, ds), fd in self._fields_by_name_and_ds.items() if n == name]
        # 相近字段名候选（防调用方未读字段指引、盲猜字段名反复试错）
        close = difflib.get_close_matches(name, self._fields_by_name.keys(), n=5, cutoff=0.4)
        # 内置子类=模块名（registry key）；GenericReport=spec 注入的 reference_key
        ref_name = self.reference_key or type(self).__module__.rsplit(".", 1)[-1]
        raise KeyError(
            f"字段 '{name}' 未在报表 {self.card_id} 找到。"
            + (f" 但有 {len(cands)} 个同名异 ds 候选: {cands[:5]}" if cands else "")
            + (f" 相近字段: {close}。" if close else "")
            + f" 完整字段清单见 .claude/skills/anta-bi/references/{ref_name}.md"
        )

    # ---------- 构造 payload ----------

    def build_payload(self, params: QueryParams) -> dict:
        """把 QueryParams 翻译成 /api/write/file/{card_id} 的请求体。"""
        import uuid

        zd = {
            "row": [f.to_zone_item() for f in params.rows],
            "column": [f.to_zone_item() for f in params.columns],
            "metric": [f.to_zone_item() for f in params.metrics],
        }
        # column 默认占位"度量名"（HAR 验证：需带 key/nameTranslated/alias）
        if not zd["column"]:
            from anta_scrap.models import _gen_key
            zd["column"] = [{
                "name": "度量名",
                "metaType": "MPH",
                "key": _gen_key() + _gen_key(),  # HAR 中度量名的 key 较长
                "nameTranslated": "度量名",
                "alias": "度量名",
            }]

        return {
            "offset": params.offset,
            "limit": params.limit,
            "filters": [f.to_payload(self.card_id) for f in params.filters],
            "treeFilters": [],
            "dynamicParams": [dp.to_payload() for dp in params.dynamic_params],
            "dynamicFieldFilters": [],
            "combinationFilters": [],
            "layerTreeFilters": [],
            "headerSortings": None,
            "rowExpand": None,
            "sorting": [],
            "name": params.card_name or self.name,
            "zoneFilter": {
                "zoneData": zd,
                "sorting": [],
                "excludeConditionConfig": {
                    "allResultsAreZero": False,
                    "resultsSumAreZero": False,
                    "allResultsAreNull": False,
                },
            },
            "taskRequestId": str(uuid.uuid4()),
        }
