import sys
import os
import io
import asyncio
import httpx

# Fix encoding para Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Adiciona a pasta raiz e a pasta douyin_api ao PATH
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "douyin_api"))

# Muda o diretório de trabalho para douyin_api
os.chdir(os.path.join(project_root, "douyin_api"))

from crawlers.hybrid.hybrid_crawler import HybridCrawler

async def test():
    crawler = HybridCrawler()
    # Vídeo completo do Douyin (com ID de vídeo direto no link)
    url = "https://www.douyin.com/video/7298145681699622182"
    print(f"Testando resolução para o vídeo do Douyin: {url}")
    try:
        # Pega os cabeçalhos com os cookies sincronizados
        headers_data = await crawler.DouyinWebCrawler.get_douyin_headers()
        headers = headers_data.get("headers", {})
        
        res = await crawler.hybrid_parsing_single_video(url, minimal=True)
        print("\n=== RESULTADOS DO PARSING ===")
        print(f"Título: {res.get('desc')}")
        
        video_data = res.get("video_data", {})
        nwm_url = video_data.get("nwm_video_url")
        nwm_hq_url = video_data.get("nwm_video_url_HQ")
        
        print(f"nwm_video_url: {nwm_url[:100]}...")
        print(f"nwm_video_url_HQ: {nwm_hq_url[:100]}...")
        
        # Vamos fazer requisição HEAD/GET parcial para ver o Content-Length (tamanho do arquivo)
        async with httpx.AsyncClient() as client:
            for name, vurl in [("nwm_video_url", nwm_url), ("nwm_video_url_HQ", nwm_hq_url)]:
                if not vurl:
                    continue
                try:
                    # Alguns CDNs do Douyin rejeitam HEAD, então faremos um GET parcial (Range) ou limitando o timeout
                    resp = await client.get(vurl, headers=headers, timeout=10.0, follow_redirects=True)
                    size_mb = int(resp.headers.get("Content-Length", 0)) / (1024 * 1024)
                    print(f"Size of {name}: {size_mb:.2f} MB")
                except Exception as e_req:
                    print(f"Erro ao obter tamanho do {name}: {e_req}")
                    
    except Exception as e:
        print(f"❌ Erro durante o teste do Douyin: {e}")

if __name__ == "__main__":
    asyncio.run(test())
