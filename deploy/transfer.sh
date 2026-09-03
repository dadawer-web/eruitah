#!/bin/bash
# ============================================================
# 传输制品到服务器
# 用法:
#   SERVER_HOST=1.2.3.4 SERVER_USER=root bash deploy/transfer.sh
# 或先 export 再执行
# ============================================================
set -e

SERVER_HOST="${SERVER_HOST:?请设置 SERVER_HOST，例如: SERVER_HOST=1.2.3.4 bash deploy/transfer.sh}"
SERVER_USER="${SERVER_USER:-root}"
REMOTE_DIR="${REMOTE_DIR:-/opt/eruitah}"
DEPLOY_DIR="/home/xmy/code/deploy"
SERVER="${SERVER_USER}@${SERVER_HOST}"

echo "===== 传输制品到 $SERVER:$REMOTE_DIR ====="

# 1. 远程创建目录
ssh "$SERVER" "mkdir -p $REMOTE_DIR/dockerfiles"

# 2. 传输打包的制品（dist.tar.gz）
echo "  [1/4] 传输 dist.tar.gz ..."
scp "$DEPLOY_DIR/dist.tar.gz" "$SERVER:/tmp/dist.tar.gz"

# 3. 传输 Dockerfile 和编排文件
echo "  [2/4] 传输 Dockerfiles ..."
scp "$DEPLOY_DIR"/dockerfiles/*.Dockerfile "$SERVER:$REMOTE_DIR/dockerfiles/"

echo "  [3/4] 传输 docker-compose.runtime.yml ..."
scp "$DEPLOY_DIR/docker-compose.runtime.yml" "$SERVER:$REMOTE_DIR/"

echo "  [4/4] 传输 server-start.sh ..."
scp "$DEPLOY_DIR/server-start.sh" "$SERVER:$REMOTE_DIR/"

# 4. 远程解压制品
echo "===== 远程解压制品 ====="
ssh "$SERVER" "cd $REMOTE_DIR && tar xzf /tmp/dist.tar.gz && rm -f /tmp/dist.tar.gz && ls -la $REMOTE_DIR/dist/"

echo ""
echo "========================================"
echo "  传输完成！"
echo "========================================"
echo "登录服务器执行启动:"
echo "  ssh $SERVER"
echo "  cd $REMOTE_DIR"
echo "  bash server-start.sh"
