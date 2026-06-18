"""
Script para sincronizar o DOUYIN_COOKIE do .env principal do projeto
com o config.yaml da API do Evil0ctal (douyin_api/crawlers/douyin/web/config.yaml).
"""

import os
import sys
import io
import yaml
from pathlib import Path
from dotenv import load_dotenv

def sync():
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    
    if not env_path.exists():
        print("⚠️ .env principal não encontrado. Crie um antes de continuar.")
        return False
        
    load_dotenv(env_path)
    
    # --- 1. Sincronização do DOUYIN_COOKIE ---
    douyin_cookie = os.getenv("DOUYIN_COOKIE", "").strip()
    douyin_success = True
    if not douyin_cookie:
        print("⚠️ DOUYIN_COOKIE está vazio no .env principal.")
        douyin_success = False
    else:
        config_path = project_root / "douyin_api" / "crawlers" / "douyin" / "web" / "config.yaml"
        if not config_path.exists():
            print(f"⚠️ config.yaml do Douyin não encontrado em: {config_path}")
            douyin_success = False
        else:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f) or {}
                
                token_mgr = config_data.setdefault("TokenManager", {})
                douyin = token_mgr.setdefault("douyin", {})
                headers = douyin.setdefault("headers", {})
                
                old_cookie = headers.get("Cookie", "")
                if old_cookie == douyin_cookie:
                    print("🔄 Cookie do Douyin já está sincronizado. Nenhuma mudança necessária.")
                else:
                    headers["Cookie"] = douyin_cookie
                    with open(config_path, "w", encoding="utf-8") as f:
                        yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
                    print("✅ DOUYIN_COOKIE sincronizado com sucesso no config.yaml do Evil0ctal!")
            except Exception as e:
                print(f"❌ Erro ao sincronizar cookie do Douyin: {e}")
                douyin_success = False

    # --- 2. Sincronização do BILIBILI_COOKIE ---
    bili_cookie = os.getenv("BILIBILI_COOKIE", "").strip()
    bili_success = True
    if not bili_cookie:
        print("⚠️ BILIBILI_COOKIE está vazio no .env principal.")
        bili_success = False
    else:
        bili_config_path = project_root / "douyin_api" / "crawlers" / "bilibili" / "web" / "config.yaml"
        if not bili_config_path.exists():
            print(f"⚠️ config.yaml do Bilibili não encontrado em: {bili_config_path}")
            bili_success = False
        else:
            try:
                with open(bili_config_path, "r", encoding="utf-8") as f:
                    bili_config_data = yaml.safe_load(f) or {}
                
                token_mgr_bili = bili_config_data.setdefault("TokenManager", {})
                bilibili = token_mgr_bili.setdefault("bilibili", {})
                headers_bili = bilibili.setdefault("headers", {})
                
                # Nota: a chave de cookie da API do Bilibili está em minúsculas: 'cookie'
                old_bili_cookie = headers_bili.get("cookie", "")
                if old_bili_cookie == bili_cookie:
                    print("🔄 Cookie do Bilibili já está sincronizado. Nenhuma mudança necessária.")
                else:
                    headers_bili["cookie"] = bili_cookie
                    with open(bili_config_path, "w", encoding="utf-8") as f:
                        yaml.dump(bili_config_data, f, default_flow_style=False, allow_unicode=True)
                    print("✅ BILIBILI_COOKIE sincronizado com sucesso no config.yaml do scrapper!")
            except Exception as e:
                print(f"❌ Erro ao sincronizar cookie do Bilibili: {e}")
                bili_success = False

    return douyin_success or bili_success


if __name__ == "__main__":
    # Fix encoding para Windows (caracteres chineses/emojis)
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    success = sync()
    sys.exit(0 if success else 1)
