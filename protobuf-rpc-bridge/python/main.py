import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge.rpc_server import RpcServer
from bridge.rpc_client import RpcClient
from services.sandbox_adapter import SandboxServiceAdapter
from services.swarm_bridge import SwarmBridge

from bridge import chat_pb2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_server(host: str = "0.0.0.0", port: int = 9998):
    sandbox_url = os.environ.get("ERUITAH_SANDBOX_URL", "http://127.0.0.1:8001")
    sandbox_ws_url = os.environ.get("ERUITAH_SANDBOX_WS_URL", "ws://127.0.0.1:8001")

    server = RpcServer(host, port)

    sandbox = SandboxServiceAdapter(sandbox_url=sandbox_url, sandbox_ws_url=sandbox_ws_url)
    sandbox.register_handlers(server)

    swarm_bridge = SwarmBridge()
    try:
        if swarm_bridge.connect():
            swarm_bridge.set_message_callback(
                lambda msg: logger.info(f"Swarm message received: type={msg.type} from={msg.from_id}")
            )
            logger.info("Swarm Bridge connected to eruitah-sandbox Swarm Hub")
    except Exception as e:
        logger.warning(f"Swarm Bridge not available: {e}")

    await server.start()
    logger.info(f"Python RPC Server (Sandbox Agent) running on {host}:{port}")
    logger.info(f"Connected to eruitah-sandbox at {sandbox_url}")
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

        logger.info("Testing SandboxService.HealthCheck RPC (requires Python server on 9998)...")
        try:
            health_client = RpcClient("127.0.0.1", 9998)
            await health_client.connect()
            health_req = chat_pb2.SandboxTaskRequest(action="health_check")
            rpc_msg = await health_client.call(
                "SandboxService", "HealthCheck", health_req, chat_pb2.SandboxTaskResponse, timeout=5
            )
            if rpc_msg and rpc_msg.payload:
                resp = chat_pb2.SandboxTaskResponse()
                resp.ParseFromString(rpc_msg.payload)
                logger.info(f"Health check: success={resp.success}, data={resp.data[:100]}")
            await health_client.disconnect()
        except Exception as e:
            logger.warning(f"Health check skipped (Python server not running on 9998): {e}")

    finally:
        await client.disconnect()


async def run_bridge_test():
    from services.sandbox_bridge import SandboxBridge

    bridge = SandboxBridge(java_host="127.0.0.1", java_port=9999, sync=False)
    await bridge.connect_async()

    try:
        logger.info("Testing SandboxBridge.call_chat_async...")
        resp = await bridge.call_chat_async(
            user_id=1, bot_id=10000,
            user_name="bridge_tester",
            message="Hello from SandboxBridge!",
            session_id="bridge_test_001",
        )
        if resp:
            logger.info(f"Chat response via bridge: bot={resp.bot_name}, msg={resp.message}")
        else:
            logger.warning("No chat response via bridge")
    finally:
        await bridge.disconnect_async()


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
    elif mode == "bridge":
        asyncio.run(run_bridge_test())
    else:
        print(f"Usage: python {sys.argv[0]} [server|client|bridge] [host] [port]")
        print()
        print("  server  - Start Python RPC Server (Sandbox Agent) on port 9998")
        print("  client  - Connect to Java/C++ backend on port 9999 and run tests")
        print("  bridge  - Test SandboxBridge (eruitah-sandbox import module)")
        print()
        print("Architecture:")
        print("  C++ muduo(:8888) <--Protobuf--> Java Backend(:9999) <--Protobuf--> Python Agent(:9998)")
        print("  eruitah-sandbox(:8001) <--HTTP/WS--> Python Agent(:9998)")
        print("  eruitah-sandbox Swarm(:9000) <--TCP JSON--> Swarm Bridge")
        print()
        print("Environment Variables:")
        print("  ERUITAH_SANDBOX_URL     - eruitah-sandbox HTTP URL (default: http://127.0.0.1:8001)")
        print("  ERUITAH_SANDBOX_WS_URL  - eruitah-sandbox WebSocket URL (default: ws://127.0.0.1:8001)")
        print("  ERUITAH_SWARM_HOST      - Swarm Hub host (default: 127.0.0.1)")
        print("  ERUITAH_SWARM_PORT      - Swarm Hub port (default: 9000)")


if __name__ == "__main__":
    main()
