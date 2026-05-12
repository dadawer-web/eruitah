import asyncio
import json
import logging
import time
from typing import AsyncGenerator, Dict, List, Optional

from bridge import chat_pb2
from bridge.rpc_server import RpcServer

logger = logging.getLogger(__name__)


class SandboxServiceAdapter:
    def __init__(
        self,
        sandbox_url: str = "http://127.0.0.1:8001",
        sandbox_ws_url: str = "ws://127.0.0.1:8001",
    ):
        self._sandbox_url = sandbox_url.rstrip("/")
        self._sandbox_ws_url = sandbox_ws_url.rstrip("/")

    def register_handlers(self, server: RpcServer):
        server.register_rpc("SandboxService", "Execute", self.handle_execute)
        server.register_rpc("SandboxService", "StreamExecute", self.handle_stream_execute)
        server.register_rpc("SandboxService", "TaskAction", self.handle_task_action)
        server.register_rpc("SandboxService", "HealthCheck", self.handle_health_check)
        server.register_rpc("SandboxService", "StopAgent", self.handle_stop_agent)
        server.register_direct(chat_pb2.SandboxExecuteRequest, self.handle_execute_direct)
        server.register_direct(chat_pb2.SwarmMessage, self.handle_swarm_message)
        logger.info("Registered SandboxService handlers (v2 - aligned with eruitah-sandbox API)")

    async def _get_http_client(self, timeout: float = 300):
        try:
            import httpx
            return httpx.AsyncClient(timeout=timeout)
        except ImportError:
            return None

    async def handle_execute(self, rpc_msg: chat_pb2.RpcMessage) -> chat_pb2.SandboxExecuteResponse:
        request = chat_pb2.SandboxExecuteRequest()
        request.ParseFromString(rpc_msg.payload)
        return await self.execute(request)

    async def handle_execute_direct(self, request: chat_pb2.SandboxExecuteRequest) -> chat_pb2.SandboxExecuteResponse:
        return await self.execute(request)

    async def execute(self, request: chat_pb2.SandboxExecuteRequest) -> chat_pb2.SandboxExecuteResponse:
        logger.info(f"Executing sandbox task: prompt={request.prompt[:80]}...")

        client = await self._get_http_client(timeout=300)
        if client is None:
            return chat_pb2.SandboxExecuteResponse(
                session_id=request.session_id or f"sb_{int(time.time())}",
                success=False,
                error="httpx not installed. Run: pip install httpx",
                timestamp=int(time.time() * 1000),
            )

        async with client:
            payload = {
                "prompt": request.prompt,
                "max_turns": request.max_turns or 30,
            }
            if request.work_dir:
                payload["work_dir"] = request.work_dir
            if request.model:
                payload["model"] = request.model
            if request.api_key:
                payload["api_key"] = request.api_key
            if request.base_url:
                payload["base_url"] = request.base_url
            if request.provider:
                payload["provider"] = request.provider

            try:
                resp = await client.post(
                    f"{self._sandbox_url}/api/v1/execute",
                    json=payload,
                )
                result = resp.json()

                session_id = request.session_id or f"sb_{int(time.time())}"
                success = result.get("success", False)
                message = result.get("message", "")
                events = result.get("events", [])
                turns_used = sum(1 for e in events if e.get("type") == "tool_start")

                return chat_pb2.SandboxExecuteResponse(
                    session_id=session_id,
                    success=success,
                    error="" if success else message,
                    final_result=message,
                    turns_used=turns_used,
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

    async def handle_stream_execute(self, rpc_msg: chat_pb2.RpcMessage) -> chat_pb2.SandboxExecuteResponse:
        request = chat_pb2.SandboxExecuteRequest()
        request.ParseFromString(rpc_msg.payload)
        logger.info(f"Stream executing sandbox task: prompt={request.prompt[:80]}...")

        try:
            import websockets
        except ImportError:
            return chat_pb2.SandboxExecuteResponse(
                session_id=request.session_id or f"sb_{int(time.time())}",
                success=False,
                error="websockets not installed. Run: pip install websockets",
                timestamp=int(time.time() * 1000),
            )

        try:
            async with websockets.connect(
                f"{self._sandbox_ws_url}/ws/coding/persistent",
                max_size=10 * 1024 * 1024,
            ) as ws:
                start_msg = {
                    "action": "run",
                    "task": request.prompt,
                }
                if request.work_dir:
                    start_msg["work_dir"] = request.work_dir
                if request.max_turns:
                    start_msg["max_turns"] = request.max_turns
                if request.model:
                    start_msg["model"] = request.model
                if request.api_key:
                    start_msg["api_key"] = request.api_key

                await ws.send(json.dumps(start_msg))

                final_result = ""
                turns_used = 0
                error_msg = ""

                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=600)
                        event = json.loads(msg)
                        event_type = event.get("type", "")

                        if event_type == "tool_start":
                            turns_used += 1
                        elif event_type == "finish":
                            final_result = event.get("data", "")
                            break
                        elif event_type == "error":
                            error_msg = event.get("data", "Error occurred")
                            break
                        elif event_type == "stopped":
                            final_result = event.get("data", "Agent stopped")
                            break

                    except asyncio.TimeoutError:
                        error_msg = "Timeout waiting for agent"
                        break

                session_id = request.session_id or f"sb_{int(time.time())}"

                return chat_pb2.SandboxExecuteResponse(
                    session_id=session_id,
                    success=bool(final_result) and not error_msg,
                    error=error_msg,
                    final_result=final_result or error_msg,
                    turns_used=turns_used,
                    timestamp=int(time.time() * 1000),
                )

        except Exception as e:
            logger.error(f"Stream execute error: {e}")
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
        action = request.action
        logger.info(f"Sandbox task action: {action}")

        if action == "list_tasks":
            return await self._task_list_tasks(request)
        elif action == "rollback_task":
            return await self._task_ws_command(request, "rollback_task")
        elif action == "delete_task":
            return await self._task_ws_command(request, "delete_task")
        elif action == "stop_agent":
            return await self._task_ws_command(request, "stop_agent")
        elif action == "switch_task":
            return await self._task_switch(request)
        elif action == "health_check":
            return await self._task_health_check(request)
        else:
            return chat_pb2.SandboxTaskResponse(
                success=False,
                action=action,
                error=f"Unknown action: {action}",
                task_id=request.task_id,
            )

    async def _task_list_tasks(self, request: chat_pb2.SandboxTaskRequest) -> chat_pb2.SandboxTaskResponse:
        client = await self._get_http_client(timeout=30)
        if client is None:
            return chat_pb2.SandboxTaskResponse(
                success=False, action="list_tasks",
                error="httpx not installed", task_id=request.task_id,
            )

        async with client:
            try:
                params = {}
                if request.work_dir:
                    params["project_path"] = request.work_dir
                resp = await client.get(
                    f"{self._sandbox_url}/api/v1/tasks",
                    params=params,
                )
                data = resp.json()
                return chat_pb2.SandboxTaskResponse(
                    success=True,
                    action="list_tasks",
                    data=json.dumps(data.get("tasks", [])),
                    task_id=request.task_id,
                )
            except Exception as e:
                return chat_pb2.SandboxTaskResponse(
                    success=False, action="list_tasks",
                    error=str(e), task_id=request.task_id,
                )

    async def _task_switch(self, request: chat_pb2.SandboxTaskRequest) -> chat_pb2.SandboxTaskResponse:
        client = await self._get_http_client(timeout=30)
        if client is None:
            return chat_pb2.SandboxTaskResponse(
                success=False, action="switch_task",
                error="httpx not installed", task_id=request.task_id,
            )

        async with client:
            try:
                target_id = request.target_task_id or request.task_id
                resp = await client.post(
                    f"{self._sandbox_url}/api/v1/tasks/{target_id}/switch",
                    json={"work_dir": request.work_dir or ""},
                )
                data = resp.json()
                return chat_pb2.SandboxTaskResponse(
                    success=data.get("success", False),
                    action="switch_task",
                    data=json.dumps(data),
                    task_id=target_id,
                )
            except Exception as e:
                return chat_pb2.SandboxTaskResponse(
                    success=False, action="switch_task",
                    error=str(e), task_id=request.task_id,
                )

    async def _task_ws_command(self, request: chat_pb2.SandboxTaskRequest, action: str) -> chat_pb2.SandboxTaskResponse:
        try:
            import websockets
        except ImportError:
            return chat_pb2.SandboxTaskResponse(
                success=False, action=action,
                error="websockets not installed", task_id=request.task_id,
            )

        try:
            async with websockets.connect(
                f"{self._sandbox_ws_url}/ws/coding",
                max_size=10 * 1024 * 1024,
            ) as ws:
                cmd = {
                    "type": "system_command",
                    "action": action,
                }
                target_id = request.target_task_id or request.task_id
                if target_id:
                    cmd["task_id"] = target_id
                if request.work_dir:
                    cmd["work_dir"] = request.work_dir

                await ws.send(json.dumps(cmd))

                result_data = ""
                deadline = time.time() + 30

                while time.time() < deadline:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=10)
                        event = json.loads(msg)
                        event_type = event.get("type", "")

                        if event_type == "system_msg":
                            result_data += event.get("content", "") + "\n"
                        elif event_type == "task_rolled_back":
                            return chat_pb2.SandboxTaskResponse(
                                success=True, action=action,
                                data=json.dumps(event),
                                task_id=target_id,
                            )
                        elif event_type == "task_deleted":
                            return chat_pb2.SandboxTaskResponse(
                                success=True, action=action,
                                data="Task deleted",
                                task_id=target_id,
                            )
                        elif event_type == "error":
                            return chat_pb2.SandboxTaskResponse(
                                success=False, action=action,
                                error=event.get("data", "Unknown error"),
                                task_id=target_id,
                            )
                    except asyncio.TimeoutError:
                        break

                return chat_pb2.SandboxTaskResponse(
                    success=bool(result_data),
                    action=action,
                    data=result_data.strip() or "Command sent (no confirmation received)",
                    task_id=target_id,
                )

        except Exception as e:
            logger.error(f"WS command error: {e}")
            return chat_pb2.SandboxTaskResponse(
                success=False, action=action,
                error=str(e), task_id=request.task_id,
            )

    async def handle_health_check(self, rpc_msg: chat_pb2.RpcMessage) -> chat_pb2.SandboxTaskResponse:
        request = chat_pb2.SandboxTaskRequest()
        request.ParseFromString(rpc_msg.payload)
        return await self._task_health_check(request)

    async def _task_health_check(self, request: chat_pb2.SandboxTaskRequest) -> chat_pb2.SandboxTaskResponse:
        client = await self._get_http_client(timeout=10)
        if client is None:
            return chat_pb2.SandboxTaskResponse(
                success=False, action="health_check",
                error="httpx not installed",
            )

        async with client:
            try:
                resp = await client.get(f"{self._sandbox_url}/api/v1/health")
                data = resp.json()
                return chat_pb2.SandboxTaskResponse(
                    success=True,
                    action="health_check",
                    data=json.dumps(data),
                )
            except Exception as e:
                return chat_pb2.SandboxTaskResponse(
                    success=False, action="health_check",
                    error=str(e),
                )

    async def handle_stop_agent(self, rpc_msg: chat_pb2.RpcMessage) -> chat_pb2.SandboxTaskResponse:
        request = chat_pb2.SandboxTaskRequest()
        request.ParseFromString(rpc_msg.payload)
        return await self._task_ws_command(request, "stop_agent")

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
