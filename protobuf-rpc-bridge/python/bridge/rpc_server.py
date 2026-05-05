import asyncio
import logging
from typing import Callable, Dict, Optional

from google.protobuf.message import Message as ProtobufMessage

from bridge import chat_pb2
from bridge.codec import encode, ProtobufCodec

logger = logging.getLogger(__name__)


class RpcServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9998):
        self._host = host
        self._port = port
        self._server: Optional[asyncio.AbstractServer] = None
        self._handlers: Dict[str, Callable] = {}
        self._direct_handlers: Dict[type, Callable] = {}

    def register_rpc(self, service_name: str, method_name: str, handler: Callable):
        key = f"{service_name}.{method_name}"
        self._handlers[key] = handler
        logger.info(f"Registered RPC handler: {key}")

    def register_direct(self, message_class: type, handler: Callable):
        self._direct_handlers[message_class] = handler
        logger.info(f"Registered direct handler: {message_class.__name__}")

    async def start(self):
        self._server = await asyncio.start_server(
            self._handle_connection, self._host, self._port
        )
        logger.info(f"Python RPC Server started on {self._host}:{self._port}")

    async def serve_forever(self):
        if self._server is None:
            await self.start()
        async with self._server:
            await self._server.serve_forever()

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("Python RPC Server stopped")

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        addr = writer.get_extra_info("peername")
        logger.info(f"Client connected: {addr}")

        codec = ProtobufCodec()

        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                codec.feed(data, lambda msg: asyncio.create_task(
                    self._dispatch(msg, writer)
                ))
        except Exception as e:
            logger.error(f"Connection error from {addr}: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            logger.info(f"Client disconnected: {addr}")

    async def _dispatch(self, message: ProtobufMessage, writer: asyncio.StreamWriter):
        if isinstance(message, chat_pb2.RpcMessage):
            await self._handle_rpc(message, writer)
        else:
            handler = self._direct_handlers.get(type(message))
            if handler:
                try:
                    response = await handler(message) if asyncio.iscoroutinefunction(handler) else handler(message)
                    if response:
                        writer.write(encode(response))
                        await writer.drain()
                except Exception as e:
                    logger.error(f"Direct handler error: {e}")

    async def _handle_rpc(self, rpc_msg: chat_pb2.RpcMessage, writer: asyncio.StreamWriter):
        if rpc_msg.type != chat_pb2.RpcMessage.REQUEST:
            return

        key = f"{rpc_msg.service_name}.{rpc_msg.method_name}"
        handler = self._handlers.get(key)

        if handler is None:
            error_resp = chat_pb2.RpcMessage(
                type=chat_pb2.RpcMessage.ERROR,
                id=rpc_msg.id,
                error_code=404,
                error_desc=f"Unknown method: {key}",
            )
            writer.write(encode(error_resp))
            await writer.drain()
            return

        try:
            response = await handler(rpc_msg) if asyncio.iscoroutinefunction(handler) else handler(rpc_msg)

            resp_msg = chat_pb2.RpcMessage(
                type=chat_pb2.RpcMessage.RESPONSE,
                id=rpc_msg.id,
                payload=response.SerializeToString(),
            )
            writer.write(encode(resp_msg))
            await writer.drain()
            logger.info(f"Sent RPC response for id={rpc_msg.id}")

        except Exception as e:
            logger.error(f"RPC handler error for {key}: {e}")
            error_resp = chat_pb2.RpcMessage(
                type=chat_pb2.RpcMessage.ERROR,
                id=rpc_msg.id,
                error_code=500,
                error_desc=str(e),
            )
            writer.write(encode(error_resp))
            await writer.drain()
