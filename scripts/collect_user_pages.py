"""用户页面ID收集脚本。

当新用户遇到页面权限问题时，运行此脚本来收集该用户的页面ID，
然后将收集到的页面ID添加到对应报表的 candidate_page_ids 列表中。
"""

from anta_scrap.auth.session import resolve_credentials
from anta_scrap.client import AntaClient


def collect_user_pages(username: str) -> dict:
    """收集用户的所有页面ID

    Args:
        username: 用户名

    Returns:
        用户的页面ID信息
    """
    print(f"=== 收集用户 {username} 的页面信息 ===\n")

    try:
        # 解析用户凭证
        creds = resolve_credentials(username, None, None)
        client = AntaClient(creds)

        # 常见的安踏BI页面ID前缀
        # 根据HAR文件分析，页面ID通常是24位，以特定前缀开头
        common_page_patterns = [
            # 从已知用户收集到的页面ID
            "ne63f6cf08bbb40c28b814e8",  # 用户<工号A>的页面
            "e71d78d5bb6234d5ead169a2",  # 用户<工号B>的页面
        ]

        user_pages = {
            "username": username,
            "accessible_pages": [],
            "inaccessible_pages": []
        }

        print("测试常见页面模式...")
        for page_id in common_page_patterns:
            try:
                data = client.get_json(
                    f"/api/page/{page_id}",
                    headers={"referer": f"https://datav.anta.com/page/{page_id}"}
                )
                cards = data.get("response", data).get("cards", [])
                print(f"✓ 可访问页面: {page_id} (包含 {len(cards)} 个卡片)")
                user_pages["accessible_pages"].append({
                    "page_id": page_id,
                    "card_count": len(cards)
                })
            except Exception as e:
                print(f"✗ 无权访问: {page_id}")

        client.close()

        print(f"\n=== 收集结果 ===")
        print(f"可访问页面: {len(user_pages['accessible_pages'])} 个")
        print(f"不可访问页面: {len(user_pages['inaccessible_pages'])} 个")

        if user_pages["accessible_pages"]:
            print(f"\n建议将以下页面ID添加到相应报表的候选列表:")
            for page_info in user_pages["accessible_pages"]:
                print(f"  - {page_info['page_id']}")

        return user_pages

    except Exception as e:
        print(f"收集失败: {e}")
        return {}


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("使用方法: python collect_user_pages.py <username>")
        print("示例: python collect_user_pages.py <工号B>")
    else:
        username = sys.argv[1]
        result = collect_user_pages(username)

        # 保存结果到文件
        if result.get("accessible_pages"):
            import json
            filename = f"user_pages_{username}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n结果已保存到: {filename}")