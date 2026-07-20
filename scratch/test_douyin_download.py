import sys
import os
import io
import asyncio
import httpx
import aiofiles

# Fix encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

async def test_download():
    # URL de reprodução do Douyin que gerou o 302 Redirect
    url = "https://aweme.snssdk.com/aweme/v1/play/?video_id=v0300fg10000d8aigmnog65j0v2cpq3g&ratio=1080p&line=0"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    temp_file = "scratch/temp_douyin_test.mp4"
    print(f"Iniciando download de teste de: {url}")
    print(f"Destino temporário: {temp_file}")
    
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, headers=headers, follow_redirects=True) as response:
                print(f"Status do request: {response.status_code}")
                # Imprime as informações de redirecionamento
                print("Histórico de redirecionamentos:")
                for r in response.history:
                    print(f"<- Redirect: {r.status_code} para {r.headers.get('Location')}")
                    
                response.raise_for_status()
                
                total_size = int(response.headers.get("Content-Length", 0))
                print(f"Tamanho do arquivo reportado pela CDN: {total_size / (1024 * 1024):.2f} MB")
                
                downloaded = 0
                async with aiofiles.open(temp_file, 'wb') as out_file:
                    async for chunk in response.aiter_bytes():
                        await out_file.write(chunk)
                        downloaded += len(chunk)
                
                print(f"Download concluído! Arquivo salvo com {downloaded / (1024 * 1024):.2f} MB")
                
        # Remove arquivo de teste se foi criado
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print("Arquivo temporário removido.")
            
    except Exception as e:
        print(f"❌ Erro no download do Douyin: {e}")

if __name__ == "__main__":
    asyncio.run(test_download())
