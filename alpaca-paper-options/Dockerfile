FROM python:3.12-slim
WORKDIR /app/alpaca-paper-options
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY . ./
RUN mkdir -p runs
CMD ["python", "scripts/paper_options_daily.py", "eod-report"]
