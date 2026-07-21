import os
import sys
import httpx
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DOUYIN_API_BASE

def main():
    cookie = os.getenv("DOUYIN_COOKIE", "").strip()
    sec_uid = "MS4wLJABAAAAkkjkbeKi-prREzF-50m8b-uWz0kX0-9_t8o"
    url = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_user_post_videos"
    
    print(f"Cookie length: {len(cookie)}")
    print(f"Testing URL: {url}")

    params = {
        "sec_user_id": sec_uid,
        "max_cursor": 0,
        "count": 20
    }
    headers = {
        "cookie": cookie
    }

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, params=params, headers=headers)
        res_json = resp.json()
        print("Root JSON keys:", list(res_json.keys()))
        print("Code:", res_json.get("code"))
        print("Data payload:", str(res_json.get("data"))[:600])

if __name__ == "__main__":
    main()
