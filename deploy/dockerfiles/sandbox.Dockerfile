# Python eruitah-sandbox runtime-only
# pip 包离线 wheel 安装；系统包/JDTLS/Playwright 浏览器仍需联网（有层缓存）
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99
ENV JDTLS_HOME=/opt/jdtls
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
ENV ERUITAH_SCREEN_WIDTH=1280
ENV ERUITAH_SCREEN_HEIGHT=720

# 系统依赖（X11/Xvfb/JDK/字体 等）
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

# Node.js（MCP server / TS LSP 需要）
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN npm config set registry https://registry.npmmirror.com \
    && npm install -g \
        @modelcontextprotocol/server-filesystem \
        @modelcontextprotocol/server-memory \
        @modelcontextprotocol/server-sequential-thinking \
        pyright typescript-language-server typescript

# JDTLS（Java LSP，下载失败会降级跳过）
RUN mkdir -p /opt/jdtls/data && \
    (curl -fsSL --retry 2 --connect-timeout 10 --max-time 120 \
        "https://mirrors.ustc.edu.cn/eclipse/jdtls/snapshots/jdt-language-server-latest.tar.gz" 2>/dev/null || \
     curl -fsSL --retry 2 --connect-timeout 10 --max-time 120 \
        "https://download.eclipse.org/jdtls/snapshots/jdt-language-server-latest.tar.gz" 2>/dev/null \
    ) | tar xz -C /opt/jdtls 2>/dev/null || echo "JDTLS download skipped - Java LSP will use fallback"

# 离线安装 Python 依赖（wheel 已随制品打包）
COPY src/requirements.txt /tmp/requirements.txt
COPY wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels \
        -r /tmp/requirements.txt \
    && pip install --no-cache-dir --no-index --find-links=/wheels playwright \
    && playwright install chromium --with-deps

# 拷源码
COPY src /app
RUN mkdir -p /tmp/eruitah-sandbox
COPY src/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8001 5900
ENTRYPOINT ["/entrypoint.sh"]
