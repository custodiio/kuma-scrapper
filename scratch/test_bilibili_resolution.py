import sys
import os
import io
import asyncio

# Fix encoding para Windows (caracteres chineses/emojis)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Adiciona a pasta raiz e a pasta douyin_api ao PATH
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "douyin_api"))

# Muda o diretório de trabalho para douyin_api para que os crawlers achem seus configs
os.chdir(os.path.join(project_root, "douyin_api"))

from crawlers.hybrid.hybrid_crawler import HybridCrawler

async def test():
    crawler = HybridCrawler()
    url = "https://www.bilibili.com/video/BV1M1421t7hT"
    print(f"Testando resolução para o vídeo: {url}")
    try:
        res = await crawler.hybrid_parsing_single_video(url, minimal=True)
        print("\n=== RESULTADOS DO PARSING ===")
        print(f"Título: {res.get('desc')}")
        print(f"Autor: {res.get('author', {}).get('name') if res.get('author') else 'N/A'}")
        
        video_data = res.get("video_data", {})
        video_url = video_data.get("nwm_video_url")
        audio_url = video_data.get("audio_url")
        
        if video_url:
            print("🟢 URL de vídeo obtida com sucesso!")
            print(f"Prefixo da URL do Vídeo: {video_url[:120]}...")
        else:
            print("🔴 Nenhuma URL de vídeo encontrada.")
            
        if audio_url:
            print("🟢 URL de áudio obtida com sucesso!")
            print(f"Prefixo da URL do Áudio: {audio_url[:120]}...")
        else:
            print("🔴 Nenhuma URL de áudio encontrada.")
            
    except Exception as e:
        print(f"❌ Erro durante o teste: {e}")

if __name__ == "__main__":
    asyncio.run(test())
