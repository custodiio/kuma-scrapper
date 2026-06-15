import os
import sys
import httpx
import logging
from dotenv import load_dotenv

# Define logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Adiciona o diretório raiz ao path para poder importar src/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import media_processor, drive_uploader

def test_api_online():
    logger.info("=== Teste 1: Verificar se a API local está online ===")
    try:
        response = httpx.get("http://localhost:5555/docs", timeout=5.0)
        if response.status_code == 200:
            logger.info("🟢 API local está online na porta 5555!")
            return True
        else:
            logger.error(f"🔴 API respondeu com código HTTP {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"🔴 Falha ao conectar na API local: {e}")
        return False

def test_download_and_process():
    logger.info("\n=== Teste 2: Download e processamento de mídia com FFmpeg ===")
    
    # URL de teste curta do Bilibili (Azulsolitan)
    test_url = "https://www.bilibili.com/video/BV1W8411t7oz"
    api_url = "http://localhost:5555/api/download"
    
    os.makedirs("data/test_temp", exist_ok=True)
    temp_raw = "data/test_temp/raw_test.mp4"
    temp_cut = "data/test_temp/cut_test.mp4"
    temp_audio = "data/test_temp/audio_test.mp3"
    
    # Limpa arquivos de testes anteriores
    for p in [temp_raw, temp_cut, temp_audio]:
        if os.path.exists(p):
            try: os.remove(p)
            except: pass
            
    # 1. Realiza download
    logger.info(f"Baixando vídeo de teste via API local: {test_url}...")
    try:
        with httpx.Client(timeout=60.0) as client:
            with client.stream("GET", api_url, params={"url": test_url, "with_watermark": "false"}) as r:
                if r.status_code != 200:
                    logger.error(f"Erro HTTP {r.status_code} na API de Download")
                    return False
                with open(temp_raw, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
    except Exception as e:
        logger.error(f"Erro no download HTTP: {e}")
        return False
        
    if not os.path.exists(temp_raw) or os.path.getsize(temp_raw) == 0:
        logger.error("Download do vídeo falhou (arquivo vazio ou inexistente).")
        return False
        
    logger.info("🟢 Download de teste concluído com sucesso!")
    
    # 2. Testa leitura de duração (FFprobe)
    duration = media_processor.get_video_duration(temp_raw)
    logger.info(f"🟢 Duração lida pelo FFprobe: {duration:.2f} segundos.")
    if duration <= 0:
        logger.error("Duração inválida ou zero lida pelo FFprobe.")
        return False
        
    # 3. Testa corte (truncamento para 10 segundos para ver se o FFmpeg funciona)
    logger.info("Testando truncamento de vídeo com FFmpeg (10 segundos)...")
    cut_success = media_processor.truncate_video(temp_raw, temp_cut, seconds=10.0)
    if cut_success and os.path.exists(temp_cut):
        cut_duration = media_processor.get_video_duration(temp_cut)
        logger.info(f"🟢 Corte concluído com sucesso! Nova duração: {cut_duration:.2f}s (esperado: ~10s).")
    else:
        logger.error("Falha ao realizar corte do vídeo com FFmpeg.")
        return False
        
    # 4. Testa extração de áudio para MP3
    logger.info("Testando extração de áudio para MP3 com FFmpeg...")
    audio_success = media_processor.extract_audio(temp_cut, temp_audio)
    if audio_success and os.path.exists(temp_audio) and os.path.getsize(temp_audio) > 0:
        logger.info(f"🟢 Extração de áudio concluída com sucesso! Tamanho do MP3: {os.path.getsize(temp_audio)} bytes.")
    else:
        logger.error("Falha ao extrair áudio com FFmpeg.")
        return False
        
    # Limpa arquivos locais de teste para não poluir
    for p in [temp_raw, temp_cut, temp_audio]:
        if os.path.exists(p):
            try: os.remove(p)
            except: pass
            
    return True

def test_drive_auth():
    logger.info("\n=== Teste 3: Autenticação com o Google Drive ===")
    uploader = drive_uploader.DriveUploader()
    if uploader.service:
        logger.info("🟢 Autenticação no Google Drive via OAuth2 concluída com sucesso!")
        return True
    else:
        logger.error("🔴 Falha ao autenticar no Google Drive. Verifique as variáveis DRIVE_ em seu .env.")
        return False

def main():
    logger.info("Iniciando testes de integração do pipeline...")
    load_dotenv()
    
    api_ok = test_api_online()
    if not api_ok:
        logger.error("Abortando testes: a API local precisa estar online para rodar.")
        sys.exit(1)
        
    media_ok = test_download_and_process()
    drive_ok = test_drive_auth()
    
    if media_ok and drive_ok:
        logger.info("\n🟢 TODOS OS TESTES PASSARAM COM SUCESSO! O pipeline local está 100% operacional.")
        sys.exit(0)
    else:
        logger.error("\n🔴 ALGUNS TESTES FALHARAM. Verifique os logs acima para diagnosticar o problema.")
        sys.exit(1)

if __name__ == "__main__":
    main()
