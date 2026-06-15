#!/bin/bash
set -e

echo "▶ Iniciando Douyin API server..."
cd /app/douyin_api
python main.py &
API_PID=$!

# Aguarda o servidor subir (até 30s)
for i in $(seq 1 30); do
    if curl -sf http://localhost:5555/health > /dev/null 2>&1; then
        echo "✅ Douyin API pronta (porta 5555)"
        break
    fi
    sleep 1
done

echo "▶ Rodando scraper..."
cd /app
python scripts/run_scrape.py

echo "✅ Job concluído"
kill $API_PID 2>/dev/null || true
