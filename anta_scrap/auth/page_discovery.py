"""用户页面ID智能发现机制。

支持两种发现策略：
1. 从服务器获取用户真实页面列表（推荐）
2. 候选页面列表尝试（备用方案）
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from anta_scrap.client import AntaClient
from anta_scrap.config import USER_HOME


@dataclass
class UserPageMapping:
    """用户页面映射：存储每个用户各个报表的正确page_id"""
    username: str
    # report_name -> page_id 的映射
    page_mappings: Dict[str, str]

    def get_page_id(self, report_name: str, default_page_id: str) -> str:
        """获取指定报表的page_id，如果没有记录则返回默认值"""
        return self.page_mappings.get(report_name, default_page_id)

    def set_page_id(self, report_name: str, page_id: str) -> None:
        """设置指定报表的page_id"""
        self.page_mappings[report_name] = page_id


class PageDiscoveryService:
    """页面发现服务：智能发现用户的正确页面ID"""

    def __init__(self, storage_path: Optional[Path] = None):
        """初始化页面发现服务

        Args:
            storage_path: 映射文件存储路径，默认为 ~/user_page_mappings.json
        """
        if storage_path is None:
            storage_path = Path.home() / "user_page_mappings.json"
        self.storage_path = storage_path
        self.mappings: Dict[str, UserPageMapping] = {}
        self._load_mappings()

    def _load_mappings(self) -> None:
        """从文件加载用户页面映射"""
        if not self.storage_path.exists():
            return

        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            for username, mapping_data in data.items():
                self.mappings[username] = UserPageMapping(
                    username=username,
                    page_mappings=mapping_data.get("page_mappings", {})
                )
        except (json.JSONDecodeError, TypeError) as e:
            print(f"警告：加载用户页面映射失败: {e}")

    def _save_mappings(self) -> None:
        """保存用户页面映射到文件"""
        data = {
            username: asdict(mapping)
            for username, mapping in self.mappings.items()
        }
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.storage_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        try:
            self.storage_path.chmod(0o600)  # 保护敏感信息
        except OSError:
            pass

    def get_user_mapping(self, username: str) -> UserPageMapping:
        """获取用户的页面映射，如果不存在则创建新的"""
        if username not in self.mappings:
            self.mappings[username] = UserPageMapping(
                username=username,
                page_mappings={}
            )
        return self.mappings[username]

    def discover_page_id(
        self,
        client: AntaClient,
        username: str,
        report_name: str,
        card_id: str,
        candidate_pages: Optional[List[str]] = None
    ) -> str:
        """智能发现用户对指定报表的正确页面ID

        优先策略：
        1. 检查缓存
        2. 从服务器获取用户的真实页面列表
        3. 使用候选页面列表（备用）

        Args:
            client: BI客户端
            username: 用户名
            report_name: 报表名称
            card_id: 卡片ID（用于验证页面是否包含目标卡片）
            candidate_pages: 候选页面ID列表（备用方案）

        Returns:
            用户可以访问的正确页面ID
        """
        # 首先检查是否已有记录
        user_mapping = self.get_user_mapping(username)
        cached_page_id = user_mapping.get_page_id(report_name, None)
        if cached_page_id:
            # 验证缓存的页面ID是否仍然有效
            if self._validate_page_id(client, cached_page_id, card_id):
                print(f"使用缓存页面ID: {cached_page_id}")
                return cached_page_id
            else:
                # 缓存失效，移除记录
                print(f"缓存页面ID失效，重新发现...")
                user_mapping.page_mappings.pop(report_name, None)

        print(f"正在为用户 {username} 发现报表 {report_name} 的正确页面ID...")

        # 策略1: 从服务器获取用户的真实页面列表
        server_pages = self._fetch_user_pages_from_server(client)
        if server_pages:
            print(f"从服务器获取到 {len(server_pages)} 个页面")
            for page_id in server_pages:
                print(f"  验证服务器页面: {page_id}")
                if self._validate_page_id(client, page_id, card_id):
                    print(f"  ✓ 找到有效页面: {page_id}")
                    user_mapping.set_page_id(report_name, page_id)
                    self._save_mappings()
                    return page_id

        # 策略2: 使用候选页面列表（备用方案）
        if candidate_pages:
            print(f"尝试候选页面列表...")
            for page_id in candidate_pages:
                print(f"  验证候选页面: {page_id}")
                if self._validate_page_id(client, page_id, card_id):
                    print(f"  ✓ 找到有效页面: {page_id}")
                    user_mapping.set_page_id(report_name, page_id)
                    self._save_mappings()
                    return page_id

        # 如果所有策略都失败，返回默认页面（可能会报错）
        default_page = candidate_pages[0] if candidate_pages else ""
        print(f"  ⚠ 所有发现策略都失败，使用默认页面: {default_page}")
        return default_page

    def _fetch_user_pages_from_server(self, client: AntaClient) -> Optional[List[str]]:
        """从服务器获取用户的真实页面列表

        通过分析BI系统的API响应和页面结构，提取用户可访问的所有页面ID。

        Returns:
            用户可访问的页面ID列表，如果获取失败则返回None
        """
        try:
            # 策略1: 尝试从用户菜单/首页获取页面列表
            # 这里需要根据实际的BI系统API来调整
            menu_data = client.get_json("/api/user/menu", headers={"referer": "https://datav.anta.com/"})

            # 从菜单数据中提取页面ID
            page_ids = self._extract_page_ids_from_menu(menu_data)
            if page_ids:
                return page_ids

        except Exception as e:
            print(f"从服务器获取页面列表失败: {e}")

        # 策略2: 尝试从用户的工作空间/最近访问获取
        try:
            recent_data = client.get_json("/api/user/recent", headers={"referer": "https://datav.anta.com/"})
            page_ids = self._extract_page_ids_from_response(recent_data)
            if page_ids:
                return page_ids
        except Exception as e:
            print(f"从最近访问获取页面列表失败: {e}")

        return None

    def _extract_page_ids_from_menu(self, menu_data: dict) -> List[str]:
        """从菜单数据中提取页面ID

        BI系统的页面ID通常是24位字符，以特定前缀开头（如ne、e等）
        """
        page_ids = []

        def extract_from_dict(data):
            if isinstance(data, dict):
                # 查找可能的页面ID字段
                for key, value in data.items():
                    if key in ['pageId', 'page_id', 'id', 'url', 'link']:
                        if isinstance(value, str) and self._is_valid_page_id(value):
                            # 从URL中提取页面ID
                            page_id = self._extract_page_id_from_url(value)
                            if page_id and page_id not in page_ids:
                                page_ids.append(page_id)
                    else:
                        extract_from_dict(value)
            elif isinstance(data, list):
                for item in data:
                    extract_from_dict(item)

        extract_from_dict(menu_data)
        return page_ids

    def _extract_page_ids_from_response(self, response_data: dict) -> List[str]:
        """从API响应中提取页面ID"""
        page_ids = []

        def extract_from_data(data):
            if isinstance(data, dict):
                for value in data.values():
                    if isinstance(value, str) and self._is_valid_page_id(value):
                        page_id = self._extract_page_id_from_url(value)
                        if page_id and page_id not in page_ids:
                            page_ids.append(page_id)
                    elif isinstance(value, (dict, list)):
                        extract_from_data(value)
            elif isinstance(data, list):
                for item in data:
                    extract_from_data(item)

        extract_from_data(response_data)
        return page_ids

    def _is_valid_page_id(self, value: str) -> bool:
        """检查是否是有效的页面ID格式

        BI系统的页面ID通常是24位字符，包含数字和字母
        """
        # 移除URL前缀和后缀
        clean_value = self._extract_page_id_from_url(value)
        if not clean_value:
            return False

        # 检查长度和格式（24位字符，字母数字组合）
        return len(clean_value) == 24 and re.match(r'^[a-zA-Z0-9]+$', clean_value)

    def _extract_page_id_from_url(self, value: str) -> Optional[str]:
        """从URL或字符串中提取页面ID

        支持格式：
        - /page/ne63f6cf08bbb40c28b814e8
        - https://datav.anta.com/page/e71d78d5bb6234d5ead169a2
        - ne63f6cf08bbb40c28b814e8 (直接ID)
        """
        # 如果是完整的URL，提取路径部分
        if '/page/' in value:
            # 从URL中提取页面ID
            match = re.search(r'/page/([a-zA-Z0-9]{24})', value)
            if match:
                return match.group(1)

        # 如果本身就是24位的ID格式
        if len(value) == 24 and re.match(r'^[a-zA-Z0-9]+$', value):
            return value

        return None

    def _validate_page_id(self, client: AntaClient, page_id: str, card_id: str) -> bool:
        """验证页面ID是否可访问

        注意：不同用户的页面实例可能包含不同的卡片结构，
        所以这里只检查页面是否可访问，而不检查特定卡片是否存在。

        Args:
            client: BI客户端
            page_id: 待验证的页面ID
            card_id: 卡片ID（暂时不用于验证，保留参数用于兼容性）

        Returns:
            页面是否可访问
        """
        try:
            data = client.get_json(
                f"/api/page/{page_id}",
                headers={"referer": f"https://datav.anta.com/page/{page_id}"}
            )

            # 检查是否成功获取页面数据
            response_data = data.get("response", data)
            cards = response_data.get("cards", [])

            print(f"    页面可访问，包含卡片: {len(cards)} 个")

            return True

        except Exception as e:
            # 检查是否是权限错误
            error_msg = str(e)
            if "无权访问" in error_msg or "1004" in error_msg:
                print(f"    页面无权访问")
            else:
                print(f"    页面验证失败: {e}")
            return False

    def clear_user_cache(self, username: str) -> None:
        """清除指定用户的页面缓存"""
        if username in self.mappings:
            del self.mappings[username]
            self._save_mappings()


# 全局单例
_page_discovery_service: Optional[PageDiscoveryService] = None


def get_page_discovery_service() -> PageDiscoveryService:
    """获取全局页面发现服务实例"""
    global _page_discovery_service
    if _page_discovery_service is None:
        _page_discovery_service = PageDiscoveryService()
    return _page_discovery_service