import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge.rpc_client import RpcClient
from bridge import chat_pb2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def test_streaming():
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 9997

    client = RpcClient(host, port)
    await client.connect()

    request = chat_pb2.SandboxExecuteRequest(
        prompt="写一个 Python 的 hello world 程序",
        model="gpt-4o",
        max_turns=3,
        work_dir="/tmp/swarm_test",
    )

    print(f"=== Streaming RPC Test: SwarmService.Chat ===")
    print(f"Connecting to {host}:{port}")
    print(f"Prompt: {request.prompt}")
    print(f"Model: {request.model}")
    print()

    chunk_count = 0
    try:
        async for rpc_msg in client.call_stream(
            "SwarmService", "Chat", request, timeout=600
        ):
            if rpc_msg.payload:
                event = chat_pb2.SandboxToolEvent()
                event.ParseFromString(rpc_msg.payload)
                chunk_count += 1

                content_preview = event.content[:100] if event.content else ""
                print(f"  [{chunk_count:3d}] type={event.event_type:20s} | {content_preview}")

                if event.event_type == "finish":
                    print()
                    print(f"  ✅ Stream finished! session_id={event.session_id}")
                elif event.event_type == "error":
                    print(f"  ❌ Error: {event.content}")

    except Exception as e:
        print(f"  ❌ Exception: {e}")

    print()
    print(f"Total chunks received: {chunk_count}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(test_streaming())
