"""
快速检查 Gateway 路由配置
"""
import sys

# 检查路由文件
import os
router_files = [
    'app/routers/__init__.py',
    'app/routers/douyin.py',
    'app/main.py'
]

print("=== 检查 Gateway 路由配置 ===\n")

for file in router_files:
    if os.path.exists(file):
        print(f"✓ {file} 存在")
        if file == 'app/routers/douyin.py':
            with open(file, 'r') as f:
                content = f.read()
                if '/api/douyin' in content:
                    print(f"  - 包含 /api/douyin 路由")
                if 'DOUYIN_SERVICE_URL' in content:
                    print(f"  - 使用 DOUYIN_SERVICE_URL 环境变量")
    else:
        print(f"✗ {file} 不存在")

print("\n=== 检查环境变量 ===")
douyin_url = os.getenv('DOUYIN_SERVICE_URL', '未设置')
print(f"DOUYIN_SERVICE_URL = {douyin_url}")

print("\n=== 建议配置 ===")
print(f"DOUYIN_SERVICE_URL 应该设置为: http://localhost:8093")
