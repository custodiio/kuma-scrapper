import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import scraper

def main():
    test_url = "https://www.douyin.com/video/7348987114674719011"
    out_file = os.path.join(PROJECT_ROOT, "scratch", "test_ep.mp4")
    res = scraper.download_douyin_video(test_url, out_file)
    print("Download result:", res)
    if os.path.exists(out_file):
        print("File size:", os.path.getsize(out_file))

if __name__ == "__main__":
    main()
