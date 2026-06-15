"""
Script de teste inicial do Douyin Anime Scraper.
Valida cada componente do setup passo a passo.

Uso: python scripts/test_setup.py
"""

import sys
import os
import io
from pathlib import Path

# Fix encoding para Windows (caracteres chineses)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Adiciona a raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Cores para o terminal
class C:
    OK = "\033[92m"    # Verde
    WARN = "\033[93m"  # Amarelo
    FAIL = "\033[91m"  # Vermelho
    BOLD = "\033[1m"
    END = "\033[0m"

def ok(msg):   print(f"  {C.OK}[OK]{C.END}    {msg}")
def warn(msg): print(f"  {C.WARN}[WARN]{C.END}  {msg}")
def fail(msg): print(f"  {C.FAIL}[FAIL]{C.END}  {msg}")
def header(msg): print(f"\n{C.BOLD}{'='*50}\n  {msg}\n{'='*50}{C.END}")


def test_env():
    """Testa se o .env existe e tem as variáveis obrigatórias."""
    header("1. Verificando .env")

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        fail(f".env nao encontrado em {env_path}")
        print(f"\n  Copie o template:")
        print(f"  copy .env.example .env")
        print(f"  Depois preencha TELEGRAM_TOKEN e DOUYIN_COOKIE")
        return False

    ok(f".env encontrado: {env_path}")

    from dotenv import load_dotenv
    load_dotenv(env_path)

    erros = 0
    for var in ["TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]:
        val = os.getenv(var, "")
        if val and val != "":
            ok(f"{var} = {val[:15]}...")
        else:
            fail(f"{var} nao definido!")
            erros += 1

    cookie = os.getenv("DOUYIN_COOKIE", "")
    if cookie:
        ok(f"DOUYIN_COOKIE = {cookie[:30]}... ({len(cookie)} chars)")
        try:
            from scripts.sync_cookie import sync
            sync()
        except Exception as e:
            warn(f"Nao foi possivel sincronizar o cookie com a API: {e}")
    else:
        warn("DOUYIN_COOKIE vazio (necessario para busca real)")

    search = os.getenv("SEARCH_TERM", "")
    ok(f"SEARCH_TERM = {search or '(padrao: xin fan jie shuo)'}")

    return erros == 0


def test_database():
    """Testa criação e operações do banco SQLite."""
    header("2. Testando banco de dados SQLite")

    try:
        from src.database import init_db, save_video, already_seen, get_stats, mark_as_posted

        test_db = str(Path(__file__).resolve().parent.parent / "data" / "test_setup.db")
        conn = init_db(test_db)
        ok("Banco criado com sucesso")

        # Salva um vídeo de teste
        v = {
            "video_id": "test_001",
            "title": "Teste: Anime Recap EP1",
            "creator": "tester",
            "duration_s": 300,
            "likes": 1500,
            "url": "https://www.douyin.com/video/test_001",
            "published_at": "2025-06-10T00:00:00",
            "episode": 1,
            "search_term": "teste",
        }
        save_video(conn, v)
        ok("Video salvo no historico")

        # Verifica duplicata
        assert already_seen(conn, "test_001") == True
        assert already_seen(conn, "test_002") == False
        ok("Deteccao de duplicatas OK")

        # Marca como postado
        mark_as_posted(conn, "test_001")
        stats = get_stats(conn)
        assert stats["total"] == 1
        assert stats["postados"] == 1
        assert stats["ultimo_episodio"] == 1
        ok(f"Stats: {stats}")

        conn.close()
        os.remove(test_db)
        ok("Banco de teste limpo")
        return True

    except Exception as e:
        fail(f"Erro no banco: {e}")
        return False


def test_episode_detector():
    """Testa detecção de episódios em títulos chineses."""
    header("3. Testando detector de episodios")

    try:
        from src.episode_detector import extract_episode, is_continuation

        testes = [
            ("\u7b2c12\u96c6 \u52a8\u6f2b\u89e3\u8bf4", "di-12-ji", 12),
            ("\u6d77\u8d3c\u738b EP1089 \u7cbe\u5f69", "EP1089", 1089),
            ("[23] recap", "[23] pattern", 23),
            ("\u5492\u672f\u56de\u6218 #5", "#5 pattern", 5),
            ("12\u8bdd recap", "12hua pattern", 12),
            ("sem episodio aqui", "sem episodio", None),
        ]

        # Títulos reais com caracteres chineses
        testes_cn = []
        try:
            testes_cn = [
                ("\u7b2c12\u96c6 \u52a8\u6f2b\u89e3\u8bf4", "\u7b2c12\u96c6", 12),
                ("\u6d77\u8d3c\u738b EP1089 \u7cbe\u5f69\u7247\u6bb5", "EP1089", 1089),
            ]
        except Exception:
            pass

        erros = 0
        for titulo, desc, esperado in testes:
            resultado = extract_episode(titulo)
            if resultado == esperado:
                ok(f"'{desc}' -> EP {resultado}")
            else:
                fail(f"'{desc}' -> {resultado} (esperado: {esperado})")
                erros += 1

        for titulo, desc, esperado in testes_cn:
            resultado = extract_episode(titulo)
            if resultado == esperado:
                ok(f"'{desc}' -> EP {resultado}")
            else:
                fail(f"'{desc}' -> {resultado} (esperado: {esperado})")
                erros += 1

        # Testa continuação
        assert is_continuation(13, 12) == True
        assert is_continuation(15, 12) == False
        assert is_continuation(None, 12) == False
        ok("Deteccao de continuacao OK")

        return erros == 0

    except Exception as e:
        fail(f"Erro no detector: {e}")
        return False


def test_telegram():
    """Testa conexão com o bot Telegram."""
    header("4. Testando conexao Telegram")

    token = os.getenv("TELEGRAM_TOKEN", "")
    if not token:
        warn("TELEGRAM_TOKEN nao definido — pulando teste")
        return True

    try:
        import httpx

        resp = httpx.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        data = resp.json()

        if data.get("ok"):
            bot = data["result"]
            ok(f"Bot conectado: @{bot.get('username', '?')} ({bot.get('first_name', '?')})")
            return True
        else:
            fail(f"Telegram retornou erro: {data.get('description', '?')}")
            return False

    except Exception as e:
        fail(f"Erro ao conectar com Telegram: {e}")
        return False


def test_douyin_api():
    """Testa conexão com o Evil0ctal Douyin API."""
    header("5. Testando Evil0ctal Douyin API")

    api_base = os.getenv("DOUYIN_API_BASE", "http://localhost:5555")

    try:
        import httpx

        resp = httpx.get(f"{api_base}/", timeout=5)
        if resp.status_code == 200:
            ok(f"Evil0ctal API respondendo em {api_base}")
            return True
        else:
            warn(f"API retornou status {resp.status_code}")
            return True

    except httpx.ConnectError:
        warn(f"Evil0ctal API nao encontrada em {api_base}")
        print(f"\n  Para subir a API localmente:")
        print(f"  1. git clone https://github.com/Evil0ctal/Douyin_TikTok_Download_API douyin_api")
        print(f"  2. cd douyin_api")
        print(f"  3. pip install -r requirements.txt")
        print(f"  4. python main.py")
        print(f"\n  A API roda em http://localhost:5555")
        return False

    except Exception as e:
        fail(f"Erro: {e}")
        return False


def test_scrape_dry_run():
    """Faz um dry-run do scraper (sem enviar ao Telegram)."""
    header("6. Dry-run do Scraper")

    api_base = os.getenv("DOUYIN_API_BASE", "http://localhost:5555")

    try:
        import httpx
        httpx.get(f"{api_base}/", timeout=3)
    except Exception:
        warn("Evil0ctal API offline — pulando dry-run")
        return True

    try:
        from src.scraper import search_douyin, parse_video

        search_term = os.getenv("SEARCH_TERM", "\u65b0\u756a\u89e3\u8bf4")
        raw_videos = search_douyin(search_term, count=5)

        if not raw_videos:
            warn("Nenhum resultado retornado (cookie pode estar expirado ou invalido)")
            return False

        ok(f"{len(raw_videos)} videos encontrados para '{search_term}'")

        # Mostra os primeiros 3
        print(f"\n  Primeiros resultados:")
        for i, raw in enumerate(raw_videos[:3], 1):
            v = parse_video(raw, search_term)
            dur_min = v['duration_s'] // 60
            dur_sec = v['duration_s'] % 60
            tipo = "LONGO" if v['duration_s'] > 240 else "SHORT"
            ep_str = f" | EP {v['episode']}" if v.get('episode') else ""

            print(f"  {i}. [{tipo}] {v['title'][:50]}")
            print(f"     {dur_min}min {dur_sec:02d}s | {v['likes']} likes{ep_str}")
            print(f"     {v['url']}")
            print()

        return True

    except Exception as e:
        fail(f"Erro no dry-run: {e}")
        return False


def main():
    print(f"\n{C.BOLD}{'#'*50}")
    print(f"  DOUYIN ANIME SCRAPER — TESTE DE SETUP")
    print(f"{'#'*50}{C.END}")

    results = {}
    results["env"]      = test_env()
    results["database"] = test_database()
    results["episodes"] = test_episode_detector()
    results["telegram"] = test_telegram()
    results["api"]      = test_douyin_api()
    results["scraper"]  = test_scrape_dry_run()

    # Resumo final
    header("RESUMO")
    total_ok = sum(1 for v in results.values() if v)
    total = len(results)

    for nome, passou in results.items():
        status = f"{C.OK}PASSOU{C.END}" if passou else f"{C.FAIL}FALHOU{C.END}"
        print(f"  {nome:15s} {status}")

    print(f"\n  {total_ok}/{total} testes passaram")

    if total_ok == total:
        print(f"\n  {C.OK}{C.BOLD}Tudo pronto! Rode: python scripts/run_scrape.py{C.END}")
    elif not results["api"]:
        print(f"\n  {C.WARN}Suba o Evil0ctal API para fazer o teste completo.{C.END}")
    elif not results["env"]:
        print(f"\n  {C.WARN}Configure o .env primeiro: copy .env.example .env{C.END}")

    return 0 if total_ok >= 4 else 1


if __name__ == "__main__":
    sys.exit(main())
