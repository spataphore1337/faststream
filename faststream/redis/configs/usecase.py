from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from faststream._internal.constants import EMPTY
from faststream._internal.endpoint.publisher import PublisherUsecaseConfig
from faststream._internal.endpoint.subscriber import SubscriberUsecaseConfig
from faststream.middlewares.acknowledgement.conf import AckPolicy

if TYPE_CHECKING:
    from faststream._internal.basic_types import AnyDict


@dataclass
class RedisPublisherConfig(PublisherUsecaseConfig):
    reply_to: str
    headers: Optional["AnyDict"]


@dataclass
class RedisSubscriberConfig(SubscriberUsecaseConfig):
    no_ack: bool

    @property
    def ack_policy(self) -> AckPolicy:
        if self._ack_policy is EMPTY:
            return AckPolicy.DO_NOTHING if self.no_ack else AckPolicy.REJECT_ON_ERROR
        return self._ack_policy

    @ack_policy.setter
    def ack_policy(self, policy: AckPolicy) -> None:
        self._ack_policy = policy
