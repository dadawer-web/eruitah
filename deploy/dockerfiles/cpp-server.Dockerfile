# C++ ChatServer runtime-only（COPY 本地编译好的二进制 + ldd 收集的 .so）
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY ChatServer /app/ChatServer
COPY libs/ /app/libs/
RUN chmod +x /app/ChatServer

# 优先加载随包带过来的 .so，避免服务器缺 Qt5/mysqlclient 等运行时库
ENV LD_LIBRARY_PATH=/app/libs

EXPOSE 6000 8888
# ChatServer 启动参数: ./ChatServer <ip> <port>
CMD ["./ChatServer", "0.0.0.0", "6000"]
