import warnings
from collections.abc import Iterable, Sequence
from typing import (
    TYPE_CHECKING,
    Literal,
    Optional,
    Union,
    cast,
    overload,
)

from faststream._internal.constants import EMPTY
from faststream.confluent.subscriber.specified import (
    SpecificationBatchSubscriber,
    SpecificationDefaultSubscriber,
)
from faststream.exceptions import SetupError
from faststream.middlewares import AckPolicy

if TYPE_CHECKING:
    from confluent_kafka import Message as ConfluentMsg
    from fast_depends.dependencies import Dependant

    from faststream._internal.basic_types import AnyDict
    from faststream._internal.types import BrokerMiddleware
    from faststream.confluent.schemas import TopicPartition


@overload
def create_subscriber(
    *topics: str,
    partitions: Sequence["TopicPartition"],
    polling_interval: float,
    batch: Literal[True],
    max_records: Optional[int],
    # Kafka information
    group_id: Optional[str],
    connection_data: "AnyDict",
    is_manual: bool,
    # Subscriber args
    ack_policy: "AckPolicy",
    no_ack: bool,
    no_reply: bool,
    broker_dependencies: Iterable["Dependant"],
    broker_middlewares: Iterable["BrokerMiddleware[tuple[ConfluentMsg, ...]]"],
    # Specification args
    title_: Optional[str],
    description_: Optional[str],
    include_in_schema: bool,
) -> "SpecificationBatchSubscriber": ...


@overload
def create_subscriber(
    *topics: str,
    partitions: Sequence["TopicPartition"],
    polling_interval: float,
    batch: Literal[False],
    max_records: Optional[int],
    # Kafka information
    group_id: Optional[str],
    connection_data: "AnyDict",
    is_manual: bool,
    # Subscriber args
    ack_policy: "AckPolicy",
    no_ack: bool,
    no_reply: bool,
    broker_dependencies: Iterable["Dependant"],
    broker_middlewares: Iterable["BrokerMiddleware[ConfluentMsg]"],
    # Specification args
    title_: Optional[str],
    description_: Optional[str],
    include_in_schema: bool,
) -> "SpecificationDefaultSubscriber": ...


@overload
def create_subscriber(
    *topics: str,
    partitions: Sequence["TopicPartition"],
    polling_interval: float,
    batch: bool,
    max_records: Optional[int],
    # Kafka information
    group_id: Optional[str],
    connection_data: "AnyDict",
    is_manual: bool,
    # Subscriber args
    ack_policy: "AckPolicy",
    no_ack: bool,
    no_reply: bool,
    broker_dependencies: Iterable["Dependant"],
    broker_middlewares: Union[
        Iterable["BrokerMiddleware[tuple[ConfluentMsg, ...]]"],
        Iterable["BrokerMiddleware[ConfluentMsg]"],
    ],
    # Specification args
    title_: Optional[str],
    description_: Optional[str],
    include_in_schema: bool,
) -> Union[
    "SpecificationDefaultSubscriber",
    "SpecificationBatchSubscriber",
]: ...


def create_subscriber(
    *topics: str,
    partitions: Sequence["TopicPartition"],
    polling_interval: float,
    batch: bool,
    max_records: Optional[int],
    # Kafka information
    group_id: Optional[str],
    connection_data: "AnyDict",
    is_manual: bool,
    # Subscriber args
    ack_policy: "AckPolicy",
    no_ack: bool,
    no_reply: bool,
    broker_dependencies: Iterable["Dependant"],
    broker_middlewares: Union[
        Iterable["BrokerMiddleware[tuple[ConfluentMsg, ...]]"],
        Iterable["BrokerMiddleware[ConfluentMsg]"],
    ],
    # Specification args
    title_: Optional[str],
    description_: Optional[str],
    include_in_schema: bool,
) -> Union[
    "SpecificationDefaultSubscriber",
    "SpecificationBatchSubscriber",
]:
    _validate_input_for_misconfigure(
        ack_policy=ack_policy, is_manual=is_manual, no_ack=no_ack
    )

    if ack_policy is EMPTY:
        ack_policy = AckPolicy.DO_NOTHING if no_ack else AckPolicy.REJECT_ON_ERROR

    if batch:
        return SpecificationBatchSubscriber(
            *topics,
            partitions=partitions,
            polling_interval=polling_interval,
            max_records=max_records,
            group_id=group_id,
            connection_data=connection_data,
            is_manual=is_manual,
            ack_policy=ack_policy,
            no_reply=no_reply,
            broker_dependencies=broker_dependencies,
            broker_middlewares=cast(
                Iterable["BrokerMiddleware[tuple[ConfluentMsg, ...]]"],
                broker_middlewares,
            ),
            title_=title_,
            description_=description_,
            include_in_schema=include_in_schema,
        )

    return SpecificationDefaultSubscriber(
        *topics,
        partitions=partitions,
        polling_interval=polling_interval,
        group_id=group_id,
        connection_data=connection_data,
        is_manual=is_manual,
        ack_policy=ack_policy,
        no_reply=no_reply,
        broker_dependencies=broker_dependencies,
        broker_middlewares=cast(
            Iterable["BrokerMiddleware[ConfluentMsg]"],
            broker_middlewares,
        ),
        title_=title_,
        description_=description_,
        include_in_schema=include_in_schema,
    )


def _validate_input_for_misconfigure(
    *,
    ack_policy: "AckPolicy",
    is_manual: bool,
    no_ack: bool,
) -> None:
    if no_ack is not EMPTY:
        warnings.warn(
            "`no_ack` option was deprecated in prior to `ack_policy=AckPolicy.DO_NOTHING`. Scheduled to remove in 0.7.0",
            category=DeprecationWarning,
            stacklevel=4,
        )

        if ack_policy is not EMPTY:
            msg = "You can't use deprecated `no_ack` and `ack_policy` simultaneously. Please, use `ack_policy` only."
            raise SetupError(msg)

    if ack_policy is not EMPTY and not is_manual:
        warnings.warn(
            "You can't use acknowledgement policy with `is_manual=False` subscriber",
            RuntimeWarning,
            stacklevel=4,
        )
