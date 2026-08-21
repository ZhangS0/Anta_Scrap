# 用户页面ID维护指南

## 背景
由于安踏BI系统没有提供获取用户页面列表的API，不同用户可能被分配到不同的页面实例。系统采用候选页面列表机制来处理这种多用户页面差异。

## 当前状态

### 已知的用户页面ID
- **用户 <工号A>**: 页面 `ne63f6cf08bbb40c28b814e8`
- **用户 <工号B>**: 页面 `e71d78d5bb6234d5ead169a2`

### 各报表的候选页面列表

#### KOLON零售日报 (`retail_daily_kolon`)
```python
class RetailDailyKolonReport(BaseReport):
    page_id = "ne63f6cf08bbb40c28b814e8"  # 默认页面
    candidate_page_ids = ["e71d78d5bb6234d5ead169a2"]  # 候选页面
```

## 新用户页面添加流程

当新用户遇到"无权访问"错误时，按以下步骤添加其页面ID：

### 1. 收集新用户页面ID
```bash
python scripts/collect_user_pages.py <新用户名>
```

示例：
```bash
python scripts/collect_user_pages.py <工号B>
```

### 2. 分析收集结果
脚本会生成一个JSON文件，显示该用户可访问的页面：
```json
{
  "username": "<工号B>",
  "accessible_pages": [
    {
      "page_id": "e71d78d5bb6234d5ead169a2",
      "card_count": 20
    }
  ]
}
```

### 3. 更新报表代码
将新发现的页面ID添加到相应报表的 `candidate_page_ids` 列表中：

```python
class RetailDailyKolonReport(BaseReport):
    page_id = "ne63f6cf08bbb40c28b814e8"
    candidate_page_ids = [
        "e71d78d5bb6234d5ead169a2",  # 用户<工号B>
        # 添加新发现的页面ID...
    ]
```

### 4. 测试验证
重新运行新用户的查询，确认权限问题已解决：
```bash
python test_user_<新用户名>.py
```

## 自动发现机制

### 工作原理
1. **缓存优先**: 首先检查是否有已缓存的页面映射
2. **候选页面尝试**: 按顺序尝试候选页面列表
3. **自动缓存**: 成功的页面映射会自动缓存供后续使用

### 缓存位置
`~/user_page_mappings.json` (用户主目录)

### 缓存格式
```json
{
  "<工号B>": {
    "username": "<工号B>",
    "page_mappings": {
      "retail_dailykolon": "e71d78d5bb6234d5ead169a2"
    }
  }
}
```

## 常见问题

### Q: 为什么不能完全自动发现？
A: 安踏BI系统没有提供获取用户页面列表的API，只能基于已知页面ID进行尝试。

### Q: 如果新用户页面ID不在候选列表怎么办？
A: 系统会报"无权访问"错误，需要按上述流程手动添加新页面ID。

### Q: 候选页面列表的顺序重要吗？
A: 重要。系统会按顺序尝试，应该将最常用的页面放在前面。

### Q: 如何确定新用户的页面ID？
A: 运行 `collect_user_pages.py` 脚本，它会自动测试已知页面并找出新用户可访问的页面。

## 维护建议

1. **定期更新**: 当新增用户时，及时收集并添加其页面ID
2. **监控日志**: 关注"无权访问"错误，可能意味着需要添加新页面
3. **用户反馈**: 收集用户的错误信息，及时处理权限问题
4. **文档更新**: 每次添加新页面后，更新此文档