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
    cookie = os.getenv("DOUYIN_COOKIE", "").strip()
    
    if not cookie:
        print("⚠️ DOUYIN_COOKIE está vazio no .env principal.")
        return False
        
    config_path = project_root / "douyin_api" / "crawlers" / "douyin" / "web" / "config.yaml"
    if not config_path.exists():
        print(f"⚠️ config.yaml da API não encontrado em: {config_path}")
        return False
        
    try:
        # Lê o config.yaml original
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}
            
        # Atualiza o cookie
        token_mgr = config_data.setdefault("TokenManager", {})
        douyin = token_mgr.setdefault("douyin", {})
        headers = douyin.setdefault("headers", {})
        
        # Salva o cookie anterior para verificar se mudou
        old_cookie = headers.get("Cookie", "")
        
        if old_cookie == cookie:
            print("🔄 Cookie já está sincronizado. Nenhuma mudança necessária.")
            return True
            
        headers["Cookie"] = cookie
        
        # Grava o config.yaml modificado
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
            
        print("✅ DOUYIN_COOKIE sincronizado com sucesso no config.yaml do Evil0ctal!")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao sincronizar cookie: {e}")
        return False

if __name__ == "__main__":
    # Fix encoding para Windows (caracteres chineses/emojis)
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    success = sync()
    sys.exit(0 if success else 1)
