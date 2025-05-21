from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Optional,
    Union,
)

from faststream._internal.constants import EMPTY
from faststream._internal.endpoint.publisher import PublisherUsecaseConfig
from faststream._internal.endpoint.subscriber import (
    SubscriberUsecaseConfig,
)
from faststream.middlewares.acknowledgement.conf import AckPolicy

if TYPE_CHECKING:
    from aiokafka import TopicPartition
    from aiokafka.abc import ConsumerRebalanceListener

    from faststream._internal.basic_types import AnyDict


@dataclass
class KafkaPublisherConfig(PublisherUsecaseConfig):
    key: Union[bytes, str, None]
    topic: str
    partition: Optional[int]
    headers: Optional[dict[str, str]]
    reply_to: Optional[str]


@dataclass
class KafkaSubscriberConfig(SubscriberUsecaseConfig):
    topics: Sequence[str]
    group_id: Optional[str]
    connection_args: "AnyDict"
    listener: Optional["ConsumerRebalanceListener"]
    pattern: Optional[str]
    partitions: Iterable["TopicPartition"]
    no_ack: bool
    auto_commit: bool
    ack_first: bool = False

    def __post_init__(self) -> None:
        if self._ack_policy is AckPolicy.ACK_FIRST:
            self.ack_first = True
            self.connection_args["enable_auto_commit"] = True

    @property
    def ack_policy(self) -> AckPolicy:
        if self._ack_policy is EMPTY:
            return AckPolicy.ACK_FIRST

        if self.auto_commit is not EMPTY:
            return (
                AckPolicy.ACK_FIRST if self.auto_commit else AckPolicy.REJECT_ON_ERROR
            )

        if self.no_ack is not EMPTY:
            return AckPolicy.DO_NOTHING if self.no_ack else EMPTY

        if self._ack_policy is AckPolicy.ACK_FIRST:
            return AckPolicy.DO_NOTHING

        return self._ack_policy

    @ack_policy.setter
    def ack_policy(self, policy: AckPolicy) -> None:
        self._ack_policy = policy
