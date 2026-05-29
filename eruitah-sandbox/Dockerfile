FROM python:3.11-slim

RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null; \
    sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list 2>/dev/null; \
    true

ENV DEBIAN_FRONTEND=noninteractive
ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_DOWNLOAD_HOST=https://npmmirror.com/mirrors/chrome-for-testing
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/

RUN apt-get update && apt-get install -y --no-install-recommends \
    git grep curl \
    libx11-6 libxext6 libxrender1 libxtst6 libxi6 libxrandr2 \
    libxss1 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libglib2.0-0 libgl1 libgtk-3-0 libnotify4 libnss3 libnspr4 \
    libasound2 libgbm1 libatk1.0-0 libatk-bridge2.0-0 libdrm2 libcups2 \
    xvfb x11vnc xdotool scrot imagemagick x11-utils wmctrl \
    fonts-noto-cjk fonts-wqy-zenhei \
    clangd default-jdk \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && sed -i 's|deb.nodesource.com|mirrors.tuna.tsinghua.edu.cn/nodesource|g' /etc/apt/sources.list.d/nodesource.list 2>/dev/null; \
    apt-get update && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN npm config set registry https://registry.npmmirror.com \
    && npm install -g \
    @modelcontextprotocol/server-filesystem \
    @modelcontextprotocol/server-memory \
    @modelcontextprotocol/server-sequential-thinking \
    pyright typescript-language-server typescript

RUN mkdir -p /opt/jdtls/data && \
    (curl -fsSL --retry 2 --retry-delay 3 --connect-timeout 10 --max-time 120 \
        "https://mirrors.ustc.edu.cn/eclipse/jdtls/snapshots/jdt-language-server-latest.tar.gz" 2>/dev/null || \
     curl -fsSL --retry 2 --retry-delay 3 --connect-timeout 10 --max-time 120 \
        "https://download.eclipse.org/jdtls/snapshots/jdt-language-server-latest.tar.gz" 2>/dev/null \
    ) | tar xz -C /opt/jdtls 2>/dev/null || echo "JDTLS download skipped - Java LSP will use fallback"

ENV JDTLS_HOME=/opt/jdtls
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

COPY requirements.txt .
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --prefer-binary -r requirements.txt \
    && pip install --no-cache-dir --prefer-binary playwright \
    && playwright install chromium --with-deps

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
