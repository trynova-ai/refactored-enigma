FROM python:3.11-slim

WORKDIR /app
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libatk1.0-0 libdrm2 libxkbcommon0 libpangocairo-1.0-0 libxcomposite1 \
        libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libgtk-3-0 libnss3 \
        libasound2 libxshmfence1 libegl1 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && playwright install --with-deps chromium

COPY . .

EXPOSE 5000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "5000"]
