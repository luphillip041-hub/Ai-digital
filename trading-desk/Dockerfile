FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/trading-desk

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . ./

RUN mkdir -p runs .cache memory

CMD ["python", "bot/discord_bot.py"]
