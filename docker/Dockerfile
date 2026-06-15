# Empacota: Evil0ctal Douyin API + scraper + notificador Telegram
FROM python:3.12-slim

WORKDIR /app

# Dependências do sistema
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

# Clona o Evil0ctal API
RUN git clone --depth=1 https://github.com/Evil0ctal/Douyin_TikTok_Download_API /app/douyin_api

# Dependências do Evil0ctal
RUN pip install --no-cache-dir -r /app/douyin_api/requirements.txt

# Dependências do scraper
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código do projeto
COPY src/ ./src/
COPY scripts/ ./scripts/

# Config do Douyin API (cookie injetado via env em runtime)
COPY docker/douyin_api_config.yaml /app/douyin_api/config.yaml

# Volume para o SQLite
VOLUME ["/data"]

# Entrypoint
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
