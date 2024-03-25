import asyncio
from abc import abstractmethod
from contextlib import suppress
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncContextManager,
    Awaitable,
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Type,
    Union,
    cast,
)

import anyio
from nats.errors import ConnectionClosedError, TimeoutError
from typing_extensions import Annotated, Doc, override

from faststream.broker.core.handler import BaseHandler
from faststream.broker.core.publisher import FakePublisher
from faststream.broker.parsers import resolve_custom_func
from faststream.broker.types import MsgType
from faststream.nats.parser import BatchParser, JsParser, NatsParser
from faststream.types import AnyDict, SendableMessage
from faststream.utils.path import compile_path

if TYPE_CHECKING:
    from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
    from fast_depends.dependencies import Depends
    from nats.aio.client import Client
    from nats.aio.msg import Msg
    from nats.aio.subscription import Subscription
    from nats.js import JetStreamContext
    from typing_extensions import Unpack

    from faststream.broker.core.handler_wrapper_mixin import (
        WrapExtraKwargs,
        WrapperProtocol,
    )
    from faststream.broker.message import StreamMessage
    from faststream.broker.types import (
        BrokerMiddleware,
        CustomDecoder,
        CustomParser,
        Filter,
        PublisherProtocol,
        SubscriberMiddleware,
    )
    from faststream.nats.producer import NatsFastProducer
    from faststream.nats.schemas import JStream, PullSub


class BaseNatsHandler(BaseHandler[MsgType]):
    """A class to represent a NATS handler."""

    subscription: Union[
        None,
        "Subscription",
        "JetStreamContext.PushSubscription",
        "JetStreamContext.PullSubscription",
    ]
    producer: Optional["PublisherProtocol"]

    def __init__(
        self,
        *,
        subject: Annotated[
            str,
            Doc("NATS subject to subscribe"),
        ],
        watcher: Annotated[
            Callable[..., AsyncContextManager[None]],
            Doc("Watcher to ack message"),
        ],
        extra_context: Annotated[
            Optional[AnyDict],
            Doc("Extra context to pass into consume scope"),
        ],
        extra_options: Annotated[
            Optional[AnyDict],
            Doc("Extra arguments for subscription creation"),
        ],
        graceful_timeout: Annotated[
            Optional[float],
            Doc(
                "Wait up to this time (if set) in graceful shutdown mode. "
                "Kills task forcefully if expired."
            ),
        ],
        middlewares: Annotated[
            Iterable["BrokerMiddleware[MsgType]"],
            Doc("Global middleware to use `on_receive`, `after_processed`"),
        ],
        queue: Annotated[
            str,
            Doc("Subscribers' NATS queue name"),
        ],
        stream: Annotated[
            Optional["JStream"],
            Doc("Subscribe to NATS Stream with `subject` filter."),
        ],
        pull_sub: Annotated[
            Optional["PullSub"],
            Doc(
                "NATS Pull consumer parameters container."
                "Should be used with `stream` only."
            ),
        ],
        # AsyncAPI information
        title_: Annotated[
            Optional[str],
            Doc("AsyncAPI subscriber title."),
        ],
        description_: Annotated[
            Optional[str],
            Doc("AsyncAPI subscriber description."),
        ],
        include_in_schema: Annotated[
            bool,
            Doc("Whether to include the handler in AsyncAPI schema."),
        ],
    ) -> None:
        """Initialize the NATS handler."""
        reg, path = compile_path(
            subject,
            replace_symbol="*",
            patch_regex=lambda x: x.replace(".>", "..+"),
        )
        self.subject = path
        self.path_regex = reg
        self.queue = queue

        self.stream = stream
        self.pull_sub = pull_sub
        self.extra_options = extra_options or {}

        super().__init__(
            middlewares=middlewares,
            graceful_timeout=graceful_timeout,
            watcher=watcher,
            extra_context=extra_context,
            # AsyncAPI
            title_=title_,
            description_=description_,
            include_in_schema=include_in_schema,
        )

        self.subscription = None
        self.producer = None
        self.tasks: List["asyncio.Task[Any]"] = []

    @override
    async def start(  # type: ignore[override]
        self,
        *,
        connection: Annotated[
            Union["Client", "JetStreamContext"],
            Doc("NATS client or JS Context object using to create subscription"),
        ],
        producer: Annotated[
            Optional["NatsFastProducer"],
            Doc("Publisher to response RPC"),
        ],
    ) -> None:
        """Create NATS subscription and start consume tasks."""
        await super().start(producer=producer)
        await self.create_subscription(connection=connection)

    async def close(self) -> None:
        """Clean up handler subscription, cancel consume task in graceful mode."""
        await super().close()

        if self.subscription is not None:
            await self.subscription.unsubscribe()
            self.subscription = None

        for task in self.tasks:
            if not task.done():
                task.cancel()
        self.tasks = []

    @abstractmethod
    async def create_subscription(
        self,
        *,
        connection: Annotated[
            Union["Client", "JetStreamContext"],
            Doc("NATS client or JS Context object using to create subscription"),
        ],
    ) -> None:
        """Create NATS subscription object to consume messages."""
        raise NotImplementedError()

    def make_response_publisher(
        self,
        message: Annotated[
            "StreamMessage[Any]",
            Doc("Message requiring reply"),
        ],
    ) -> Sequence[FakePublisher]:
        """Create FakePublisher object to use it as one of `publishers` in `self.consume` scope."""
        if not message.reply_to or self.producer is None:
            return ()

        return (
            FakePublisher(
                self.producer.publish,
                publish_kwargs={
                    "subject": message.reply_to,
                },
            ),
        )

    @staticmethod
    def get_routing_hash(
        subject: Annotated[
            str,
            Doc("NATS subject to consume messages"),
        ],
    ) -> int:
        """Get handler hash by outer data.

        Using to find handler in `broker.handlers` dictionary.
        """
        return hash(subject)

    @staticmethod
    def build_log_context(
        message: Annotated[
            Optional["StreamMessage[Any]"],
            Doc("Message which we are building context for"),
        ],
        subject: Annotated[
            str,
            Doc("NATS subject we are listening"),
        ],
        *,
        queue: Annotated[
            str,
            Doc("Using queue group name"),
        ] = "",
        stream: Annotated[
            Optional["JStream"],
            Doc("Stream object we are listening"),
        ] = None,
    ) -> Dict[str, str]:
        """Static method to build log context out of `self.consume` scope."""
        return {
            "subject": subject,
            "queue": queue,
            "stream": getattr(stream, "name", ""),
            "message_id": getattr(message, "message_id", ""),
        }

    def get_log_context(
        self,
        message: Annotated[
            Optional["StreamMessage[Any]"],
            Doc("Message which we are building context for"),
        ],
    ) -> Dict[str, str]:
        """Log context factory using in `self.consume` scope."""
        return self.build_log_context(
            message=message,
            subject=self.subject,
            queue=self.queue,
            stream=self.stream,
        )


class DefaultHandler(BaseNatsHandler["Msg"]):
    """One-message consumer class."""

    send_stream: "MemoryObjectSendStream[Msg]"
    receive_stream: "MemoryObjectReceiveStream[Msg]"

    def __init__(
        self,
        *,
        subject: Annotated[
            str,
            Doc("NATS subject to subscribe"),
        ],
        watcher: Annotated[
            Callable[..., AsyncContextManager[None]],
            Doc("Watcher to ack message"),
        ],
        extra_context: Annotated[
            Optional[AnyDict],
            Doc("Extra context to pass into consume scope"),
        ],
        queue: Annotated[
            str,
            Doc("NATS queue name"),
        ],
        stream: Annotated[
            Optional["JStream"],
            Doc("NATS Stream object"),
        ],
        pull_sub: Annotated[
            Optional["PullSub"],
            Doc("NATS Pull consumer parameters container"),
        ],
        extra_options: Annotated[
            Optional[AnyDict],
            Doc("Extra arguments for subscription creation"),
        ],
        graceful_timeout: Annotated[
            Optional[float],
            Doc(
                "Wait up to this time (if set) in graceful shutdown mode. "
                "Kills task forcefully if expired."
            ),
        ],
        max_workers: Annotated[
            int,
            Doc("Process up to this parameter messages concurrently"),
        ],
        middlewares: Annotated[
            Iterable["BrokerMiddleware[Msg]"],
            Doc("Global middleware to use `on_receive`, `after_processed`"),
        ],
        title_: Annotated[
            Optional[str],
            Doc("AsyncAPI subscriber title"),
        ],
        description_: Annotated[
            Optional[str],
            Doc("AsyncAPI subscriber description"),
        ],
        include_in_schema: Annotated[
            bool,
            Doc("Whether to include the handler in AsyncAPI schema"),
        ],
    ) -> None:
        """Default handler initializer.

        Has `max_workers`, `limiter`, `send_stream` and `receive_stream` custom attributes.
        They are related for concurrent message processing in async pool.
        """
        super().__init__(
            subject=subject,
            watcher=watcher,
            extra_context=extra_context,
            queue=queue,
            stream=stream,
            pull_sub=pull_sub,
            extra_options=extra_options,
            graceful_timeout=graceful_timeout,
            middlewares=middlewares,
            description_=description_,
            title_=title_,
            include_in_schema=include_in_schema,
        )

        self.max_workers = max_workers

        self.send_stream, self.receive_stream = anyio.create_memory_object_stream(
            max_buffer_size=max_workers
        )
        self.limiter = anyio.Semaphore(max_workers)

    @override
    def add_call(  # type: ignore[override]
        self,
        *,
        filter: Annotated[
            "Filter[StreamMessage[Msg]]",
            Doc("Filter function to decide about message processing"),
        ],
        parser: Annotated[
            Optional["CustomParser[Msg]"],
            Doc("Parser to map original **nats-py** Msg to FastStream one"),
        ],
        decoder: Annotated[
            Optional["CustomDecoder[StreamMessage[Msg]]"],
            Doc("Function to decode FastStream msg bytes body to python objects"),
        ],
        middlewares: Annotated[
            Iterable["SubscriberMiddleware"],
            Doc("`self.consume` scope middlewares"),
        ],
        dependencies: Annotated[
            Sequence["Depends"],
            Doc("Top-level dependencies passing to FastDepends"),
        ],
        **wrapper_kwargs: "Unpack[WrapExtraKwargs]",
    ) -> "WrapperProtocol[Msg]":
        """Decorator to register user function as handler call."""
        parser_: Union[Type[NatsParser], Type[JsParser]] = NatsParser if self.stream is None else JsParser
        return super().add_call(
            parser_=resolve_custom_func(parser, parser_.parse_message),
            decoder_=resolve_custom_func(decoder, parser_.decode_message),
            filter_=filter,
            middlewares_=middlewares,
            dependencies_=dependencies,
            **wrapper_kwargs,
        )

    async def create_subscription(
        self,
        *,
        connection: Annotated[
            Union["Client", "JetStreamContext"],
            Doc("NATS client or JS Context object using to create subscription"),
        ],
    ) -> None:
        """Create NATS subscription and start consume task."""
        cb: Callable[["Msg"], Awaitable[Any]]
        if self.max_workers > 1:
            self.tasks.append(asyncio.create_task(self._serve_consume_queue()))
            cb = self.__put_msg
        else:
            cb = self.consume

        if self.pull_sub is not None:
            connection = cast("JetStreamContext", connection)

            if self.stream is None:
                raise ValueError("Pull subscriber can be used only with a stream")

            self.subscription = await connection.pull_subscribe(
                subject=self.subject,
                **self.extra_options,
            )
            self.tasks.append(asyncio.create_task(self._consume_pull(cb=cb)))

        else:
            self.subscription = await connection.subscribe(
                subject=self.subject,
                queue=self.queue,
                cb=cb,  # type: ignore[arg-type]
                **self.extra_options,
            )

    async def _serve_consume_queue(
        self,
    ) -> None:
        """Endless task consuming messages from in-memory queue.

        Suitable to batch messages by amount, timestamps, etc and call `consume` for this batches.
        """
        async with anyio.create_task_group() as tg:
            async for msg in self.receive_stream:
                tg.start_soon(self.__consume_msg, msg)

    async def _consume_pull(
        self,
        cb: Callable[["Msg"], Awaitable[SendableMessage]],
    ) -> None:
        """Endless task consuming messages using NATS Pull subscriber."""
        assert self.pull_sub  # nosec B101

        sub = cast("JetStreamContext.PullSubscription", self.subscription)

        while self.running:  # pragma: no branch
            messages = []
            with suppress(TimeoutError, ConnectionClosedError):
                messages = await sub.fetch(
                    batch=self.pull_sub.batch_size,
                    timeout=self.pull_sub.timeout,
                )

            if messages:
                async with anyio.create_task_group() as tg:
                    for msg in messages:
                        tg.start_soon(cb, msg)

    async def __consume_msg(
        self,
        msg: "Msg",
    ) -> None:
        """Proxy method to call `self.consume` with semaphore block."""
        async with self.limiter:
            await self.consume(msg)

    async def __put_msg(self, msg: "Msg") -> None:
        """Proxy method to put msg into in-memory queue with semaphore block."""
        async with self.limiter:
            await self.send_stream.send(msg)


class BatchHandler(BaseNatsHandler[List["Msg"]]):
    """Batch-message consumer class."""

    pull_sub: "PullSub"
    stream: "JStream"

    @override
    def add_call(  # type: ignore[override]
        self,
        *,
        filter: "Filter[StreamMessage[List[Msg]]]",
        parser: Optional["CustomParser[List[Msg]]"],
        decoder: Optional["CustomDecoder[StreamMessage[List[Msg]]]"],
        middlewares: Iterable["SubscriberMiddleware"],
        dependencies: Sequence["Depends"],
        **wrap_kwargs: Any,
    ) -> "WrapperProtocol[List[Msg]]":
        return super().add_call(
            parser_=resolve_custom_func(parser, BatchParser.parse_batch),
            decoder_=resolve_custom_func(decoder, BatchParser.decode_batch),
            filter_=filter,
            middlewares_=middlewares,
            dependencies_=dependencies,
            **wrap_kwargs,
        )

    @override
    async def create_subscription(  # type: ignore[override]
        self,
        *,
        connection: Annotated[
            "JetStreamContext",
            Doc("JS Context object using to create subscription"),
        ],
    ) -> None:
        """Create NATS subscription and start consume task."""
        self.subscription = await connection.pull_subscribe(
            subject=self.subject,
            **self.extra_options,
        )
        self.tasks.append(asyncio.create_task(self._consume_pull()))

    async def _consume_pull(self) -> None:
        """Endless task consuming messages using NATS Pull subscriber."""
        assert self.subscription, "You should call `create_subscription` at first."  # nosec B101

        sub = cast("JetStreamContext.PullSubscription", self.subscription)

        while self.running:  # pragma: no branch
            with suppress(TimeoutError, ConnectionClosedError):
                messages = await sub.fetch(
                    batch=self.pull_sub.batch_size,
                    timeout=self.pull_sub.timeout,
                )

                if messages:
                    await self.consume(messages)
