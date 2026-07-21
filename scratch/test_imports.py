import sys, os
sys.path.insert(0, "/app/scrapper_douyin")
sys.path.insert(0, "/home/ubuntu/apps/anime-pipeline")

# Testa se consegue importar o pipeline_controller
try:
    from bot.pipeline_controller import PipelineController
    print("✅ PipelineController importado com sucesso!")
except Exception as e:
    print(f"❌ Erro ao importar PipelineController: {e}")
    sys.exit(1)

# Testa se consegue importar o database do anime-pipeline
try:
    from bot import database as animerecap_db
    print("✅ database do AnimeRecap importado com sucesso!")
    print(f"  set_project_opts: {animerecap_db.set_project_opts}")
    print(f"  update_step: {animerecap_db.update_step}")
except Exception as e:
    print(f"❌ Erro ao importar database do AnimeRecap: {e}")

# Testa se a função get_animerecap_path retorna o caminho certo
from src import pipeline_integrator
path = pipeline_integrator.get_animerecap_path()
print(f"\n✅ AnimeRecap path detectado: {path}")
