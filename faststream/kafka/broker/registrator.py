from functools import partial
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Literal,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
)

from aiokafka import AIOKafkaConsumer, ConsumerRecord
from aiokafka.coordinator.assignors.abstract import AbstractPartitionAssignor
from aiokafka.coordinator.assignors.roundrobin import RoundRobinPartitionAssignor
from fast_depends.dependencies import Depends
from typing_extensions import Annotated, Doc, deprecated, override

from faststream.broker.core.abc import ABCBroker
from faststream.broker.message import StreamMessage
from faststream.broker.types import (
    CustomDecoder,
    CustomParser,
    Filter,
    PublisherMiddleware,
    SubscriberMiddleware,
)
from faststream.broker.utils import default_filter
from faststream.exceptions import SetupError
from faststream.kafka.publisher.asyncapi import AsyncAPIPublisher
from faststream.kafka.subscriber.asyncapi import AsyncAPISubscriber


class KafkaRegistrator(ABCBroker[Union[
    ConsumerRecord,
    Tuple[ConsumerRecord, ...],
]]):
    """Includable to KafkaBroker router."""

    _subscribers: Dict[int, AsyncAPISubscriber]
    _publishers: Dict[int, AsyncAPIPublisher]

    @override
    def subscriber(  # type: ignore[override]
        self,
        *topics: str,
        group_id: Optional[str] = None,
        key_deserializer: Optional[Callable[[bytes], Any]] = None,
        value_deserializer: Optional[Callable[[bytes], Any]] = None,
        fetch_max_wait_ms: int = 500,
        fetch_max_bytes: int = 52428800,
        fetch_min_bytes: int = 1,
        max_partition_fetch_bytes: int = 1 * 1024 * 1024,
        auto_offset_reset: Literal[
            "latest",
            "earliest",
            "none"
        ] = "latest",
        auto_commit: bool = True,
        auto_commit_interval_ms: int = 5 * 1000,
        check_crcs: bool = True,
        partition_assignment_strategy: Sequence[AbstractPartitionAssignor] = (
            RoundRobinPartitionAssignor,
        ),
        max_poll_interval_ms: int = 5 * 60 * 1000,
        rebalance_timeout_ms: Optional[int] = None,
        session_timeout_ms: int = 10 * 1000,
        heartbeat_interval_ms: int = 3 * 1000,
        consumer_timeout_ms: int = 200,
        max_poll_records: Optional[int] = None,
        exclude_internal_topics: bool = True,
        isolation_level: Literal[
            "read_uncommitted",
            "read_committed"
        ] = "read_uncommitted",
        batch: bool = False,
        max_records: Optional[int] = None,
        batch_timeout_ms: int = 200,
        # broker args
        dependencies: Annotated[
            Iterable[Depends],
            Doc("Dependencies list (`[Depends(),]`) to apply to the subscriber."),
        ] = (),
        parser: Annotated[
            Optional[
                Union[
                    CustomParser[ConsumerRecord],
                    CustomParser[Tuple[ConsumerRecord, ...]],
                ]
            ],
            Doc("Parser to map original **ConsumerRecord** object to FastStream one."),
        ] = None,
        decoder: Annotated[
            Optional[
                Union[
                    CustomDecoder[StreamMessage[ConsumerRecord]],
                    CustomDecoder[StreamMessage[Tuple[ConsumerRecord, ...]]],
                ]
            ],
            Doc("Function to decode FastStream msg bytes body to python objects."),
        ] = None,
        middlewares: Annotated[
            Iterable[SubscriberMiddleware],
            Doc("Subscriber middlewares to wrap incoming message processing."),
        ] = (),
        filter: Annotated[
            Union[
                Filter[StreamMessage[ConsumerRecord]],
                Filter[StreamMessage[Tuple[ConsumerRecord, ...]]],
            ],
            Doc(
                "Overload subscriber to consume various messages from the same source."
            ),
            deprecated(
                "Deprecated in **FastStream 0.5.0**. "
                "Please, create `subscriber` object and use it explicitly instead. "
                "Argument will be removed in **FastStream 0.6.0**."
            ),
        ] = default_filter,
        retry: Annotated[
            bool,
            Doc("Whether to `nack` message at processing exception."),
        ] = False,
        no_ack: Annotated[
            bool,
            Doc("Whether to disable **FastStream** autoacknowledgement logic or not."),
        ] = False,
        # AsyncAPI args
        title: Annotated[
            Optional[str],
            Doc("AsyncAPI subscriber object title."),
        ] = None,
        description: Annotated[
            Optional[str],
            Doc(
                "AsyncAPI subscriber object description. "
                "Uses decorated docstring as default."
            ),
        ] = None,
        include_in_schema: Annotated[
            bool,
            Doc("Whetever to include operation in AsyncAPI schema or not."),
        ] = True,
    ) -> AsyncAPISubscriber:
        if not auto_commit and not group_id:
            raise SetupError(
                "You should install `group_id` with manual commit mode")

        builder = partial(
            AIOKafkaConsumer,
            key_deserializer=key_deserializer,
            value_deserializer=value_deserializer,
            fetch_max_wait_ms=fetch_max_wait_ms,
            fetch_max_bytes=fetch_max_bytes,
            fetch_min_bytes=fetch_min_bytes,
            max_partition_fetch_bytes=max_partition_fetch_bytes,
            auto_offset_reset=auto_offset_reset,
            enable_auto_commit=auto_commit,
            auto_commit_interval_ms=auto_commit_interval_ms,
            check_crcs=check_crcs,
            partition_assignment_strategy=partition_assignment_strategy,
            max_poll_interval_ms=max_poll_interval_ms,
            rebalance_timeout_ms=rebalance_timeout_ms,
            session_timeout_ms=session_timeout_ms,
            heartbeat_interval_ms=heartbeat_interval_ms,
            consumer_timeout_ms=consumer_timeout_ms,
            max_poll_records=max_poll_records,
            exclude_internal_topics=exclude_internal_topics,
            isolation_level=isolation_level,
        )

        subcriber = cast(
            AsyncAPISubscriber,
            super().subscriber(
                AsyncAPISubscriber.create(
                    *topics,
                    batch=batch,
                    batch_timeout_ms=batch_timeout_ms,
                    max_records=max_records,
                    group_id=group_id,
                    builder=builder,
                    is_manual=not auto_commit,
                    # subscriber args
                    no_ack=no_ack,
                    retry=retry,
                    broker_middlewares=self._middlewares,
                    broker_dependencies=self._dependencies,
                    # AsyncAPI
                    title_=title,
                    description_=description,
                    include_in_schema=self._solve_include_in_schema(
                        include_in_schema),
                )
            ),
        )

        return subcriber.add_call(
            filter_=filter,
            parser_=parser or self._parser,
            decoder_=decoder or self._decoder,
            dependencies_=dependencies,
            middlewares_=middlewares,
        )

    @override
    def publisher(  # type: ignore[override]
        self,
        topic: str,
        *,
        key: Optional[bytes] = None,
        partition: Optional[int] = None,
        timestamp_ms: Optional[int] = None,
        batch: bool = False,
        headers: Annotated[
            Optional[Dict[str, str]],
            Doc(
                "Message headers to store metainformation. "
                "**content-type** and **correlation_id** will be setted automatically by framework anyway. "
                "Can be overrided by `publish.headers` if specified."
            ),
        ] = None,
        reply_to: Annotated[
            str,
            Doc("Topic name to send response."),
        ] = "",
        # basic args
        middlewares: Annotated[
            Iterable[PublisherMiddleware],
            Doc("Publisher middlewares to wrap outgoing messages."),
        ] = (),
        # AsyncAPI args
        title: Annotated[
            Optional[str],
            Doc("AsyncAPI publisher object title."),
        ] = None,
        description: Annotated[
            Optional[str],
            Doc("AsyncAPI publisher object description."),
        ] = None,
        schema: Annotated[
            Optional[Any],
            Doc(
                "AsyncAPI publishing message type. "
                "Should be any python-native object annotation or `pydantic.BaseModel`."
            ),
        ] = None,
        include_in_schema: Annotated[
            bool,
            Doc("Whetever to include operation in AsyncAPI schema or not."),
        ] = True,
    ) -> AsyncAPIPublisher:
        """Creates long-living and AsyncAPI-documented publisher object.

        You can use it as a handler decorator (handler should be decorated by `@broker.subscriber(...)` too) - `@broker.publisher(...)`.
        In such case publisher will publish your handler return value.

        Or you can create a publisher object to call it lately - `broker.publisher(...).publish(...)`.
        """
        return cast(
            AsyncAPIPublisher,
            super().publisher(
                AsyncAPIPublisher.create(
                    # batch flag
                    batch=batch,
                    # default args
                    key=key,
                    # both args
                    topic=topic,
                    partition=partition,
                    timestamp_ms=timestamp_ms,
                    headers=headers,
                    reply_to=reply_to,
                    # publisher-specific
                    broker_middlewares=self._middlewares,
                    middlewares=middlewares,
                    # AsyncAPI
                    title_=title,
                    description_=description,
                    schema_=schema,
                    include_in_schema=self._solve_include_in_schema(
                        include_in_schema),
                ),
            ),
        )
