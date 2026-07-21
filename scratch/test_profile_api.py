import os
import sys
import httpx
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import DOUYIN_API_BASE

def main():
    aweme_id = "7348987114674719011"
    
    with httpx.Client(timeout=30.0) as client:
        # Test 1: fetch_one_video
        r1 = client.get(f"{DOUYIN_API_BASE}/api/douyin/web/fetch_one_video", params={"aweme_id": aweme_id})
        print("Status r1:", r1.status_code)
        print("Root keys:", list(r1.json().keys()))
        data = r1.json().get("data", {})
        if isinstance(data, dict):
            print("Data keys:", list(data.keys()))
            aweme_detail = data.get("aweme_detail", {})
            if isinstance(aweme_detail, dict):
                print("Aweme detail keys:", list(aweme_detail.keys()))
                video = aweme_detail.get("video", {})
                play_addr = video.get("play_addr", {}).get("url_list", []) if isinstance(video, dict) else []
                print("Play addr count:", len(play_addr))
                if play_addr:
                    print("URL:", play_addr[0][:100])

if __name__ == "__main__":
    main()
