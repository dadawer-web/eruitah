#!/bin/bash
set -e

echo "🚀 Eruitah 智能编程沙盒启动中..."

DISPLAY_NUM=99
SCREEN_WIDTH=${ERUITAH_SCREEN_WIDTH:-1280}
SCREEN_HEIGHT=${ERUITAH_SCREEN_HEIGHT:-720}

echo "🖥️  启动 Xvfb 虚拟桌面: :${DISPLAY_NUM} (${SCREEN_WIDTH}x${SCREEN_HEIGHT})"
Xvfb :${DISPLAY_NUM} -screen 0 ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x24 -ac -nolisten tcp &
XVFB_PID=$!
sleep 1

if ! kill -0 $XVFB_PID 2>/dev/null; then
    echo "❌ Xvfb 启动失败"
    exit 1
fi
echo "✅ Xvfb 已启动 (PID: $XVFB_PID)"

export DISPLAY=:${DISPLAY_NUM}

if [ "${ERUITAH_ENABLE_VNC:-false}" = "true" ]; then
    VNC_PORT=${ERUITAH_VNC_PORT:-5900}
    echo "📺 启动 x11vnc (端口: ${VNC_PORT})..."
    x11vnc -display :${DISPLAY_NUM} -rfbport ${VNC_PORT} -nopw -shared -forever -bg
    echo "✅ VNC 已启动: vnc://localhost:${VNC_PORT}"
fi

echo "🤖 启动 Eruitah Agent 服务..."
exec uvicorn main:app --host 0.0.0.0 --port 8001
