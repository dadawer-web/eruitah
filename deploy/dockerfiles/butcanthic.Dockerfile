# Python butcanthic runtime-only（离线 wheel 安装，不联网 pip install）
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libsm6 libxext6 libxrender-dev libgl1-mesa-glx \
        poppler-utils tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖（离线 wheel），利用 Docker 层缓存
COPY src/requirements.txt /tmp/requirements.txt
COPY wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r /tmp/requirements.txt

# 再拷源码（源码改动不会重装依赖）
COPY src /app

EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
