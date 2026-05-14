import asyncio
import json
import logging
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge.streaming_rpc_server import StreamingRpcServer
from bridge import chat_pb2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

ERUITAH_SANDBOX_DIR = os.environ.get(
    "ERUITAH_SANDBOX_DIR", "/home/xmy/code/eruitah-sandbox"
)

_executor = ThreadPoolExecutor(max_workers=4)


def _import_run_swarm():
    if ERUITAH_SANDBOX_DIR not in sys.path:
        sys.path.insert(0, ERUITAH_SANDBOX_DIR)
    from agent_swarm import run_swarm
    return run_swarm


def _event_to_tool_event(event: dict, session_id: str) -> chat_pb2.SandboxToolEvent:
    event_type = event.get("type", "unknown")
    content = event.get("data", "") or event.get("content", "")
    status_data = ""
    if event.get("status"):
        status_data = json.dumps({"status": event["status"]}, ensure_ascii=False)
    elif event.get("loop"):
        status_data = json.dumps(
            {"loop": event["loop"], "role": event.get("role", "")}, ensure_ascii=False
        )
    elif event.get("result"):
        status_data = json.dumps(
            {"has_result": True, "type": event_type}, ensure_ascii=False
        )

    return chat_pb2.SandboxToolEvent(
        session_id=session_id,
        event_type=event_type,
        tool_name=event.get("tool_name", ""),
        args_json=json.dumps(event.get("args", {}), ensure_ascii=False) if event.get("args") else "",
        result=event.get("result", "") if isinstance(event.get("result"), str) else "",
        is_error=event_type == "error",
        content=str(content),
        status_data=status_data,
        timestamp=int(time.time() * 1000),
    )


def _make_finish_event(session_id: str, status: str, error_msg: str = "") -> chat_pb2.SandboxToolEvent:
    finish_data = {"type": "chat_finish", "status": status}
    if error_msg:
        finish_data["error"] = error_msg

    return chat_pb2.SandboxToolEvent(
        session_id=session_id,
        event_type="chat_finish",
        is_error=(status == "error"),
        content=json.dumps(finish_data, ensure_ascii=False),
        timestamp=int(time.time() * 1000),
    )


def _run_swarm_in_thread(request: chat_pb2.SandboxExecuteRequest, queue: Queue):
    task_id = request.session_id or f"swarm_{uuid.uuid4().hex[:8]}"

    try:
        run_swarm = _import_run_swarm()
    except ImportError as e:
        queue.put(("error", (task_id, str(e))))
        queue.put(None)
        return

    prompt = request.prompt
    if not prompt:
        queue.put(("error", (task_id, "prompt is empty")))
        queue.put(None)
        return

    try:
        for event in run_swarm(
            user_input=prompt,
            task_description=prompt,
            work_dir=request.work_dir or ".",
            max_turns=request.max_turns or 30,
            api_key=request.api_key or None,
            model=request.model or None,
            base_url=request.base_url or None,
            provider=request.provider or "openai",
            task_id=task_id,
            yield_events=True,
        ):
            queue.put(("event", (event, task_id)))
    except Exception as e:
        logger.error(f"[SwarmThread] Unhandled exception in run_swarm: {e}", exc_info=True)
        queue.put(("error", (task_id, str(e))))
    finally:
        queue.put(None)


async def handle_swarm_chat(rpc_msg: chat_pb2.RpcMessage):
    request = chat_pb2.SandboxExecuteRequest()
    request.ParseFromString(rpc_msg.payload)

    prompt = request.prompt
    session_id = request.session_id or f"swarm_{uuid.uuid4().hex[:8]}"
    logger.info(f"[SwarmChat] prompt={prompt[:80] if prompt else 'EMPTY'}... session_id={session_id}")

    if not prompt:
        yield _make_finish_event("error", "error", "prompt is empty")
        return

    q: Queue = Queue()
    loop = asyncio.get_event_loop()

    loop.run_in_executor(_executor, _run_swarm_in_thread, request, q)

    has_error = False
    error_msg = ""

    try:
        while True:
            try:
                item = await loop.run_in_executor(None, q.get, True, 0.1)
            except Empty:
                await asyncio.sleep(0.01)
                continue

            if item is None:
                break

            kind, data = item
            if kind == "event":
                event_dict, tid = data
                yield _event_to_tool_event(event_dict, tid)
            elif kind == "error":
                tid, err = data
                has_error = True
                error_msg = err
                logger.error(f"[SwarmChat] Error from swarm thread: {err}")
                yield chat_pb2.SandboxToolEvent(
                    session_id=tid,
                    event_type="error",
                    is_error=True,
                    content=err,
                    timestamp=int(time.time() * 1000),
                )
                break

    except asyncio.CancelledError:
        logger.warning(f"[SwarmChat] Stream cancelled for session_id={session_id}")
        has_error = True
        error_msg = "Stream cancelled by client"
        yield _make_finish_event(session_id, "error", "Stream cancelled by client")

    except Exception as e:
        logger.error(f"[SwarmChat] Unexpected error in stream loop: {e}", exc_info=True)
        has_error = True
        error_msg = str(e)
        yield _make_finish_event(session_id, "error", str(e))

    finally:
        status = "error" if has_error else "success"
        logger.info(f"[SwarmChat] Stream finished: session_id={session_id} status={status}")
        if not has_error:
            yield _make_finish_event(session_id, "success")


async def main():
    host = os.environ.get("RPC_HOST", "0.0.0.0")
    port = int(os.environ.get("RPC_PORT", "9997"))

    server = StreamingRpcServer(host, port)
    server.register("SwarmService", "Chat", handle_swarm_chat)

    await server.start()
    logger.info(f"Simple Swarm RPC Server running on {host}:{port}")
    logger.info("Interface: SwarmService.Chat (streaming)")
    logger.info("  Request:  SandboxExecuteRequest (prompt, work_dir, max_turns, model, ...)")
    logger.info("  Response: stream of SandboxToolEvent (event_type, content, ...)")
    logger.info(f"eruitah-sandbox dir: {ERUITAH_SANDBOX_DIR}")

    await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
