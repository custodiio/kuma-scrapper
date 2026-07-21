import os
import sys
import httpx
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DOUYIN_API_BASE

def main():
    cookie = os.getenv("DOUYIN_COOKIE", "").strip()
    url_one = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_one_video"
    url_mix = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_user_mix_videos"
    url_user = f"{DOUYIN_API_BASE}/api/douyin/web/fetch_user_post_videos"

    headers = {"cookie": cookie}

    with httpx.Client(timeout=30.0) as client:
        # Test 1: One Video
        r1 = client.get(url_one, params={"aweme_id": "7348987114674719011"}, headers=headers)
        print("Fetch One Video status:", r1.status_code, "Data ok:", bool(r1.json().get("data")))

        # Test 2: Mix (Collection)
        r2 = client.get(url_mix, params={"mix_id": "7307044815158102068", "max_cursor": 0, "counts": 20}, headers=headers)
        d2 = r2.json().get("data", {})
        print("Fetch Mix Videos status:", r2.status_code, "Douyin status:", d2.get("status_code"), "Count:", len(d2.get("aweme_list") or []))

        # Test 3: User Post Videos
        r3 = client.get(url_user, params={"sec_user_id": "MS4wLJABAAAAkkjkbeKi-prREzF-50m8b-uWz0kX0-9_t8o", "max_cursor": 0, "count": 20}, headers=headers)
        d3 = r3.json().get("data", {})
        print("Fetch User Posts status:", r3.status_code, "Douyin status:", d3.get("status_code"), "Count:", len(d3.get("aweme_list") or []))

if __name__ == "__main__":
    main()
