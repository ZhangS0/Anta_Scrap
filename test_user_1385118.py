"""测试用户 <工号A> 的报表查询权限作为对比"""

from anta_scrap.auth.session import resolve_credentials
from anta_scrap.client import AntaClient
from anta_scrap.config import get_report_class
import yaml

def test_user_access(username: str):
    """测试指定用户的报表访问权限"""
    print(f"=== 测试用户 {username} 的报表访问权限 ===\n")

    try:
        # 1. 解析凭证（使用缓存的JWT）
        print("1. 解析用户凭证...")
        creds = resolve_credentials(username, None, None)
        print(f"   ✓ 凭证解析成功: user_id={creds.user_id}, dom_id={creds.dom_id}")

        # 2. 创建客户端
        print("\n2. 创建客户端...")
        client = AntaClient(creds)
        print("   ✓ 客户端创建成功")

        # 3. 测试KOLON报表
        print("\n3. 测试 KOLON 零售报表...")
        report_key = "retail_daily_kolon"
        rpt_class = get_report_class(report_key)
        rpt = rpt_class(client)
        print(f"   ✓ 报表实例: page_id={rpt.page_id}, card_id={rpt.card_id}")

        # 尝试获取元数据
        print("\n4. 获取报表元数据（权限检查关键点）...")
        try:
            meta = rpt.fetch_meta()
            print(f"   ✓ 元数据获取成功")
            print(f"   ✓ 页面卡片数: {len(meta.get('cards', []))}")
            print(f"\n✓✓✓ 用户 {username} 对报表 {report_key} 有访问权限 ✓✓✓")
            return True
        except Exception as e:
            print(f"   ✗ 元数据获取失败: {e}")
            return False

    except Exception as e:
        print(f"\n✗✗✗ 测试失败: {type(e).__name__}: {e} ✗✗✗")
        return False
    finally:
        if 'client' in locals():
            client.close()

if __name__ == "__main__":
    # 测试用户 <工号A> 作为对比
    success = test_user_access("<工号A>")