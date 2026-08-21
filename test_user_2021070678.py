"""测试用户 <工号B> 的报表查询权限"""

from anta_scrap.auth.session import resolve_credentials
from anta_scrap.client import AntaClient
from anta_scrap.config import get_report_class
from anta_scrap.export import download, poll_task, trigger_export
from anta_scrap.templates import template_to_params
import yaml

def test_user_access(username: str):
    """测试指定用户的报表访问权限"""
    print(f"=== 测试用户 {username} 的报表访问权限 ===\n")

    try:
        # 1. 解析凭证（使用缓存的JWT）
        print("1. 解析用户凭证...")
        creds = resolve_credentials(username, None, None)
        print(f"   ✓ 凭证解析成功: user_id={creds.user_id}, dom_id={creds.dom_id}")
        print(f"   ✓ JWT过期时间: {creds.expires_at}")

        # 2. 创建客户端
        print("\n2. 创建客户端...")
        client = AntaClient(creds)
        print("   ✓ 客户端创建成功")

        # 3. 测试KOLON报表
        print("\n3. 测试 KOLON 零售报表...")
        report_key = "retail_daily_kolon"

        # 加载默认模板
        template_path = "templates/retail_daily_kolon.default.yaml"
        with open(template_path, 'r', encoding='utf-8') as f:
            template_yaml = f.read()

        tpl = yaml.safe_load(template_yaml)
        print(f"   ✓ 模板加载成功: {tpl['report']}")

        # 获取报表类
        rpt_class = get_report_class(report_key)
        print(f"   ✓ 报表类: {rpt_class.__name__}")

        # 创建报表实例（使用新的页面自动发现机制）
        rpt = rpt_class(client, username=username)
        print(f"   ✓ 报表实例: page_id={rpt.page_id}, card_id={rpt.card_id}")

        # 尝试获取元数据（这里可能暴露权限问题）
        print("\n4. 获取报表元数据（权限检查关键点）...")
        try:
            meta = rpt.fetch_meta()
            print(f"   ✓ 元数据获取成功")
            print(f"   ✓ 页面卡片数: {len(meta.get('cards', []))}")
        except Exception as e:
            print(f"   ✗ 元数据获取失败: {e}")
            if "权限" in str(e) or "permission" in str(e).lower() or "403" in str(e):
                print(f"   🔒 这可能是权限问题！")
            return False

        # 解析模板参数
        print("\n5. 解析模板参数...")
        try:
            params = template_to_params(rpt, tpl)
            print(f"   ✓ 参数解析成功: {len(params.rows)} 行, {len(params.metrics)} 指标")
        except Exception as e:
            print(f"   ✗ 参数解析失败: {e}")
            if "字段" in str(e) and "未找到" in str(e):
                print(f"   🔒 这可能是字段权限问题！用户可能看不到某些字段")
            return False

        # 尝试触发导出
        print("\n6. 尝试触发导出任务...")
        try:
            task_id = trigger_export(rpt, params)
            print(f"   ✓ 导出任务触发成功: task_id={task_id}")
        except Exception as e:
            print(f"   ✗ 导出任务触发失败: {e}")
            if "权限" in str(e) or "permission" in str(e).lower() or "403" in str(e):
                print(f"   🔒 这确认是权限问题！")
            return False

        print(f"\n✓✓✓ 用户 {username} 对报表 {report_key} 有完整访问权限 ✓✓✓")
        return True

    except Exception as e:
        print(f"\n✗✗✗ 测试失败: {type(e).__name__}: {e} ✗✗✗")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if 'client' in locals():
            client.close()

if __name__ == "__main__":
    # 测试用户 <工号B>
    success = test_user_access("<工号B>")

    if not success:
        print("\n建议检查：")
        print("1. 用户是否有该报表的访问权限")
        print("2. 用户是否能访问报表所需的所有字段")
        print("3. 用户的域权限设置是否正确")
    else:
        print("\n权限检查通过！")