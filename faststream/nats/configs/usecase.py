from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from faststream._internal.constants import EMPTY
from faststream._internal.endpoint.publisher import PublisherUsecaseConfig
from faststream._internal.endpoint.subscriber import SubscriberUsecaseConfig
from faststream.middlewares import AckPolicy

if TYPE_CHECKING:
    from nats.js.api import ConsumerConfig

    from faststream._internal.basic_types import (
        AnyDict,
    )
    from faststream.nats.schemas import JStream


@dataclass
class NatsSubscriberConfig(SubscriberUsecaseConfig):
    subject: str
    config: "ConsumerConfig"
    extra_options: Optional["AnyDict"]
    no_ack: bool
    ack_first: bool

    @property
    def ack_policy(self) -> AckPolicy:
        if self.ack_first is not EMPTY:
            return AckPolicy.ACK_FIRST if self.ack_first else AckPolicy.REJECT_ON_ERROR

        if self.no_ack is not EMPTY:
            return AckPolicy.DO_NOTHING if self.no_ack else EMPTY

        if self._ack_policy is EMPTY:
            return AckPolicy.REJECT_ON_ERROR
        return self._ack_policy

    @ack_policy.setter
    def ack_policy(self, policy: AckPolicy) -> None:
        self._ack_policy = policy


@dataclass
class NatsPublisherConfig(PublisherUsecaseConfig):
    subject: str
    reply_to: str
    headers: Optional[dict[str, str]]
    stream: Optional["JStream"]
    timeout: Optional[float]
