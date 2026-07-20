import sys
import os
import asyncio
import httpx

# Adiciona o diretório raiz ao path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src import database, search_scrapper

async def populate_refs():
    print("Iniciando varredura para preencher referências dos canais cadastrados...")
    database.init_db()
    
    channels = database.get_channels()
    if not channels:
        print("Nenhum canal cadastrado no banco de dados.")
        return
        
    print(f"Total de canais encontrados: {len(channels)}")
    
    for ch in channels:
        uid = ch["uid"]
        name = ch["name"]
        current_ref = ch.get("last_video_ref")
        
        print(f"\nCanal: {name} (UID: {uid}) | Ref Atual: {current_ref}")
        
        if not current_ref:
            print(f"Buscando vídeo recente para {name} no Bilibili...")
            try:
                latest_video = await search_scrapper.get_latest_video_for_channel(uid)
                if latest_video and latest_video.get("bvid"):
                    new_ref = latest_video["bvid"]
                    database.update_channel_ref(uid, new_ref)
                    print(f"✅ Canal {name} atualizado com a referência: {new_ref} - Título: {latest_video.get('title')}")
                else:
                    print(f"⚠️ Não foi possível encontrar nenhum vídeo recente para o canal {name}. Verifique se o UID é válido.")
            except Exception as e:
                print(f"❌ Erro ao buscar referência para {name}: {e}")
        else:
            print("Canal já possui referência de vídeo inicial.")

    print("\nVarredura concluída!")

if __name__ == "__main__":
    asyncio.run(populate_refs())
