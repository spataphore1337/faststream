from types import TracebackType
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncContextManager,
    Optional,
    Type,
    Union,
    cast,
)

import anyio
from aio_pika.abc import AbstractIncomingMessage

from faststream.broker.parsers import resolve_custom_func
from faststream.exceptions import WRONG_PUBLISH_ARGS
from faststream.rabbit.parser import AioPikaParser
from faststream.rabbit.schemas import RABBIT_REPLY, RabbitExchange
from faststream.utils.functions import fake_context, timeout_scope

if TYPE_CHECKING:
    import aiormq
    from aio_pika import IncomingMessage, RobustChannel, RobustQueue
    from aio_pika.abc import DateType, HeadersType, TimeoutType
    from anyio.streams.memory import MemoryObjectReceiveStream

    from faststream.broker.message import StreamMessage
    from faststream.broker.types import (
        AsyncCustomDecoder,
        AsyncCustomParser,
        AsyncDecoder,
        AsyncParser,
    )
    from faststream.rabbit.helpers import RabbitDeclarer
    from faststream.rabbit.types import AioPikaSendableMessage
    from faststream.types import SendableMessage


class AioPikaFastProducer:
    """A class for fast producing messages using aio-pika."""

    _decoder: "AsyncDecoder[StreamMessage[IncomingMessage]]"
    _parser: "AsyncParser[IncomingMessage]"

    def __init__(
        self,
        *,
        channel: "RobustChannel",
        declarer: "RabbitDeclarer",
        parser: Optional["AsyncCustomParser[IncomingMessage]"],
        decoder: Optional["AsyncCustomDecoder[StreamMessage[IncomingMessage]]"],
    ) -> None:
        """Initialize a class instance.

        Args:
            channel: The aio_pika.RobustChannel object.
            declarer: The RabbitDeclarer object.
            parser: An optional AsyncCustomParser object for parsing incoming messages.
            decoder: An optional AsyncCustomDecoder object for decoding incoming messages.
        """
        self._channel = channel
        self.declarer = declarer
        self._parser = resolve_custom_func(parser, AioPikaParser.parse_message)
        self._decoder = resolve_custom_func(decoder, AioPikaParser.decode_message)
        self._rpc_lock = anyio.Lock()

    async def publish(
        self,
        message: "AioPikaSendableMessage" = "",
        exchange: Union["RabbitExchange", str, None] = None,
        *,
        routing_key: str = "",
        mandatory: bool = True,
        immediate: bool = False,
        timeout: "TimeoutType" = None,
        rpc: bool = False,
        rpc_timeout: Optional[float] = 30.0,
        raise_timeout: bool = False,
        persist: bool = False,
        reply_to: Optional[str] = None,
        headers: Optional["HeadersType"] = None,
        content_type: Optional[str] = None,
        content_encoding: Optional[str] = None,
        priority: Optional[int] = None,
        correlation_id: Optional[str] = None,
        expiration: Optional["DateType"] = None,
        message_id: Optional[str] = None,
        timestamp: Optional["DateType"] = None,
        message_type: Optional[str] = None,
        user_id: Optional[str] = None,
        app_id: Optional[str] = None,
    ) -> Optional[Any]:
        """Publish a message to a RabbitMQ queue."""
        context: AsyncContextManager[
            Optional["MemoryObjectReceiveStream[IncomingMessage]"]
        ]
        if rpc:
            if reply_to is not None:
                raise WRONG_PUBLISH_ARGS

            context = _RPCCallback(
                self._rpc_lock,
                await self.declarer.declare_queue(RABBIT_REPLY),
            )
        else:
            context = fake_context()

        async with context as response_queue:
            r = await self._publish(
                message=message,
                exchange=exchange,
                routing_key=routing_key,
                mandatory=mandatory,
                immediate=immediate,
                timeout=timeout,
                persist=persist,
                reply_to=reply_to if response_queue is None else RABBIT_REPLY.name,
                headers=headers,
                content_type=content_type,
                content_encoding=content_encoding,
                priority=priority,
                correlation_id=correlation_id,
                expiration=expiration,
                message_id=message_id,
                timestamp=timestamp,
                message_type=message_type,
                user_id=user_id,
                app_id=app_id,
            )

            if response_queue is None:
                return r

            else:
                msg: Optional["IncomingMessage"] = None
                with timeout_scope(rpc_timeout, raise_timeout):
                    msg = await response_queue.receive()

                if msg:  # pragma: no branch
                    return await self._decoder(await self._parser(msg))

        return None

    async def _publish(
        self,
        message: "AioPikaSendableMessage",
        *,
        exchange: Union["RabbitExchange", str, None],
        routing_key: str,
        mandatory: bool,
        immediate: bool,
        timeout: "TimeoutType",
        persist: bool,
        reply_to: Optional[str],
        headers: Optional["HeadersType"],
        content_type: Optional[str],
        content_encoding: Optional[str],
        priority: Optional[int],
        correlation_id: Optional[str],
        expiration: Optional["DateType"],
        message_id: Optional[str],
        timestamp: Optional["DateType"],
        message_type: Optional[str],
        user_id: Optional[str],
        app_id: Optional[str],
    ) -> Union["aiormq.abc.ConfirmationFrameType", "SendableMessage"]:
        """Publish a message to a RabbitMQ exchange."""
        p_exchange = RabbitExchange.validate(exchange)

        if p_exchange is None:
            exchange_obj = self._channel.default_exchange
        else:
            p_exchange.passive = True
            exchange_obj = await self.declarer.declare_exchange(p_exchange)

        message = AioPikaParser.encode_message(
            message=message,
            persist=persist,
            reply_to=reply_to,
            headers=headers,
            content_type=content_type,
            content_encoding=content_encoding,
            priority=priority,
            correlation_id=correlation_id,
            expiration=expiration,
            message_id=message_id,
            timestamp=timestamp,
            message_type=message_type,
            user_id=user_id,
            app_id=app_id,
        )

        return await exchange_obj.publish(
            message=message,
            routing_key=routing_key,
            mandatory=mandatory,
            immediate=immediate,
            timeout=timeout,
        )


class _RPCCallback:
    """A class representing an RPC callback.

    Attributes:
        lock : a lock object used for synchronization
        queue : a robust queue object for receiving callback messages

    Methods:
        __aenter__ : Asynchronous context manager method that acquires the lock and returns a memory object receive stream for incoming messages.
        __aexit__ : Asynchronous context manager method that releases the lock and cancels the consumer tag for the queue.
    """

    def __init__(
        self, lock: "anyio.Lock", callback_queue: "RobustQueue"
    ) -> None:
        """Initialize an object of a class.

        Args:
            lock: An instance of `anyio.Lock` used for synchronization.
            callback_queue: An instance of `aio_pika.RobustQueue` used for callback queue.
        """
        self.lock = lock
        self.queue = callback_queue

    async def __aenter__(self) -> "MemoryObjectReceiveStream[IncomingMessage]":
        (
            send_response_stream,
            receive_response_stream,
        ) = anyio.create_memory_object_stream[AbstractIncomingMessage](max_buffer_size=1)
        await self.lock.acquire()

        self.consumer_tag = await self.queue.consume(
            callback=send_response_stream.send,
            no_ack=True,
        )

        return cast(
            "MemoryObjectReceiveStream[IncomingMessage]",
            receive_response_stream,
        )

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_val: Optional[BaseException] = None,
        exc_tb: Optional[TracebackType] = None,
    ) -> None:
        """Exit method for an asynchronous context manager.

        Args:
            exc_type: The type of the exception being handled, if any.
            exc_val: The exception instance being handled, if any.
            exc_tb: The traceback of the exception being handled, if any.
        """
        self.lock.release()
        await self.queue.cancel(self.consumer_tag)
