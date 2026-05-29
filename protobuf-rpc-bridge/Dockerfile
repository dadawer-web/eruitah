FROM python:3.11-slim

WORKDIR /bridge

ENV PYTHONUNBUFFERED=1

COPY python/requirements.txt .
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --prefer-binary -r requirements.txt

COPY python/ /bridge/

EXPOSE 9998

CMD ["python", "main.py", "server", "0.0.0.0", "9998"]
