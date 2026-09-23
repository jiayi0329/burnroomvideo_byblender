from fastapi import FastAPI, HTTPException
import os
import requests
import urllib.request
import json  # 新增了 json 库用来保存文件

app = FastAPI(title="火灾蔓延视频生成系统 API")

BASE_URL = "https://api.4dkankan.com"
APP_KEY = os.getenv("DK_APPKEY")

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": APP_KEY
}

@app.get("/")
def read_root():
    return {"status": "Backend is running!", "appkey_loaded": bool(APP_KEY)}

@app.get("/api/scenes")
def get_all_scenes():
    url = f"{BASE_URL}/scene/getSceneList"
    payload = {"pageNum": 1, "pageSize": 50}
    response = requests.post(url, headers=HEADERS, json=payload).json()
    if response.get("code") == 0:
        scenes = [{"场景名称": item.get("sceneName"), "sceneCode": item.get("sceneCode")} for item in response.get("data", {}).get("list", [])]
        return {"status": "success", "总数量": response["data"]["total"], "场景列表": scenes}
    raise HTTPException(status_code=400, detail="获取失败")

@app.get("/api/download_scene/{scene_code}")
def download_scene_files(scene_code: str):
    '''终极版：下载场景全景图、模型，并额外保存点位信息 points.json'''
    
    save_dir = f"/app/data/{scene_code}"
    os.makedirs(save_dir, exist_ok=True)
    downloaded_files = []

    try:
        # 1. 下载全景图
        pano_url = f"{BASE_URL}/scene/getScenePanorama"
        pano_res = requests.post(pano_url, headers=HEADERS, json={"sceneCode": scene_code}).json()
        if pano_res.get("code") == 0 and pano_res.get("data"):
            for link in pano_res["data"]:
                filename = link.split("/")[-1]
                filepath = os.path.join(save_dir, filename)
                if not os.path.exists(filepath): # 如果已经下载过就不重复下载了，节省时间
                    urllib.request.urlretrieve(link, filepath)
                downloaded_files.append(f"全景图已存: {filename}")

        # 2. 下载模型文件
        obj_url = f"{BASE_URL}/scene/getSceneObj"
        obj_res = requests.post(obj_url, headers=HEADERS, json={"sceneCode": scene_code}).json()
        if obj_res.get("code") == 0 and obj_res.get("data"):
            for link in obj_res["data"]:
                filename = link.split("/")[-1]
                filepath = os.path.join(save_dir, filename)
                if not os.path.exists(filepath):
                    urllib.request.urlretrieve(link, filepath)
                downloaded_files.append(f"模型已存: {filename}")

        # 3. 获取并保存点位信息 (新增环节！)
        point_url = f"{BASE_URL}/scene/getScenePointInfo"
        point_res = requests.post(point_url, headers=HEADERS, json={"sceneCode": scene_code}).json()
        if point_res.get("code") == 0 and point_res.get("data"):
            points_path = os.path.join(save_dir, "points.json")
            # 把返回的数据存成 json 文件
            with open(points_path, "w", encoding="utf-8") as f:
                json.dump(point_res["data"], f, ensure_ascii=False, indent=2)
            downloaded_files.append("🎯 点位信息已存: points.json")

        return {
            "status": "所有资产获取成功！", 
            "sceneCode": scene_code, 
            "详细信息": downloaded_files
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载过程中发生错误: {str(e)}")