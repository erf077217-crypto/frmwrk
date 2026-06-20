FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    tmux \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN npm i -g opencode-ai

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/docker-entrypoint.sh

RUN useradd -m -u 1000 app && \
    mkdir -p /home/app/.local/share/opencode && \
    mkdir -p /home/app/.config/opencode && \
    mkdir -p /home/app/.cache/opencode && \
    chown -R app:app /home/app

USER app

EXPOSE 7777

ENTRYPOINT ["/app/docker-entrypoint.sh"]
