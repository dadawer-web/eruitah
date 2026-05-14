import asyncio
import json
import logging
import os
import sys
import time
import uuid
from typing import Callable, Dict, Optional

from google.protobuf.message import Message as ProtobufMessage

from bridge import chat_pb2
from bridge.codec import encode, ProtobufCodec

logger = logging.getLogger(__name__)


class StreamingRpcServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9997):
        self._host = host
        self._port = port
        self._server: Optional[asyncio.AbstractServer] = None
        self._handlers: Dict[str, Callable] = {}
        self._active_streams: Dict[int, asyncio.Task] = {}

    def register(self, service_name: str, method_name: str, handler: Callable):
        key = f"{service_name}.{method_name}"
        self._handlers[key] = handler
        logger.info(f"Registered streaming RPC handler: {key}")

    async def start(self):
        self._server = await asyncio.start_server(
            self._handle_connection, self._host, self._port
        )
        logger.info(f"Streaming RPC Server started on {self._host}:{self._port}")

    async def serve_forever(self):
        if self._server is None:
            await self.start()
        async with self._server:
            await self._server.serve_forever()

    async def stop(self):
        for rpc_id, task in self._active_streams.items():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._active_streams.clear()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
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
        except ConnectionResetError:
            logger.warning(f"Connection reset by client: {addr}")
        except Exception as e:
            logger.error(f"Connection error from {addr}: {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info(f"Client disconnected: {addr}")

    async def _dispatch(self, message: ProtobufMessage, writer: asyncio.StreamWriter):
        if not isinstance(message, chat_pb2.RpcMessage):
            return
        if message.type != chat_pb2.RpcMessage.REQUEST:
            return

        key = f"{message.service_name}.{message.method_name}"
        handler = self._handlers.get(key)

        if handler is None:
            await self._send_error(writer, message.id, 404, f"Unknown method: {key}")
            return

        try:
            result = handler(message)

            if hasattr(result, '__aiter__'):
                try:
                    async for chunk in result:
                        if writer.is_closing():
                            logger.warning(f"Client disconnected during stream for {key} id={message.id}")
                            break
                        await self._send_stream_chunk(writer, message.id, chunk)
                except asyncio.CancelledError:
                    logger.warning(f"Stream cancelled for {key} id={message.id}")
                    await self._send_error(writer, message.id, 499, "Stream cancelled")
                    return
                except Exception as stream_err:
                    logger.error(f"Stream iteration error for {key} id={message.id}: {stream_err}", exc_info=True)
                    try:
                        await self._send_error(writer, message.id, 500, f"Stream error: {stream_err}")
                    except Exception:
                        pass
                    return

                if not writer.is_closing():
                    await self._send_stream_end(writer, message.id)

            elif hasattr(result, '__iter__') and not isinstance(result, (bytes, str, dict, ProtobufMessage)):
                try:
                    for chunk in result:
                        if isinstance(chunk, ProtobufMessage):
                            await self._send_stream_chunk(writer, message.id, chunk)
                    await self._send_stream_end(writer, message.id)
                except Exception as iter_err:
                    logger.error(f"Iteration error for {key} id={message.id}: {iter_err}", exc_info=True)
                    try:
                        await self._send_error(writer, message.id, 500, f"Iteration error: {iter_err}")
                    except Exception:
                        pass
            else:
                if isinstance(result, ProtobufMessage):
                    await self._send_response(writer, message.id, result)
                else:
                    await self._send_response(writer, message.id, result)

        except Exception as e:
            logger.error(f"Handler error for {key}: {e}", exc_info=True)
            try:
                await self._send_error(writer, message.id, 500, str(e))
            except Exception:
                pass

    async def _send_response(self, writer: asyncio.StreamWriter, rpc_id: int, payload: ProtobufMessage):
        resp = chat_pb2.RpcMessage(
            type=chat_pb2.RpcMessage.RESPONSE,
            id=rpc_id,
            service_name="",
            method_name="",
            payload=payload.SerializeToString(),
        )
        writer.write(encode(resp))
        await writer.drain()

    async def _send_stream_chunk(self, writer: asyncio.StreamWriter, rpc_id: int, payload: ProtobufMessage):
        resp = chat_pb2.RpcMessage(
            type=chat_pb2.RpcMessage.STREAM,
            id=rpc_id,
            service_name="",
            method_name="",
            payload=payload.SerializeToString(),
        )
        writer.write(encode(resp))
        await writer.drain()

    async def _send_stream_end(self, writer: asyncio.StreamWriter, rpc_id: int):
        resp = chat_pb2.RpcMessage(
            type=chat_pb2.RpcMessage.STREAM_END,
            id=rpc_id,
            service_name="",
            method_name="",
        )
        writer.write(encode(resp))
        await writer.drain()

    async def _send_error(self, writer: asyncio.StreamWriter, rpc_id: int, code: int, desc: str):
        resp = chat_pb2.RpcMessage(
            type=chat_pb2.RpcMessage.ERROR,
            id=rpc_id,
            error_code=code,
            error_desc=desc,
        )
        writer.write(encode(resp))
        await writer.drain()
