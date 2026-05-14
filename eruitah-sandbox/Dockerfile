FROM python:3.11-slim

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null; \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list 2>/dev/null; \
    true

ENV DEBIAN_FRONTEND=noninteractive
ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true

RUN apt-get update && apt-get install -y \
    git grep curl \
    xvfb x11vnc xdotool scrot imagemagick \
    libx11-6 libxext6 libxrender1 libxtst6 libxi6 libxrandr2 \
    libglib2.0-0 libgl1 libgtk-3-0 libnotify4 libnss3 libnspr4 \
    libxss1 libasound2 libgbm1 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    fonts-noto-cjk fonts-wqy-zenhei \
    clangd default-jdk \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN npm config set registry https://registry.npmmirror.com

RUN npm install -g \
    @modelcontextprotocol/server-filesystem \
    @modelcontextprotocol/server-github \
    @modelcontextprotocol/server-puppeteer \
    @modelcontextprotocol/server-memory \
    @modelcontextprotocol/server-sequential-thinking \
    @modelcontextprotocol/server-postgres \
    pyright typescript-language-server typescript

RUN mkdir -p /opt/jdtls && \
    curl -fsSL "https://download.eclipse.org/jdtls/snapshots/jdt-language-server-latest.tar.gz" | tar xz -C /opt/jdtls && \
    mkdir -p /opt/jdtls/data

ENV JDTLS_HOME=/opt/jdtls
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

RUN mkdir -p /tmp/eruitah-sandbox

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8001 5900

ENV DISPLAY=:99
ENV ERUITAH_SCREEN_WIDTH=1280
ENV ERUITAH_SCREEN_HEIGHT=720
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

ENTRYPOINT ["/entrypoint.sh"]
