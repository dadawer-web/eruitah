import asyncio
import logging
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge.rpc_client import RpcClient, SyncRpcClient
from bridge import chat_pb2

logger = logging.getLogger(__name__)


class SandboxBridge:
    """
    eruitah-sandbox <-> protobuf-rpc-bridge 桥接模块

    eruitah-sandbox 可以直接 import 此模块，通过 Protobuf RPC 与 Java/C++ 后端通信。

    使用方式 (在 eruitah-sandbox 中):
        sys.path.insert(0, '/home/xmy/code/protobuf-rpc-bridge/python')
        from services.sandbox_bridge import SandboxBridge

        bridge = SandboxBridge(java_host='127.0.0.1', java_port=9999)
        bridge.connect()

        # 调用 Java 后端的 ChatService
        response = bridge.call_chat(user_id=1, bot_id=10000,
                                     user_name='agent', message='hello',
                                     session_id='s1')

        # 调用 C++ muduo 后端
        response = bridge.call_chat_raw(user_id=1, bot_id=10000,
                                         user_name='agent', message='hello',
                                         session_id='s1')

        bridge.disconnect()
    """

    def __init__(
        self,
        java_host: str = "127.0.0.1",
        java_port: int = 9999,
        cpp_host: str = "127.0.0.1",
        cpp_port: int = 8888,
        sync: bool = True,
    ):
        self._java_host = java_host
        self._java_port = java_port
        self._cpp_host = cpp_host
        self._cpp_port = cpp_port
        self._sync = sync

        if sync:
            self._java_client = SyncRpcClient(java_host, java_port)
            self._cpp_client = SyncRpcClient(cpp_host, cpp_port)
        else:
            self._java_client = RpcClient(java_host, java_port)
            self._cpp_client = RpcClient(cpp_host, cpp_port)

    def connect(self):
        if self._sync:
            self._java_client.connect()
            try:
                self._cpp_client.connect()
            except Exception as e:
                logger.warning(f"C++ backend not available: {e}")
        else:
            logger.warning("Use await bridge.connect_async() for async mode")

    async def connect_async(self):
        await self._java_client.connect()
        try:
            await self._cpp_client.connect()
        except Exception as e:
            logger.warning(f"C++ backend not available: {e}")

    def disconnect(self):
        if self._sync:
            self._java_client.disconnect()
            try:
                self._cpp_client.disconnect()
            except Exception:
                pass
        else:
            logger.warning("Use await bridge.disconnect_async() for async mode")

    async def disconnect_async(self):
        await self._java_client.disconnect()
        try:
            await self._cpp_client.disconnect()
        except Exception:
            pass

    @property
    def java_connected(self) -> bool:
        return self._java_client.connected

    @property
    def cpp_connected(self) -> bool:
        return self._cpp_client.connected

    def call_chat(
        self,
        user_id: int,
        bot_id: int,
        user_name: str,
        message: str,
        session_id: str = "",
        metadata: Optional[dict] = None,
    ) -> Optional[chat_pb2.ChatResponse]:
        request = chat_pb2.ChatRequest(
            user_id=user_id,
            bot_id=bot_id,
            user_name=user_name,
            message=message,
            session_id=session_id,
            timestamp=int(asyncio.get_event_loop().time() * 1000) if not self._sync else 0,
        )
        if metadata:
            for k, v in metadata.items():
                request.metadata[k] = str(v)

        if self._sync:
            return self._java_client.call(
                "ChatService", "Chat", request, chat_pb2.ChatResponse, timeout=30
            )
        else:
            return None

    async def call_chat_async(
        self,
        user_id: int,
        bot_id: int,
        user_name: str,
        message: str,
        session_id: str = "",
        metadata: Optional[dict] = None,
    ) -> Optional[chat_pb2.ChatResponse]:
        request = chat_pb2.ChatRequest(
            user_id=user_id,
            bot_id=bot_id,
            user_name=user_name,
            message=message,
            session_id=session_id,
            timestamp=int(asyncio.get_event_loop().time() * 1000),
        )
        if metadata:
            for k, v in metadata.items():
                request.metadata[k] = str(v)

        rpc_msg = await self._java_client.call(
            "ChatService", "Chat", request, chat_pb2.ChatResponse, timeout=30
        )
        if rpc_msg and rpc_msg.payload:
            resp = chat_pb2.ChatResponse()
            resp.ParseFromString(rpc_msg.payload)
            return resp
        return None

    def call_chat_raw(
        self,
        user_id: int,
        bot_id: int,
        user_name: str,
        message: str,
        session_id: str = "",
    ) -> Optional[chat_pb2.ChatResponse]:
        request = chat_pb2.ChatRequest(
            user_id=user_id,
            bot_id=bot_id,
            user_name=user_name,
            message=message,
            session_id=session_id,
            timestamp=0,
        )

        if self._sync:
            return self._cpp_client.call(
                "ChatService", "Chat", request, chat_pb2.ChatResponse, timeout=30
            )
        else:
            return None

    def call_group_chat(
        self,
        group_id: int,
        sender_id: int,
        message: str,
        session_id: str = "",
    ) -> Optional[chat_pb2.GroupChatResponse]:
        request = chat_pb2.GroupChatRequest(
            group_id=group_id,
            sender_id=sender_id,
            message=message,
            session_id=session_id,
            timestamp=0,
        )

        if self._sync:
            return self._java_client.call(
                "ChatService", "GroupChat", request, chat_pb2.GroupChatResponse, timeout=30
            )
        else:
            return None

    def call_sandbox_execute(
        self,
        prompt: str,
        model: str = "gpt-4o",
        max_turns: int = 30,
        work_dir: str = "",
        api_key: str = "",
        base_url: str = "",
        provider: str = "",
        session_id: str = "",
    ) -> Optional[chat_pb2.SandboxExecuteResponse]:
        request = chat_pb2.SandboxExecuteRequest(
            prompt=prompt,
            model=model,
            max_turns=max_turns,
            work_dir=work_dir or None,
            api_key=api_key or None,
            base_url=base_url or None,
            provider=provider or None,
            session_id=session_id or None,
        )

        if self._sync:
            return self._java_client.call(
                "ChatService", "SandboxExecute", request, chat_pb2.SandboxExecuteResponse, timeout=300
            )
        else:
            return None

    def send_swarm_message(
        self,
        msg_type: int,
        from_id: str,
        content: str = "",
        to_id: str = "",
        task: str = "",
    ) -> bool:
        msg = chat_pb2.SwarmMessage(
            type=msg_type,
            from_id=from_id,
            to_id=to_id,
            content=content,
            task=task,
            timestamp=int(asyncio.get_event_loop().time() * 1000) if not self._sync else 0,
        )

        try:
            if self._sync:
                self._java_client.send_message(msg)
            return True
        except Exception as e:
            logger.error(f"Failed to send swarm message: {e}")
            return False


def create_bridge(
    java_host: str = "127.0.0.1",
    java_port: int = 9999,
    cpp_host: str = "127.0.0.1",
    cpp_port: int = 8888,
    sync: bool = True,
) -> SandboxBridge:
    return SandboxBridge(
        java_host=java_host,
        java_port=java_port,
        cpp_host=cpp_host,
        cpp_port=cpp_port,
        sync=sync,
    )
