import asyncio
import logging
import threading
import time
from typing import AsyncGenerator, Callable, Dict, Optional

from google.protobuf.message import Message as ProtobufMessage

from bridge import chat_pb2
from bridge.codec import encode, decode, ProtobufCodec

logger = logging.getLogger(__name__)


class RpcClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 9999):
        self._host = host
        self._port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._id = 0
        self._pending: Dict[int, asyncio.Future] = {}
        self._stream_queues: Dict[int, asyncio.Queue] = {}
        self._loop: Optional[asyncio.EventLoop] = None
        self._connected = False
        self._recv_task: Optional[asyncio.Task] = None
        self._on_event: Optional[Callable] = None

    @property
    def connected(self) -> bool:
        return self._connected and self._writer is not None and not self._writer.is_closing()

    def set_event_handler(self, handler: Callable[[ProtobufMessage], None]):
        self._on_event = handler

    async def connect(self):
        self._loop = asyncio.get_event_loop()
        self._reader, self._writer = await asyncio.open_connection(
            self._host, self._port
        )
        self._connected = True
        self._recv_task = asyncio.create_task(self._recv_loop())
        logger.info(f"Connected to {self._host}:{self._port}")

    async def disconnect(self):
        self._connected = False
        if self._recv_task:
            self._recv_task.cancel()
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        logger.info("Disconnected")

    async def call(
        self,
        service_name: str,
        method_name: str,
        request: ProtobufMessage,
        response_class: type,
        timeout: float = 30.0,
    ) -> Optional[ProtobufMessage]:
        if not self.connected:
            raise ConnectionError("Not connected")

        self._id += 1
        rpc_id = self._id

        rpc_msg = chat_pb2.RpcMessage(
            type=chat_pb2.RpcMessage.REQUEST,
            id=rpc_id,
            service_name=service_name,
            method_name=method_name,
            payload=request.SerializeToString(),
        )

        future = self._loop.create_future()
        self._pending[rpc_id] = future

        data = encode(rpc_msg)
        self._writer.write(data)
        await self._writer.drain()

        logger.info(f"Sent RPC: {service_name}.{method_name} id={rpc_id}")

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.error(f"RPC timeout: {service_name}.{method_name} id={rpc_id}")
            self._pending.pop(rpc_id, None)
            return None

    async def send_message(self, message: ProtobufMessage):
        if not self.connected:
            raise ConnectionError("Not connected")

        data = encode(message)
        self._writer.write(data)
        await self._writer.drain()

    async def call_stream(
        self,
        service_name: str,
        method_name: str,
        request: ProtobufMessage,
        timeout: float = 600.0,
    ) -> AsyncGenerator[chat_pb2.RpcMessage, None]:
        if not self.connected:
            raise ConnectionError("Not connected")

        self._id += 1
        rpc_id = self._id

        rpc_msg = chat_pb2.RpcMessage(
            type=chat_pb2.RpcMessage.REQUEST,
            id=rpc_id,
            service_name=service_name,
            method_name=method_name,
            payload=request.SerializeToString(),
        )

        queue = asyncio.Queue()
        self._stream_queues[rpc_id] = queue

        data = encode(rpc_msg)
        self._writer.write(data)
        await self._writer.drain()

        logger.info(f"Sent streaming RPC: {service_name}.{method_name} id={rpc_id}")

        try:
            deadline = time.time() + timeout
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    logger.error(f"Stream timeout: {service_name}.{method_name} id={rpc_id}")
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    logger.error(f"Stream timeout: {service_name}.{method_name} id={rpc_id}")
                    break

                if item is None:
                    break
                if isinstance(item, Exception):
                    raise item
                yield item
        finally:
            self._stream_queues.pop(rpc_id, None)

    async def _recv_loop(self):
        codec = ProtobufCodec()
        try:
            while self._connected:
                data = await self._reader.read(65536)
                if not data:
                    logger.info("Connection closed by remote")
                    self._connected = False
                    break

                codec.feed(data, self._on_message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Recv loop error: {e}")
            self._connected = False

    def _on_message(self, message: ProtobufMessage):
        if isinstance(message, chat_pb2.RpcMessage):
            self._handle_rpc_response(message)
        elif self._on_event:
            self._on_event(message)

    def _handle_rpc_response(self, rpc_msg: chat_pb2.RpcMessage):
        if rpc_msg.type == chat_pb2.RpcMessage.RESPONSE:
            future = self._pending.pop(rpc_msg.id, None)
            if future and not future.done():
                future.set_result(rpc_msg)
            logger.info(f"Received RPC response id={rpc_msg.id}")
        elif rpc_msg.type == chat_pb2.RpcMessage.STREAM:
            queue = self._stream_queues.get(rpc_msg.id)
            if queue:
                queue.put_nowait(rpc_msg)
        elif rpc_msg.type == chat_pb2.RpcMessage.STREAM_END:
            queue = self._stream_queues.get(rpc_msg.id)
            if queue:
                queue.put_nowait(None)
            logger.info(f"Stream ended for id={rpc_msg.id}")
        elif rpc_msg.type == chat_pb2.RpcMessage.ERROR:
            future = self._pending.pop(rpc_msg.id, None)
            queue = self._stream_queues.get(rpc_msg.id)
            if future and not future.done():
                future.set_exception(
                    RuntimeError(f"RPC error: {rpc_msg.error_desc}")
                )
            if queue:
                queue.put_nowait(RuntimeError(f"RPC error: {rpc_msg.error_desc}"))
            logger.error(f"RPC error id={rpc_msg.id}: {rpc_msg.error_desc}")


class SyncRpcClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 9999):
        self._async_client = RpcClient(host, port)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def connect(self):
        self._thread.start()
        asyncio.run_coroutine_threadsafe(self._async_client.connect(), self._loop).result(
            timeout=10
        )

    def disconnect(self):
        asyncio.run_coroutine_threadsafe(
            self._async_client.disconnect(), self._loop
        ).result(timeout=5)
        self._loop.call_soon_threadsafe(self._loop.stop)

    @property
    def connected(self) -> bool:
        return self._async_client.connected

    def call(
        self,
        service_name: str,
        method_name: str,
        request: ProtobufMessage,
        response_class: type,
        timeout: float = 30.0,
    ) -> Optional[ProtobufMessage]:
        coro = self._async_client.call(
            service_name, method_name, request, response_class, timeout
        )
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        rpc_msg = future.result(timeout=timeout + 5)

        if rpc_msg and rpc_msg.payload:
            response = response_class()
            response.ParseFromString(rpc_msg.payload)
            return response
        return None

    def send_message(self, message: ProtobufMessage):
        coro = self._async_client.send_message(message)
        asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=10)
