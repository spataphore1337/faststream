from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from faststream._internal.constants import EMPTY
from faststream._internal.endpoint.publisher import PublisherUsecaseConfig
from faststream._internal.endpoint.subscriber import SubscriberUsecaseConfig
from faststream.middlewares import AckPolicy

if TYPE_CHECKING:
    from faststream._internal.basic_types import AnyDict
    from faststream.rabbit.publisher.usecase import PublishKwargs
    from faststream.rabbit.schemas import (
        Channel,
        RabbitExchange,
        RabbitQueue,
    )
    from faststream.rabbit.schemas.exchange import RabbitExchange
    from faststream.rabbit.schemas.queue import RabbitQueue


@dataclass(kw_only=True)
class RabbitSubscriberConfig(SubscriberUsecaseConfig):
    queue: "RabbitQueue"
    exchange: "RabbitExchange"

    consume_args: Optional["AnyDict"]
    channel: Optional["Channel"]

    _no_ack: bool = field(repr=False)

    @property
    def no_ack(self) -> bool:
        if self._no_ack is not EMPTY:
            return self._no_ack

        return self._ack_policy is AckPolicy.ACK_FIRST

    @property
    def ack_policy(self) -> AckPolicy:
        if self._ack_policy is EMPTY:
            return AckPolicy.REJECT_ON_ERROR

        if self._ack_policy is AckPolicy.ACK_FIRST:
            # This case suppressed in prior to `no_ack` protocol option
            return AckPolicy.DO_NOTHING

        return self._ack_policy


@dataclass(kw_only=True)
class RabbitPublisherConfig(PublisherUsecaseConfig):
    queue: "RabbitQueue"
    exchange: "RabbitExchange"

    routing_key: str
    message_kwargs: "PublishKwargs"
