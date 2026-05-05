import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge.rpc_server import RpcServer
from bridge.rpc_client import RpcClient
from services.sandbox_adapter import SandboxServiceAdapter

from bridge import chat_pb2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_server(host: str = "0.0.0.0", port: int = 9998):
    server = RpcServer(host, port)

    sandbox = SandboxServiceAdapter()
    sandbox.register_handlers(server)

    await server.start()
    logger.info(f"Python RPC Server (Sandbox Agent) running on {host}:{port}")
    logger.info("C++ muduo / Java backend can now call SandboxService via Protobuf RPC")

    await server.serve_forever()


async def run_client_test(host: str = "127.0.0.1", port: int = 9999):
    client = RpcClient(host, port)
    await client.connect()

    try:
        logger.info("Testing Chat RPC...")
        chat_req = chat_pb2.ChatRequest(
            user_id=1,
            bot_id=10000,
            user_name="python_tester",
            message="你好，旗舰大师！我是从 Python 端发来的消息",
            session_id="py_test_001",
            timestamp=int(asyncio.get_event_loop().time() * 1000),
        )

        rpc_msg = await client.call(
            "ChatService", "Chat", chat_req, chat_pb2.ChatResponse, timeout=10
        )

        if rpc_msg and rpc_msg.payload:
            resp = chat_pb2.ChatResponse()
            resp.ParseFromString(rpc_msg.payload)
            logger.info(f"Chat response: bot={resp.bot_name}, msg={resp.message}")

        logger.info("Testing SandboxExecute RPC...")
        sandbox_req = chat_pb2.SandboxExecuteRequest(
            prompt="Write a hello world program in Python",
            model="gpt-4o",
            max_turns=5,
        )

        rpc_msg = await client.call(
            "ChatService", "SandboxExecute", sandbox_req, chat_pb2.SandboxExecuteResponse, timeout=30
        )

        if rpc_msg and rpc_msg.payload:
            resp = chat_pb2.SandboxExecuteResponse()
            resp.ParseFromString(rpc_msg.payload)
            logger.info(f"Sandbox response: success={resp.success}, result={resp.final_result[:100]}")

    finally:
        await client.disconnect()


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "server"

    if mode == "server":
        host = sys.argv[2] if len(sys.argv) > 2 else "0.0.0.0"
        port = int(sys.argv[3]) if len(sys.argv) > 3 else 9998
        asyncio.run(run_server(host, port))
    elif mode == "client":
        host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
        port = int(sys.argv[3]) if len(sys.argv) > 3 else 9999
        asyncio.run(run_client_test(host, port))
    else:
        print(f"Usage: python {sys.argv[0]} [server|client] [host] [port]")
        print()
        print("  server  - Start Python RPC Server (Sandbox Agent) on port 9998")
        print("  client  - Connect to Java/C++ backend on port 9999 and run tests")
        print()
        print("Architecture:")
        print("  C++ muduo(:8888) <--Protobuf--> Java Backend(:9999) <--Protobuf--> Python Agent(:9998)")
        print("  eruitah-sandbox(:8001) <--HTTP/WS--> Python Agent(:9998)")


if __name__ == "__main__":
    main()
