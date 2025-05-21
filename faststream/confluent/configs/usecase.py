from collections.abc import Sequence
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Optional,
    Union,
)

from faststream._internal.constants import EMPTY
from faststream._internal.endpoint.publisher import PublisherUsecaseConfig
from faststream._internal.endpoint.subscriber import SubscriberUsecaseConfig
from faststream.middlewares import AckPolicy

if TYPE_CHECKING:
    from faststream._internal.basic_types import AnyDict
    from faststream.confluent.schemas import TopicPartition


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
    partitions: Sequence["TopicPartition"]
    polling_interval: float
    group_id: Optional[str]
    connection_data: "AnyDict"
    auto_commit: bool
    no_ack: bool

    def __post_init__(self) -> None:
        if self._ack_policy is AckPolicy.ACK_FIRST:
            self.connection_data["enable_auto_commit"] = True

    @property
    def ack_policy(self) -> AckPolicy:
        if self.auto_commit is not EMPTY:
            return (
                AckPolicy.ACK_FIRST if self.auto_commit else AckPolicy.REJECT_ON_ERROR
            )

        if self.no_ack is not EMPTY:
            return AckPolicy.DO_NOTHING if self.no_ack else EMPTY

        if self._ack_policy is EMPTY:
            return AckPolicy.ACK_FIRST

        if self._ack_policy is AckPolicy.ACK_FIRST:
            return AckPolicy.DO_NOTHING

        return self._ack_policy

    @ack_policy.setter
    def ack_policy(self, policy: AckPolicy) -> None:
        self._ack_policy = policy
