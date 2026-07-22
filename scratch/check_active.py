import os, httpx, sys

DOUYIN_API_BASE = "http://localhost:5555"
video_url = "https://www.douyin.com/video/7661112899154300196"
output_path = "/tmp/teste_ep1.mp4"

print(f"Testando download: {video_url}")
print(f"API base: {DOUYIN_API_BASE}")

api_url = f"{DOUYIN_API_BASE}/api/download"

try:
    with httpx.Client(timeout=60.0) as client:
        with client.stream("GET", api_url, params={"url": video_url, "with_watermark": "false"}) as r:
            content_type = r.headers.get("Content-Type", "")
            print(f"Status: {r.status_code} | Content-Type: {content_type}")
            
            if r.status_code == 200 and "application/json" not in content_type:
                with open(output_path, "wb") as f:
                    total = 0
                    for chunk in r.iter_bytes(chunk_size=16384):
                        f.write(chunk)
                        total += len(chunk)
                print(f"✅ Baixado! {total:,} bytes -> {output_path}")
            else:
                data = r.read()
                print(f"❌ Resposta JSON/erro: {data[:500]}")
except Exception as e:
    print(f"❌ Exceção: {e}")
