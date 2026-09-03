#!/bin/bash
# ============================================================
# 本地编译/打包三个服务，产出制品到 deploy/dist/
# 用法: bash deploy/build-local.sh
# ============================================================
set -e

PROJECT_ROOT="/home/xmy/code"
DIST="$PROJECT_ROOT/deploy/dist"
JOBS=$(nproc)

echo "===== 清理旧制品 ====="
rm -rf "$DIST"
mkdir -p "$DIST"

# ------------------------------------------------------------
# [1/4] Java ai-service  -> jar 包（跨平台，最省心）
# ------------------------------------------------------------
echo "===== [1/4] 构建 Java ai-service ====="
cd "$PROJECT_ROOT/ai-service"
mvn clean package -DskipTests -q
mkdir -p "$DIST/ai-service"
cp target/ai-service-1.0.0.jar "$DIST/ai-service/app.jar"
cp .env.example "$DIST/ai-service/.env.example" 2>/dev/null || true
# 若已有 .env 也一并带上
cp .env "$DIST/ai-service/.env" 2>/dev/null || true
echo "  -> 产物: $DIST/ai-service/app.jar"

# ------------------------------------------------------------
# [2/4] C++ ChatServer -> 二进制 + ldd 收集动态库
# ------------------------------------------------------------
echo "===== [2/4] 构建 C++ ChatServer ====="
cd "$PROJECT_ROOT"
mkdir -p build
cd build
cmake .. -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -3
make -j"$JOBS" ChatServer 2>&1 | tail -5
mkdir -p "$DIST/cpp-server/libs"
cp src/server/ChatServer "$DIST/cpp-server/"
# 收集所有非系统基础库的 .so（Qt5/mysqlclient/hiredis 等）
ldd src/server/ChatServer \
  | grep "=> /" | awk '{print $3}' \
  | sort -u > /tmp/so-list.txt
echo "  -> 依赖 .so 数量: $(wc -l < /tmp/so-list.txt)"
while read -r so; do
  [ -f "$so" ] && cp "$so" "$DIST/cpp-server/libs/" 2>/dev/null || true
done < /tmp/so-list.txt
rm -f /tmp/so-list.txt
echo "  -> 产物: $DIST/cpp-server/ChatServer (+ $(ls "$DIST/cpp-server/libs" | wc -l) 个 .so)"

# ------------------------------------------------------------
# [3/4] Python butcanthic -> 离线 wheel + 源码
# ------------------------------------------------------------
echo "===== [3/4] 构建 Python butcanthic (离线 wheel) ====="
mkdir -p "$DIST/butcanthic/wheels"
cd "$PROJECT_ROOT/butcanthic"
pip download -d "$DIST/butcanthic/wheels" -r requirements.txt --prefer-binary -q
# 打包源码（排除虚拟环境/缓存/运行时数据）
rsync -a --exclude='venv/' --exclude='__pycache__/' --exclude='.git/' \
  --exclude='*.db' --exclude='uploads/' --exclude='output/' \
  --exclude='metadata.db' --exclude='graph_db.json' \
  --exclude='image_caption_cache.json' \
  "$PROJECT_ROOT/butcanthic/" "$DIST/butcanthic/src/"
echo "  -> 产物: $DIST/butcanthic/wheels (+ $(du -sh "$DIST/butcanthic/src" | cut -f1) 源码)"

# ------------------------------------------------------------
# [4/4] Python eruitah-sandbox -> 离线 wheel + 源码
# ------------------------------------------------------------
echo "===== [4/4] 构建 Python eruitah-sandbox (离线 wheel) ====="
mkdir -p "$DIST/sandbox/wheels"
cd "$PROJECT_ROOT/eruitah-sandbox"
pip download -d "$DIST/sandbox/wheels" -r requirements.txt --prefer-binary -q
# playwright 不在 requirements.txt，单独下载
pip download -d "$DIST/sandbox/wheels" playwright --prefer-binary -q
rsync -a --exclude='venv/' --exclude='__pycache__/' --exclude='.git/' \
  --exclude='*.db' --exclude='.user_data/' --exclude='.eruitah_cache/' \
  --exclude='.code_index.db' --exclude='.theseus/' \
  --exclude='cloud-storage/' --exclude='spring-cloud-demo/' --exclude='threadpool-rs/' \
  "$PROJECT_ROOT/eruitah-sandbox/" "$DIST/sandbox/src/"
echo "  -> 产物: $DIST/sandbox/wheels (+ $(du -sh "$DIST/sandbox/src" | cut -f1) 源码)"

# ------------------------------------------------------------
# 打包 dist 为 tar.gz 便于传输
# ------------------------------------------------------------
echo "===== 打包 dist 为 tar.gz ====="
cd "$PROJECT_ROOT/deploy"
tar czf dist.tar.gz dist/
echo ""
echo "========================================"
echo "  本地构建全部完成！"
echo "========================================"
echo "制品目录: $DIST"
echo "打包文件: $PROJECT_ROOT/deploy/dist.tar.gz"
echo ""
echo "各制品大小:"
du -sh "$DIST"/*
du -sh "$PROJECT_ROOT/deploy/dist.tar.gz"
echo ""
echo "下一步: bash deploy/transfer.sh"
