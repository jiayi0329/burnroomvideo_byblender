import os
import requests
import json
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 获取授权码
APP_KEY = os.getenv("DK_APPKEY")
BASE_URL = "https://api.4dkankan.com"

def test_connection():
    url = f"{BASE_URL}/scene/getSceneList"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": APP_KEY
    }
    
    # 请求体：获取第一页，每页10条记录
    payload = {
        "pageNum": 1,
        "pageSize": 10
    }
    
    print("正在连接 4DKankan 服务器验证授权码...")
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status() # 检查 HTTP 状态码
        
        data = response.json()
        if data.get("code") == 0:
            print("✅ 鉴权成功！服务器返回数据：")
            # 格式化打印返回的部分场景列表数据
            print(json.dumps(data.get("data", {}), indent=2, ensure_ascii=False))
        else:
            print(f"❌ 鉴权失败，错误信息: {data.get('message')}")
            
    except Exception as e:
        print(f"❌ 请求发生异常: {e}")

if __name__ == "__main__":
    # 确保你已经安装了 requests 和 python-dotenv 库
    # pip install requests python-dotenv
    test_connection()