import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Dict, Optional

from bridge import chat_pb2
from bridge.rpc_server import RpcServer

logger = logging.getLogger(__name__)


class SandboxServiceAdapter:
    def __init__(
        self,
        sandbox_url: str = "http://127.0.0.1:8001",
        sandbox_ws_url: str = "ws://127.0.0.1:8001",
    ):
        self._sandbox_url = sandbox_url
        self._sandbox_ws_url = sandbox_ws_url

    def register_handlers(self, server: RpcServer):
        server.register_rpc("SandboxService", "Execute", self.handle_execute)
        server.register_rpc("SandboxService", "TaskAction", self.handle_task_action)
        server.register_rpc("SandboxService", "StreamExecute", self.handle_stream_execute)
        server.register_direct(chat_pb2.SandboxExecuteRequest, self.handle_execute_direct)
        server.register_direct(chat_pb2.SwarmMessage, self.handle_swarm_message)
        logger.info("Registered SandboxService handlers")

    async def handle_execute(self, rpc_msg: chat_pb2.RpcMessage) -> chat_pb2.SandboxExecuteResponse:
        request = chat_pb2.SandboxExecuteRequest()
        request.ParseFromString(rpc_msg.payload)
        return await self.execute(request)

    async def handle_execute_direct(self, request: chat_pb2.SandboxExecuteRequest) -> chat_pb2.SandboxExecuteResponse:
        return await self.execute(request)

    async def execute(self, request: chat_pb2.SandboxExecuteRequest) -> chat_pb2.SandboxExecuteResponse:
        logger.info(f"Executing sandbox task: prompt={request.prompt[:50]}...")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=300) as client:
                payload = {
                    "prompt": request.prompt,
                    "work_dir": request.work_dir or None,
                    "max_turns": request.max_turns or 30,
                    "model": request.model or None,
                    "api_key": request.api_key or None,
                    "base_url": request.base_url or None,
                    "provider": request.provider or None,
                }
                payload = {k: v for k, v in payload.items() if v is not None}

                resp = await client.post(
                    f"{self._sandbox_url}/api/v1/execute",
                    json=payload,
                )
                result = resp.json()

                session_id = request.session_id or f"sb_{int(time.time())}"

                return chat_pb2.SandboxExecuteResponse(
                    session_id=session_id,
                    success=result.get("success", False),
                    error=result.get("message", "") if not result.get("success") else "",
                    final_result=result.get("message", ""),
                    turns_used=len(result.get("events", [])),
                    timestamp=int(time.time() * 1000),
                )

        except ImportError:
            return chat_pb2.SandboxExecuteResponse(
                session_id=request.session_id or f"sb_{int(time.time())}",
                success=False,
                error="httpx not installed. Run: pip install httpx",
                timestamp=int(time.time() * 1000),
            )
        except Exception as e:
            logger.error(f"Sandbox execute error: {e}")
            return chat_pb2.SandboxExecuteResponse(
                session_id=request.session_id or f"sb_{int(time.time())}",
                success=False,
                error=str(e),
                timestamp=int(time.time() * 1000),
            )

    async def handle_task_action(self, rpc_msg: chat_pb2.RpcMessage) -> chat_pb2.SandboxTaskResponse:
        request = chat_pb2.SandboxTaskRequest()
        request.ParseFromString(rpc_msg.payload)
        return await self.task_action(request)

    async def task_action(self, request: chat_pb2.SandboxTaskRequest) -> chat_pb2.SandboxTaskResponse:
        logger.info(f"Sandbox task action: {request.action}")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                if request.action == "list_tasks":
                    resp = await client.get(f"{self._sandbox_url}/api/v1/tasks")
                    data = resp.json()
                    return chat_pb2.SandboxTaskResponse(
                        success=True,
                        action=request.action,
                        data=json.dumps(data.get("tasks", [])),
                        task_id=request.task_id,
                    )
                elif request.action == "rollback_task":
                    resp = await client.post(
                        f"{self._sandbox_url}/api/v1/tasks/{request.target_task_id}/rollback"
                    )
                    return chat_pb2.SandboxTaskResponse(
                        success=True,
                        action=request.action,
                        data="Rolled back",
                        task_id=request.target_task_id,
                    )
                elif request.action == "delete_task":
                    resp = await client.delete(
                        f"{self._sandbox_url}/api/v1/tasks/{request.target_task_id}"
                    )
                    return chat_pb2.SandboxTaskResponse(
                        success=True,
                        action=request.action,
                        data="Deleted",
                        task_id=request.target_task_id,
                    )
                else:
                    return chat_pb2.SandboxTaskResponse(
                        success=False,
                        action=request.action,
                        error=f"Unknown action: {request.action}",
                        task_id=request.task_id,
                    )

        except Exception as e:
            return chat_pb2.SandboxTaskResponse(
                success=False,
                action=request.action,
                error=str(e),
                task_id=request.task_id,
            )

    async def handle_stream_execute(self, rpc_msg: chat_pb2.RpcMessage) -> chat_pb2.SandboxExecuteResponse:
        request = chat_pb2.SandboxExecuteRequest()
        request.ParseFromString(rpc_msg.payload)

        logger.info(f"Stream executing sandbox task: prompt={request.prompt[:50]}...")

        try:
            import websockets

            async with websockets.connect(
                f"{self._sandbox_ws_url}/ws/coding/persistent"
            ) as ws:
                start_msg = {
                    "action": "run",
                    "task": request.prompt,
                    "work_dir": request.work_dir or "",
                    "max_turns": request.max_turns or 30,
                }
                if request.model:
                    start_msg["model"] = request.model
                if request.api_key:
                    start_msg["api_key"] = request.api_key

                await ws.send(json.dumps(start_msg))

                final_result = ""
                turns_used = 0

                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=300)
                        event = json.loads(msg)
                        event_type = event.get("type", "")

                        if event_type == "tool_start":
                            turns_used += 1
                        elif event_type == "finish":
                            final_result = event.get("data", "")
                            break
                        elif event_type == "error":
                            final_result = event.get("data", "Error occurred")
                            break
                        elif event_type == "stopped":
                            final_result = event.get("data", "Agent stopped")
                            break

                    except asyncio.TimeoutError:
                        final_result = "Timeout waiting for agent"
                        break

                session_id = request.session_id or f"sb_{int(time.time())}"

                return chat_pb2.SandboxExecuteResponse(
                    session_id=session_id,
                    success=bool(final_result),
                    final_result=final_result,
                    turns_used=turns_used,
                    timestamp=int(time.time() * 1000),
                )

        except ImportError:
            return chat_pb2.SandboxExecuteResponse(
                session_id=request.session_id or f"sb_{int(time.time())}",
                success=False,
                error="websockets not installed. Run: pip install websockets",
                timestamp=int(time.time() * 1000),
            )
        except Exception as e:
            return chat_pb2.SandboxExecuteResponse(
                session_id=request.session_id or f"sb_{int(time.time())}",
                success=False,
                error=str(e),
                timestamp=int(time.time() * 1000),
            )

    async def handle_swarm_message(self, msg: chat_pb2.SwarmMessage) -> Optional[chat_pb2.SwarmMessage]:
        logger.info(f"Swarm message: type={msg.type} from={msg.from_id}")

        if msg.type == chat_pb2.SwarmMessage.HELP_REQUEST:
            return chat_pb2.SwarmMessage(
                type=chat_pb2.SwarmMessage.HELP_RESPONSE,
                from_id="python_sandbox_agent",
                to_id=msg.from_id,
                task=msg.task,
                result=f"[Python Sandbox Agent] Received help request for: {msg.task[:50]}",
                msg_id=msg.msg_id,
                timestamp=int(time.time() * 1000),
            )

        return None
