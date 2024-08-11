from typing import (
    TYPE_CHECKING,
    Dict,
    Tuple,
)

from faststream.asyncapi.utils import resolve_payloads
from faststream.broker.types import MsgType
from faststream.confluent.subscriber.usecase import (
    BatchSubscriber,
    DefaultSubscriber,
    LogicSubscriber,
)
from faststream.specification.bindings import ChannelBinding, kafka
from faststream.specification.channel import Channel
from faststream.specification.message import CorrelationId, Message
from faststream.specification.operation import Operation

if TYPE_CHECKING:
    from confluent_kafka import Message as ConfluentMsg


class AsyncAPISubscriber(LogicSubscriber[MsgType]):
    """A class to handle logic and async API operations."""

    def get_name(self) -> str:
        return f'{",".join(self.topics)}:{self.call_name}'

    def get_schema(self) -> Dict[str, Channel]:
        channels = {}

        payloads = self.get_payloads()
        for t in self.topics:
            handler_name = self.title_ or f"{t}:{self.call_name}"

            channels[handler_name] = Channel(
                description=self.description,
                subscribe=Operation(
                    message=Message(
                        title=f"{handler_name}:Message",
                        payload=resolve_payloads(payloads),
                        correlationId=CorrelationId(
                            location="$message.header#/correlation_id"
                        ),
                    ),
                ),
                bindings=ChannelBinding(
                    kafka=kafka.ChannelBinding(topic=t),
                ),
            )

        return channels


class AsyncAPIDefaultSubscriber(
    DefaultSubscriber,
    AsyncAPISubscriber["ConfluentMsg"],
):
    pass


class AsyncAPIBatchSubscriber(
    BatchSubscriber,
    AsyncAPISubscriber[Tuple["ConfluentMsg", ...]],
):
    pass
