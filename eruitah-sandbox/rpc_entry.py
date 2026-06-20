import asyncio
import json
import logging
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue

from decorators import aios_notify

RPC_BRIDGE_DIR = os.environ.get(
    "RPC_BRIDGE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "protobuf-rpc-bridge", "python"),
)
if RPC_BRIDGE_DIR not in sys.path:
    sys.path.insert(0, RPC_BRIDGE_DIR)

try:
    from bridge.streaming_rpc_server import StreamingRpcServer
    from bridge.rpc_client import RpcClient, SyncRpcClient
    from bridge import chat_pb2
except ImportError as _e:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        f"⚠️ protobuf 或 bridge 模块导入失败 ({_e})，RPC 功能不可用。"
        f"请执行: pip install protobuf"
    )
    StreamingRpcServer = None
    RpcClient = None
    SyncRpcClient = None
    chat_pb2 = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

JAVA_RPC_HOST = os.environ.get("JAVA_RPC_HOST", "127.0.0.1")
JAVA_RPC_PORT = int(os.environ.get("JAVA_RPC_PORT", "9999"))

WORKTREE_BASE_DIR = os.environ.get("WORKTREE_BASE_DIR", "/home/agent-worktrees")

_executor = ThreadPoolExecutor(max_workers=4)

_java_rpc_client: SyncRpcClient | None = None


def _get_java_rpc_client() -> SyncRpcClient:
    global _java_rpc_client
    if _java_rpc_client and _java_rpc_client.connected:
        return _java_rpc_client
    _java_rpc_client = SyncRpcClient(JAVA_RPC_HOST, JAVA_RPC_PORT)
    _java_rpc_client.connect()
    logger.info(f"[RPC] Connected to Java backend at {JAVA_RPC_HOST}:{JAVA_RPC_PORT}")
    return _java_rpc_client


def _import_run_swarm():
    sandbox_dir = os.environ.get(
        "ERUITAH_SANDBOX_DIR",
        os.path.dirname(os.path.abspath(__file__)),
    )
    if sandbox_dir not in sys.path:
        sys.path.insert(0, sandbox_dir)
    from agent_swarm import run_swarm
    return run_swarm


def _import_sandbox_manager():
    sandbox_dir = os.environ.get(
        "ERUITAH_SANDBOX_DIR",
        os.path.dirname(os.path.abspath(__file__)),
    )
    if sandbox_dir not in sys.path:
        sys.path.insert(0, sandbox_dir)
    from sandbox_manager import get_sandbox_manager
    return get_sandbox_manager


def _allocate_worktree(user_id: int, session_id: str) -> str:
    from sandbox_isolation import get_user_work_dir
    work_dir = get_user_work_dir(user_id, session_id)
    os.makedirs(work_dir, exist_ok=True)

    try:
        get_sandbox_manager = _import_sandbox_manager()
        sm = get_sandbox_manager()
        if sm:
            task_id = f"rpc_{session_id}"
            try:
                sandbox = sm.create_task(task_id=task_id, work_dir=work_dir)
                if sandbox and hasattr(sandbox, 'work_dir') and sandbox.work_dir:
                    work_dir = sandbox.work_dir
                    logger.info(f"[RPC] Allocated Git Worktree for task={task_id}: {work_dir}")
            except Exception as e:
                logger.warning(f"[RPC] GitSandboxManager allocation failed, using plain dir: {e}")
    except Exception as e:
        logger.debug(f"[RPC] GitSandboxManager not available, using plain dir: {e}")

    return work_dir


def _event_to_run_code_response(event: dict, session_id: str) -> chat_pb2.RunCodeResponse:
    event_type = event.get("type", "unknown")
    content = event.get("data", "") or event.get("content", "")

    if event_type in ("tool_start", "tool_end"):
        tool_name = event.get("tool_name", "")
        args_json = event.get("args", "")
        if isinstance(args_json, dict):
            args_json = json.dumps(args_json, ensure_ascii=False)
        result = event.get("result", "")
        log_line = f"[{event_type}] {tool_name}"
        if args_json:
            log_line += f" | args: {args_json[:200]}"
        if result:
            log_line += f" | result: {str(result)[:200]}"
        return chat_pb2.RunCodeResponse(log_stream=log_line, is_finished=False)

    if event_type == "chat_finish":
        return chat_pb2.RunCodeResponse(
            log_stream="[System] Task finished.",
            is_finished=True,
        )

    if event_type == "finish":
        status = event.get("status", "")
        data = content or ""
        log_line = f"[finish] {data}"
        if status:
            log_line += f" (status: {status})"
        return chat_pb2.RunCodeResponse(log_stream=log_line, is_finished=True)

    if event_type == "error":
        return chat_pb2.RunCodeResponse(
            log_stream=f"[error] {content}",
            is_finished=True,
        )

    if event_type in ("system_alert", "agent_status", "agent_state", "typing"):
        return chat_pb2.RunCodeResponse(
            log_stream=content or f"[{event_type}]",
            is_finished=False,
        )

    if event_type == "message":
        return chat_pb2.RunCodeResponse(
            log_stream=content or "",
            is_finished=False,
        )

    if event_type == "swarm_result":
        result = event.get("result")
        if result:
            data = event.get("data", "Task completed")
            return chat_pb2.RunCodeResponse(log_stream=f"[result] {data}", is_finished=False)
        return chat_pb2.RunCodeResponse(log_stream="", is_finished=False)

    if content:
        return chat_pb2.RunCodeResponse(log_stream=content, is_finished=False)

    return chat_pb2.RunCodeResponse(log_stream="", is_finished=False)


@aios_notify(
    source="sandbox",
    action_start="thinking",
    action_error="error",
    action_success="idle",
    start_msg_template="AI Agent 正在您的沙盒中疯狂敲代码...",
    success_msg_template="代码执行完美！未发现 Bug。",
)
def _run_swarm_in_thread(user_id, request, queue: Queue):
    """Agent 执行入口（user_id 提升为首参，供 @aios_notify 提取）"""
    session_id = request.session_id or f"rpc_{uuid.uuid4().hex[:8]}"
    task_prompt = request.task_prompt
    skills = list(request.skills)

    if not user_id or user_id <= 0:
        logger.warning(
            f"[RPC] user_id={user_id} is invalid for tenant isolation! session={session_id}"
        )

    try:
        run_swarm = _import_run_swarm()
    except ImportError as e:
        queue.put(("error", (session_id, str(e))))
        queue.put(None)
        return

    if not task_prompt:
        queue.put(("error", (session_id, "task_prompt is empty")))
        queue.put(None)
        return

    work_dir = _allocate_worktree(user_id, session_id)

    logger.info(
        f"[RPC] Starting swarm for user={user_id} session={session_id} "
        f"work_dir={work_dir} skills={skills}"
    )

    try:
        for event in run_swarm(
            user_input=task_prompt,
            task_description=task_prompt,
            work_dir=work_dir,
            max_turns=30,
            task_id=session_id,
            yield_events=True,
            user_id=user_id,
        ):
            queue.put(("event", (event, session_id, user_id)))
    except Exception as e:
        logger.error(f"[RPC] Swarm execution error: {e}", exc_info=True)
        queue.put(("error", (session_id, str(e))))
    finally:
        queue.put(None)


async def handle_run_agent_task(rpc_msg: chat_pb2.RpcMessage):
    request = chat_pb2.RunCodeRequest()
    request.ParseFromString(rpc_msg.payload)

    user_id = request.user_id
    session_id = request.session_id or f"rpc_{uuid.uuid4().hex[:8]}"
    task_prompt = request.task_prompt

    if not user_id or user_id <= 0:
        logger.warning(
            f"[SandboxService.RunAgentTask] user_id is {user_id}, "
            f"tenant isolation requires non-zero user_id! session={session_id}"
        )

    logger.info(
        f"[SandboxService.RunAgentTask] user={user_id} session={session_id} "
        f"prompt={task_prompt[:80] if task_prompt else 'EMPTY'}..."
    )

    if not task_prompt:
        yield chat_pb2.RunCodeResponse(
            log_stream="[error] task_prompt is empty",
            is_finished=True,
        )
        return

    q: Queue = Queue()
    loop = asyncio.get_event_loop()

    loop.run_in_executor(_executor, _run_swarm_in_thread, user_id, request, q)

    has_error = False

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
                event_dict, sid, uid = data
                yield _event_to_run_code_response(event_dict, sid)
            elif kind == "error":
                sid, err = data
                has_error = True
                logger.error(f"[SandboxService] Error: {err}")
                yield chat_pb2.RunCodeResponse(
                    log_stream=f"[error] {err}",
                    is_finished=True,
                )
                break

    except asyncio.CancelledError:
        logger.warning(f"[SandboxService] Stream cancelled: session={session_id}")
        yield chat_pb2.RunCodeResponse(
            log_stream="[System] Stream cancelled by client.",
            is_finished=True,
        )

    except Exception as e:
        logger.error(f"[SandboxService] Unexpected error: {e}", exc_info=True)
        yield chat_pb2.RunCodeResponse(
            log_stream=f"[error] {str(e)}",
            is_finished=True,
        )

    finally:
        status = "error" if has_error else "success"
        logger.info(f"[SandboxService] Task finished: session={session_id} status={status}")
        if not has_error:
            yield chat_pb2.RunCodeResponse(
                log_stream="[System] Task execution complete.",
                is_finished=True,
            )


def report_career_advice(
    user_id: int,
    extracted_skills: list,
    resume_highlight: str,
    next_suggestion: str,
):
    if chat_pb2 is None:
        logger.warning("[RPC] report_career_advice 跳过: protobuf 未安装")
        return
    try:
        client = _get_java_rpc_client()

        req = chat_pb2.CareerAdviceRequest(
            user_id=user_id,
            extracted_skills=extracted_skills,
            resume_highlight=resume_highlight,
            next_suggestion=next_suggestion,
            skills=extracted_skills,
            learning_advice=next_suggestion,
        )

        response = client.call(
            "CareerAdviceService",
            "SendCareerAdvice",
            req,
            chat_pb2.CareerAdviceResponse,
            timeout=60.0,
        )

        if response and response.success:
            logger.info(f"[RPC] Career advice sent to Java for user={user_id}")
        else:
            err = "no response" if not response else "success=false"
            logger.warning(f"[RPC] Career advice delivery failed for user={user_id}: {err}")

    except Exception as e:
        logger.error(f"[RPC] Failed to send career advice to Java: {e}")


async def report_career_advice_async(
    user_id: int,
    extracted_skills: list,
    resume_highlight: str,
    next_suggestion: str,
):
    if chat_pb2 is None:
        logger.warning("[RPC] report_career_advice_async 跳过: protobuf 未安装")
        return
    try:
        client = RpcClient(JAVA_RPC_HOST, JAVA_RPC_PORT)
        await client.connect()

        req = chat_pb2.CareerAdviceRequest(
            user_id=user_id,
            extracted_skills=extracted_skills,
            resume_highlight=resume_highlight,
            next_suggestion=next_suggestion,
            skills=extracted_skills,
            learning_advice=next_suggestion,
        )

        response = await client.call(
            "CareerAdviceService",
            "SendCareerAdvice",
            req,
            chat_pb2.CareerAdviceResponse,
            timeout=60.0,
        )

        if response and response.success:
            logger.info(f"[RPC] Career advice sent to Java for user={user_id}")
        else:
            err = "no response" if not response else "success=false"
            logger.warning(f"[RPC] Career advice delivery failed for user={user_id}: {err}")

        await client.disconnect()

    except Exception as e:
        logger.error(f"[RPC] Failed to send career advice to Java (async): {e}")


async def main():
    if StreamingRpcServer is None:
        logger.error("❌ RPC 服务无法启动: protobuf 或 bridge 模块未安装。请执行: pip install protobuf")
        return

    host = os.environ.get("RPC_HOST", "0.0.0.0")
    port = int(os.environ.get("RPC_PORT", "9997"))

    server = StreamingRpcServer(host, port)

    server.register("SandboxService", "RunAgentTask", handle_run_agent_task)

    server.register("SwarmService", "Chat", handle_run_agent_task)

    await server.start()
    logger.info(f"=" * 60)
    logger.info(f"  Eruitah Sandbox RPC Server")
    logger.info(f"  Listening: {host}:{port}")
    logger.info(f"  Services:")
    logger.info(f"    - SandboxService.RunAgentTask (streaming)")
    logger.info(f"    - SwarmService.Chat (streaming, compat)")
    logger.info(f"  Java backend: {JAVA_RPC_HOST}:{JAVA_RPC_PORT}")
    logger.info(f"  Worktree base: {WORKTREE_BASE_DIR}")
    logger.info(f"  Bridge dir: {RPC_BRIDGE_DIR}")
    logger.info(f"=" * 60)

    await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
