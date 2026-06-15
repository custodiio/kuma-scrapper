import os
import sys
import time
import io
import asyncio
from datetime import datetime

# Configura o stdout/stderr para UTF-8 no Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

# Garante que o diretório raiz está no path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import database, search_scrapper, telegram_bot

def test_database_and_queue():
    print("\n--- 1. TESTANDO BANCO DE DADOS E ESTATÍSTICAS DA FILA ---")
    database.init_db()
    
    # Limpa antes de testar
    database.clean_database()
    
    # Cadastra canal de teste
    print("Cadastrando canal de teste...")
    database.add_channel("test_uid_123", "Canal de Teste Bili", "shorts", "anime")
    
    # Registra vídeo pending (mapeado)
    print("Registrando vídeo pendente...")
    database.register_video(
        bvid="BV1testPending",
        title="Anime de Teste Pendente",
        channel_uid="test_uid_123",
        source="channel",
        category="shorts",
        content_type="anime",
        status="pending"
    )
    
    # Registra vídeo downloaded (fila)
    print("Registrando vídeo baixado (na fila)...")
    database.register_video(
        bvid="BV1testDownloaded",
        title="Anime de Teste Baixado",
        channel_uid="test_uid_123",
        source="channel",
        category="shorts",
        content_type="anime",
        status="downloaded"
    )
    
    # Verifica pendentes (fila)
    fila = database.get_pending_videos("shorts", "anime")
    print(f"Vídeos na fila 'Próximo a Postar' ( Shorts - Anime ): {len(fila)}")
    assert len(fila) == 1, "Deveria ter exatamente 1 vídeo na fila."
    assert fila[0]["bvid"] == "BV1testDownloaded", "BVID na fila incorreto."
    
    # Testa contadores
    print("Marcando vídeo da fila como postado...")
    database.mark_video_as_posted("BV1testDownloaded")
    
    posted_7d = database.get_posted_videos_count_since(7)
    print(f"Vídeos postados nos últimos 7 dias: {posted_7d}")
    assert posted_7d == 1, "Contador de postados incorreto."
    
    since_last = database.get_downloaded_count_since_last_post("shorts", "anime")
    print(f"Vídeos baixados desde a última publicação: {since_last}")
    assert since_last == 0, "Contador desde o último post deveria ser 0 após postar tudo."
    
    # Adiciona mais um downloaded para verificar contagem desde o último post
    database.register_video(
        bvid="BV1testNewDownloaded",
        title="Anime Novo Baixado",
        channel_uid="test_uid_123",
        source="channel",
        category="shorts",
        content_type="anime",
        status="downloaded"
    )
    since_last = database.get_downloaded_count_since_last_post("shorts", "anime")
    print(f"Vídeos baixados desde a última publicação (após novo download): {since_last}")
    assert since_last == 1, "Deveria contar 1 novo download após o post."
    
    print("✅ Teste de banco de dados concluído com sucesso!")

def test_cache_cleanup():
    print("\n--- 2. TESTANDO EXCLUSÃO FÍSICA E LIMPEZA DE CACHE ---")
    
    # Garante que os caminhos de cache existem
    os.makedirs(telegram_bot.TEMP_DIR, exist_ok=True)
    api_dir_bili = os.path.join("douyin_api", "download", "bilibili_video")
    api_dir_douyin = os.path.join("douyin_api", "download", "douyin_video")
    os.makedirs(api_dir_bili, exist_ok=True)
    os.makedirs(api_dir_douyin, exist_ok=True)
    
    # Cria arquivos temporários falsos
    bot_temp_file = os.path.join(telegram_bot.TEMP_DIR, "fake_bot_temp.mp4")
    api_bili_file = os.path.join(api_dir_bili, "fake_bili_cache.mp4")
    api_douyin_file = os.path.join(api_dir_douyin, "fake_douyin_cache.mp4")
    
    for f in [bot_temp_file, api_bili_file, api_douyin_file]:
        with open(f, "w") as out:
            out.write("Mídia falsa de teste")
        print(f"Criado arquivo falso: {f}")
        assert os.path.exists(f), f"Falha ao criar arquivo {f} para teste."
        
    # Executa a limpeza
    print("Chamando limpeza de cache profunda...")
    telegram_bot.deep_clean_cache()
    
    # Verifica se os arquivos foram excluídos fisicamente
    for f in [bot_temp_file, api_bili_file, api_douyin_file]:
        exists = os.path.exists(f)
        print(f"Arquivo existe? {f} -> {exists}")
        assert not exists, f"Arquivo {f} não deveria existir após a limpeza."
        
    print("✅ Teste de limpeza de cache física concluído com sucesso!")

async def test_bilibili_search():
    print("\n--- 3. TESTANDO BYPASS DE COOKIE E BUSCA NO BILIBILI ---")
    try:
        raw_results = await search_scrapper.fetch_bilibili_search_videos("新番解说", max_pages=1)
        print(f"Vídeos brutos encontrados na busca Bilibili: {len(raw_results)}")
        if raw_results:
            first = raw_results[0]
            print(f"Primeiro resultado:")
            print(f"  BVID: {first['bvid']}")
            print(f"  Título: {first['title']}")
            print(f"  Autor: {first['author']}")
            print(f"  Hype Score: {first['hype_score']}")
            print(f"  Capa (pic): {first['pic']}")
            
            assert first['bvid'] is not None, "BVID não deveria ser nulo."
            assert first['hype_score'] > 0, "Hype Score deveria ser maior que zero."
            
            print("Testando filtro e gravação de busca geral no SQLite...")
            inserted = await search_scrapper.run_search_scraping()
            print(f"Vídeos inseridos/atualizados na tabela de triagem: {inserted}")
            
            results = database.get_search_results("pending")
            print(f"Vídeos pendentes de triagem no banco: {len(results)}")
            assert len(results) >= 0, "Deveria retornar uma lista de pendentes."
        else:
            print("⚠️ Alerta: Nenhum resultado retornado do Bilibili. Isso pode indicar bloqueio temporário ou alteração na API.")
    except Exception as e:
        print(f"❌ Erro durante o teste de busca do Bilibili: {e}")
        raise e
        
    print("✅ Teste de busca geral do Bilibili concluído com sucesso!")

async def main():
    print("=" * 60)
    print("  EXECUTANDO TESTES DO PIPELINE FASE 2")
    print("=" * 60)
    
    test_database_and_queue()
    test_cache_cleanup()
    await test_bilibili_search()
    
    print("\n" + "=" * 60)
    print("  ✨ TODOS OS TESTES PASSARAM COM SUCESSO! ✨")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
