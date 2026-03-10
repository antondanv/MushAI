FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    requests \
    beautifulsoup4 \
    pandas \
    numpy \
    yfinance \
    matplotlib
