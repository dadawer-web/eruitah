#!/bin/bash
# ============================================================
# 服务器端：构建 runtime-only 镜像并启动
# 在服务器上执行: cd /opt/eruitah && bash server-start.sh
# ============================================================
set -e
cd "$(dirname "$0")"

echo "===== 复制 Dockerfile 到各制品目录 ====="
cp dockerfiles/ai-service.Dockerfile  dist/ai-service/Dockerfile
cp dockerfiles/cpp-server.Dockerfile  dist/cpp-server/Dockerfile
cp dockerfiles/butcanthic.Dockerfile  dist/butcanthic/Dockerfile
cp dockerfiles/sandbox.Dockerfile     dist/sandbox/Dockerfile

echo "===== 构建 runtime-only 镜像（首次较慢，后续有缓存）====="
docker compose -f docker-compose.runtime.yml build

echo "===== 启动全部服务 ====="
docker compose -f docker-compose.runtime.yml up -d

echo "===== 等待服务就绪 ====="
sleep 5

echo "===== 服务状态 ====="
docker compose -f docker-compose.runtime.yml ps

echo ""
echo "========================================"
echo "  启动完成！"
echo "========================================"
echo "查看日志:   docker compose -f docker-compose.runtime.yml logs -f"
echo "停止服务:   docker compose -f docker-compose.runtime.yml down"
echo "单独看某服务: docker compose -f docker-compose.runtime.yml logs -f ai-service"
