import re
from typing import Any, Optional, Sequence, Union

from faststream.broker.core.call_wrapper import HandlerCallWrapper
from faststream.broker.test import TestBroker, call_handler
from faststream.exceptions import SetupError
from faststream.redis.asyncapi import Handler
from faststream.redis.broker import RedisBroker
from faststream.redis.message import (
    BatchListMessage,
    BatchStreamMessage,
    DefaultListMessage,
    DefaultStreamMessage,
    PubSubMessage,
    bDATA_KEY,
)
from faststream.redis.parser import RawMessage
from faststream.redis.producer import RedisFastProducer
from faststream.redis.publisher import LogicPublisher
from faststream.redis.schemas import INCORRECT_SETUP_MSG
from faststream.types import AnyDict, SendableMessage

__all__ = ("TestRedisBroker",)


class TestRedisBroker(TestBroker[RedisBroker]):
    """A class to test Redis brokers."""

    @staticmethod
    def patch_publisher(
        broker: RedisBroker,
        publisher: Any,
    ) -> None:
        publisher._producer = broker._producer

    @staticmethod
    def create_publisher_fake_subscriber(
        broker: RedisBroker,
        publisher: LogicPublisher,
    ) -> HandlerCallWrapper[Any, Any, Any]:
        @broker.subscriber(**publisher.subscriber_property)
        def f(msg: Any) -> None:
            pass

        return f

    @staticmethod
    async def _fake_connect(
        broker: RedisBroker,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        broker._producer = FakeProducer(broker)  # type: ignore[assignment]

    @classmethod
    def _fake_start(
        cls,
        broker: RedisBroker,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super()._fake_start(broker, *args, **kwargs)

        for h in broker.handlers.values():
            h.producer = FakeProducer(broker)  # type: ignore[assignment]

    @staticmethod
    def remove_publisher_fake_subscriber(
        broker: RedisBroker,
        publisher: LogicPublisher,
    ) -> None:
        broker.handlers.pop(
            hash(Handler.create(**publisher.subscriber_property)),
            None,
        )


class FakeProducer(RedisFastProducer):
    def __init__(self, broker: RedisBroker) -> None:
        self.broker = broker

    async def publish(
        self,
        message: SendableMessage,
        channel: Optional[str] = None,
        reply_to: str = "",
        headers: Optional[AnyDict] = None,
        correlation_id: Optional[str] = None,
        *,
        list: Optional[str] = None,
        stream: Optional[str] = None,
        rpc: bool = False,
        rpc_timeout: Optional[float] = 30.0,
        raise_timeout: bool = False,
        maxlen: Optional[int] = None,
    ) -> Optional[Any]:
        body = build_message(message=message, reply_to=reply_to, correlation_id=correlation_id, headers=headers,)

        any_of = channel or list or stream
        if any_of is None:
            raise SetupError(INCORRECT_SETUP_MSG)

        msg: Any = None
        for handler in self.broker.handlers.values():  # pragma: no branch
            call = False

            if channel and (ch := getattr(handler, "channel", None)) is not None:
                call = bool(
                    (not ch.pattern and ch.name == channel)
                    or (
                        ch.pattern
                        and re.match(
                            ch.name.replace(".", "\\.").replace("*", ".*"),
                            channel,
                        )
                    )
                )

                msg = PubSubMessage(
                    type="message",
                    data=body,
                    channel=channel,
                    pattern=ch.pattern,
                )

            elif list and (ls := getattr(handler, "list_sub", None)) is not None:
                if ls.batch:
                    msg = BatchListMessage(
                        type="blist",
                        channel=list,
                        data=[body],
                    )

                else:
                    msg = DefaultListMessage(
                        type="list",
                        channel=list,
                        data=body,
                    )

                call = list == ls.name

            elif stream and (st := getattr(handler, "stream_sub", None)) is not None:
                if st.batch:
                    msg = BatchStreamMessage(
                        type="bstream",
                        channel=stream,
                        data=[{bDATA_KEY: body}],
                        message_ids=[]
                    )
                else:
                    msg = DefaultStreamMessage(
                        type="stream",
                        channel=stream,
                        data={bDATA_KEY: body},
                        message_ids=[]
                    )

                call = stream == st.name

            if call:
                r = await call_handler(
                    handler=handler,
                    message=msg,
                    rpc=rpc,
                    rpc_timeout=rpc_timeout,
                    raise_timeout=raise_timeout,
                )

                if rpc:  # pragma: no branch
                    return r

        return None

    async def publish_batch(
        self,
        *msgs: SendableMessage,
        list: str,
    ) -> None:
        for handler in self.broker.handlers.values():  # pragma: no branch
            if (list_sub := getattr(handler, "list_sub", None)) and list_sub.name == list:
                await call_handler(
                    handler=handler,
                    message=BatchListMessage(
                        type="blist",
                        channel=list,
                        data=[build_message(m) for m in msgs],
                    )
                )

        return None


def build_message(
    message: Union[Sequence[SendableMessage], SendableMessage],
    *,
    reply_to: str = "",
    correlation_id: Optional[str] = None,
    headers: Optional[AnyDict] = None,
) -> bytes:
    data = RawMessage.encode(
        message=message,
        reply_to=reply_to,
        headers=headers,
        correlation_id=correlation_id,
    )
    return data
