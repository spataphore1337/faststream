from abc import abstractmethod
from contextlib import AsyncExitStack
from copy import deepcopy
from itertools import chain
from typing import TYPE_CHECKING, Any, Iterable, Optional

from typing_extensions import Annotated, Doc, override

from faststream.broker.publisher.usecase import PublisherUsecase
from faststream.exceptions import NOT_CONNECTED_YET
from faststream.redis.message import BaseMessage
from faststream.redis.schemas import ListSub, PubSub, StreamSub

if TYPE_CHECKING:
    from faststream.broker.types import BrokerMiddleware, PublisherMiddleware
    from faststream.redis.publisher.producer import RedisFastProducer
    from faststream.types import AnyDict, SendableMessage


class LogicPublisher(PublisherUsecase[BaseMessage]):
    """A class to represent a Redis publisher."""
    _producer: Optional["RedisFastProducer"]

    def __init__(
        self,
        *,
        reply_to: str,
        headers: Optional["AnyDict"],
        # Publisher args
        broker_middlewares: Iterable["BrokerMiddleware[BaseMessage]"],
        middlewares: Iterable["PublisherMiddleware"],
        # AsyncAPI args
        schema_: Optional[Any],
        title_: Optional[str],
        description_: Optional[str],
        include_in_schema: bool,
    ) -> None:
        super().__init__(
            broker_middlewares=broker_middlewares,
            middlewares=middlewares,
            # AsyncAPI args
            schema_=schema_,
            title_=title_,
            description_=description_,
            include_in_schema=include_in_schema,
        )

        self.reply_to = reply_to
        self.headers = headers

        self._producer = None

    @property
    @abstractmethod
    def subscriber_property(self) -> "AnyDict":
        raise NotImplementedError()


class ChannelPublisher(LogicPublisher):
    def __init__(
        self,
        *,
        channel: PubSub,
        reply_to: str,
        headers: Optional["AnyDict"],
        # Regular publisher options
        broker_middlewares: Iterable["BrokerMiddleware[BaseMessage]"],
        middlewares: Iterable["PublisherMiddleware"],
        # AsyncAPI options
        schema_: Optional[Any],
        title_: Optional[str],
        description_: Optional[str],
        include_in_schema: bool,
    ) -> None:
        super().__init__(
            reply_to=reply_to,
            headers=headers,
            broker_middlewares=broker_middlewares,
            middlewares=middlewares,
            schema_=schema_,
            title_=title_,
            description_=description_,
            include_in_schema=include_in_schema,
        )

        self.channel = channel

    def __hash__(self) -> int:
        return hash(f"publisher:pubsub:{self.channel.name}")

    @property
    def subscriber_property(self) -> "AnyDict":
        return {
            "channel": self.channel,
            "list": None,
            "stream": None,
        }

    def add_prefix(self, prefix: str) -> None:
        channel = deepcopy(self.channel)
        channel.name = "".join((prefix, channel.name))
        self.channel = channel

    @override
    async def publish(  # type: ignore[override]
        self,
        message: Annotated[
            "SendableMessage",
            Doc("Message body to send."),
        ] = None,
        channel: Annotated[
            Optional[str],
            Doc("Redis PubSub object name to send message."),
        ] = None,
        reply_to: Annotated[
            str,
            Doc("Reply message destination PubSub object name."),
        ] = "",
        headers: Annotated[
            Optional["AnyDict"],
            Doc("Message headers to store metainformation."),
        ] = None,
        correlation_id: Annotated[
            Optional[str],
            Doc(
                "Manual message **correlation_id** setter. "
                "**correlation_id** is a useful option to trace messages."
            ),
        ] = None,
        *,
        # rpc args
        rpc: Annotated[
            bool,
            Doc("Whether to wait for reply in blocking mode."),
        ] = False,
        rpc_timeout: Annotated[
            Optional[float],
            Doc("RPC reply waiting time."),
        ] = 30.0,
        raise_timeout: Annotated[
            bool,
            Doc(
                "Whetever to raise `TimeoutError` or return `None` at **rpc_timeout**. "
                "RPC request returns `None` at timeout by default."
            ),
        ] = False,
        # publisher specific
        extra_middlewares: Annotated[
            Iterable["PublisherMiddleware"],
            Doc("Extra middlewares to wrap publishing process."),
        ] = (),
    ) -> Optional[Any]:
        assert self._producer, NOT_CONNECTED_YET  # nosec B101

        channel_sub = PubSub.validate(channel or self.channel)
        reply_to = reply_to or self.reply_to
        headers = headers or self.headers

        async with AsyncExitStack() as stack:
            for m in chain(
                extra_middlewares
                or (m(None).publish_scope for m in self._broker_middlewares),
                self._middlewares,
            ):
                message = await stack.enter_async_context(
                    m(
                        message,
                        channel=channel_sub.name,
                        # basic args
                        reply_to=reply_to,
                        headers=headers,
                        correlation_id=correlation_id,
                        # RPC args
                        rpc=rpc,
                        rpc_timeout=rpc_timeout,
                        raise_timeout=raise_timeout,
                    )
                )

            return await self._producer.publish(
                message=message,
                channel=channel_sub.name,
                # basic args
                reply_to=reply_to,
                headers=headers,
                correlation_id=correlation_id,
                # RPC args
                rpc=rpc,
                rpc_timeout=rpc_timeout,
                raise_timeout=raise_timeout,
            )

        return None


class ListPublisher(LogicPublisher):
    def __init__(
        self,
        *,
        list: ListSub,
        reply_to: str,
        headers: Optional["AnyDict"],
        # Regular publisher options
        broker_middlewares: Iterable["BrokerMiddleware[BaseMessage]"],
        middlewares: Iterable["PublisherMiddleware"],
        # AsyncAPI options
        schema_: Optional[Any],
        title_: Optional[str],
        description_: Optional[str],
        include_in_schema: bool,
    ) -> None:
        super().__init__(
            reply_to=reply_to,
            headers=headers,
            broker_middlewares=broker_middlewares,
            middlewares=middlewares,
            schema_=schema_,
            title_=title_,
            description_=description_,
            include_in_schema=include_in_schema,
        )

        self.list = list

    def __hash__(self) -> int:
        return hash(f"publisher:list:{self.list.name}")

    @property
    def subscriber_property(self) -> "AnyDict":
        return {
            "channel": None,
            "list": self.list,
            "stream": None,
        }

    def add_prefix(self, prefix: str) -> None:
        list_sub = deepcopy(self.list)
        list_sub.name = "".join((prefix, list_sub.name))
        self.list = list_sub

    @override
    async def publish(  # type: ignore[override]
        self,
        message: Annotated[
            "SendableMessage",
            Doc("Message body to send."),
        ] = None,
        list: Annotated[
            Optional[str],
            Doc("Redis List object name to send message."),
        ] = None,
        reply_to: Annotated[
            str,
            Doc("Reply message destination PubSub object name."),
        ] = "",
        headers: Annotated[
            Optional["AnyDict"],
            Doc("Message headers to store metainformation."),
        ] = None,
        correlation_id: Annotated[
            Optional[str],
            Doc(
                "Manual message **correlation_id** setter. "
                "**correlation_id** is a useful option to trace messages."
            ),
        ] = None,
        *,
        # rpc args
        rpc: Annotated[
            bool,
            Doc("Whether to wait for reply in blocking mode."),
        ] = False,
        rpc_timeout: Annotated[
            Optional[float],
            Doc("RPC reply waiting time."),
        ] = 30.0,
        raise_timeout: Annotated[
            bool,
            Doc(
                "Whetever to raise `TimeoutError` or return `None` at **rpc_timeout**. "
                "RPC request returns `None` at timeout by default."
            ),
        ] = False,
        # publisher specific
        extra_middlewares: Annotated[
            Iterable["PublisherMiddleware"],
            Doc("Extra middlewares to wrap publishing process."),
        ] = (),
    ) -> Any:
        assert self._producer, NOT_CONNECTED_YET  # nosec B101

        list_sub = ListSub.validate(list or self.list)
        reply_to = reply_to or self.reply_to
        headers = headers or self.headers

        async with AsyncExitStack() as stack:
            for m in chain(
                extra_middlewares
                or (m(None).publish_scope for m in self._broker_middlewares),
                self._middlewares,
            ):
                message = await stack.enter_async_context(
                    m(
                        message,
                        list=list_sub.name,
                        # basic args
                        reply_to=reply_to,
                        headers=headers,
                        correlation_id=correlation_id,
                        # RPC args
                        rpc=rpc,
                        rpc_timeout=rpc_timeout,
                        raise_timeout=raise_timeout,
                    )
                )

            return await self._producer.publish(
                message=message,
                list=list_sub.name,
                # basic args
                reply_to=reply_to,
                headers=headers,
                correlation_id=correlation_id,
                # RPC args
                rpc=rpc,
                rpc_timeout=rpc_timeout,
                raise_timeout=raise_timeout,
            )

        return None


class ListBatchPublisher(ListPublisher):
    @override
    async def publish(  # type: ignore[override]
        self,
        message: Annotated[
            Iterable["SendableMessage"],
            Doc("Message body to send."),
        ] = (),
        list: Annotated[
            Optional[str],
            Doc("Redis List object name to send message."),
        ] = None,
        *,
        correlation_id: Annotated[
            Optional[str],
            Doc(
                "Has no real effect. Option to be compatible with original protocol."
            ),
        ] = None,
        # publisher specific
        extra_middlewares: Annotated[
            Iterable["PublisherMiddleware"],
            Doc("Extra middlewares to wrap publishing process."),
        ] = (),
    ) -> None:
        assert self._producer, NOT_CONNECTED_YET  # nosec B101

        list_sub = ListSub.validate(list or self.list)

        async with AsyncExitStack() as stack:
            wrapped_messages = [
                await stack.enter_async_context(
                    middleware(msg, list=list_sub)
                )
                for msg in message
                for middleware in chain(
                    extra_middlewares
                    or (m(None).publish_scope for m in self._broker_middlewares),
                    self._middlewares,
                )
            ] or message

            return await self._producer.publish_batch(
                *wrapped_messages,
                list=list_sub.name,
            )

        return None


class StreamPublisher(LogicPublisher):
    def __init__(
        self,
        *,
        stream: StreamSub,
        reply_to: str,
        headers: Optional["AnyDict"],
        # Regular publisher options
        broker_middlewares: Iterable["BrokerMiddleware[BaseMessage]"],
        middlewares: Iterable["PublisherMiddleware"],
        # AsyncAPI options
        schema_: Optional[Any],
        title_: Optional[str],
        description_: Optional[str],
        include_in_schema: bool,
    ) -> None:
        super().__init__(
            reply_to=reply_to,
            headers=headers,
            broker_middlewares=broker_middlewares,
            middlewares=middlewares,
            schema_=schema_,
            title_=title_,
            description_=description_,
            include_in_schema=include_in_schema,
        )

        self.stream = stream

    def __hash__(self) -> int:
        return hash(f"publisher:stream:{self.stream.name}")

    @property
    def subscriber_property(self) -> "AnyDict":
        return {
            "channel": None,
            "list": None,
            "stream": self.stream
        }

    def add_prefix(self, prefix: str) -> None:
        stream_sub = deepcopy(self.stream)
        stream_sub.name = "".join((prefix, stream_sub.name))
        self.stream = stream_sub

    @override
    async def publish(  # type: ignore[override]
        self,
        message: Annotated[
            "SendableMessage",
            Doc("Message body to send."),
        ] = None,
        stream: Annotated[
            Optional[str],
            Doc("Redis Stream object name to send message."),
        ] = None,
        reply_to: Annotated[
            str,
            Doc("Reply message destination PubSub object name."),
        ] = "",
        headers: Annotated[
            Optional["AnyDict"],
            Doc("Message headers to store metainformation."),
        ] = None,
        correlation_id: Annotated[
            Optional[str],
            Doc(
                "Manual message **correlation_id** setter. "
                "**correlation_id** is a useful option to trace messages."
            ),
        ] = None,
        *,
        maxlen: Annotated[
            Optional[int],
            Doc(
                "Redis Stream maxlen publish option. "
                "Remove eldest message if maxlen exceeded."
            ),
        ] = None,
        # rpc args
        rpc: Annotated[
            bool,
            Doc("Whether to wait for reply in blocking mode."),
        ] = False,
        rpc_timeout: Annotated[
            Optional[float],
            Doc("RPC reply waiting time."),
        ] = 30.0,
        raise_timeout: Annotated[
            bool,
            Doc(
                "Whetever to raise `TimeoutError` or return `None` at **rpc_timeout**. "
                "RPC request returns `None` at timeout by default."
            ),
        ] = False,
        # publisher specific
        extra_middlewares: Annotated[
            Iterable["PublisherMiddleware"],
            Doc("Extra middlewares to wrap publishing process."),
        ] = (),
    ) -> Optional[Any]:
        assert self._producer, NOT_CONNECTED_YET  # nosec B101

        stream_sub = StreamSub.validate(stream or self.stream)
        maxlen = maxlen or stream_sub.maxlen
        reply_to = reply_to or self.reply_to
        headers = headers or self.headers

        async with AsyncExitStack() as stack:
            for m in chain(
                extra_middlewares
                or (m(None).publish_scope for m in self._broker_middlewares),
                self._middlewares,
            ):
                message = await stack.enter_async_context(
                    m(
                        message,
                        stream=stream_sub.name,
                        maxlen=maxlen,
                        # basic args
                        reply_to=reply_to,
                        headers=headers,
                        correlation_id=correlation_id,
                        # RPC args
                        rpc=rpc,
                        rpc_timeout=rpc_timeout,
                        raise_timeout=raise_timeout,
                    )
                )

            return await self._producer.publish(
                message=message,
                stream=stream_sub.name,
                maxlen=maxlen,
                # basic args
                reply_to=reply_to,
                headers=headers,
                correlation_id=correlation_id,
                # RPC args
                rpc=rpc,
                rpc_timeout=rpc_timeout,
                raise_timeout=raise_timeout,
            )

        return None
