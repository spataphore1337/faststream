from typing import TYPE_CHECKING, Any, Dict, Iterable, Optional, Sequence

from typing_extensions import override

from faststream.broker.core.publisher import BasePublisher
from faststream.confluent.producer import AsyncConfluentFastProducer
from faststream.exceptions import NOT_CONNECTED_YET, SetupError
from faststream.types import SendableMessage

if TYPE_CHECKING:
    from faststream.broker.types import PublisherMiddleware


class LogicPublisher(BasePublisher["Message"]):
    """A class to publish messages to a Kafka topic.

    Attributes:
        _producer : An optional instance of AsyncConfluentFastProducer
        batch : A boolean indicating whether to send messages in batch
        client_id : A string representing the client ID

    Methods:
        publish : Publishes messages to the Kafka topic

    Raises:
        AssertionError: If `_producer` is not set up or if multiple messages are sent without the `batch` flag

    """

    _producer: Optional[AsyncConfluentFastProducer]

    def __init__(
        self,
        *,
        topic: str,
        partition: Optional[int],
        timestamp_ms: Optional[int],
        headers: Optional[Dict[str, str]],
        reply_to: Optional[str],
        client_id: str,
        # Regular publisher options
        middlewares: Iterable["PublisherMiddleware"],
        # AsyncAPI options
        schema_: Optional[Any],
        title_: Optional[str],
        description_: Optional[str],
        include_in_schema: bool,
    ) -> None:
        super().__init__(
            middlewares=middlewares,
            schema_=schema_,
            title_=title_,
            description_=description_,
            include_in_schema=include_in_schema,
        )

        self.topic = topic
        self.partition = partition
        self.timestamp_ms = timestamp_ms
        self.client_id = client_id
        self.reply_to = reply_to
        self.headers = headers

        self._producer = None

    def __hash__(self) -> int:
        return hash(self.topic)

    @override
    async def publish(  # type: ignore[override]
        self,
        *messages: SendableMessage,
        message: SendableMessage = "",
        key: Optional[bytes] = None,
        partition: Optional[int] = None,
        timestamp_ms: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
        correlation_id: Optional[str] = None,
        # Regular publisher options
        middlewares: Iterable["PublisherMiddleware"],
        # AsyncAPI options
        schema_: Optional[Any],
        title_: Optional[str],
        description_: Optional[str],
        include_in_schema: bool,
    ) -> None:
        """Publish messages to a topic.

        Args:
            *messages: Variable length argument list of SendableMessage objects.
            message: A SendableMessage object. Default is an empty string.
            key: Optional bytes object representing the message key.
            partition: Optional integer representing the partition to publish the message to.
            timestamp_ms: Optional integer representing the timestamp of the message in milliseconds.
            headers: Optional dictionary of header key-value pairs.
            correlation_id: Optional string representing the correlation ID of the message.

        Returns:
            None

        Raises:
            AssertionError: If `_producer` is not set up.
            AssertionError: If `batch` flag is not set and there are multiple messages.
            ValueError: If `message` is not a sequence when `messages` is empty.

        """
        assert self._producer, NOT_CONNECTED_YET  # nosec B101
        assert (  # nosec B101
            self.batch or len(messages) < 2
        ), "You can't send multiple messages without `batch` flag"
        assert self.topic, "You have to specify outgoing topic"  # nosec B101

        if not self.batch:
            return await self._producer.publish(
                message=next(iter(messages), message),
                topic=self.topic,
                key=key,
                partition=partition or self.partition,
                timestamp_ms=timestamp_ms or self.timestamp_ms,
                correlation_id=correlation_id,
                headers=headers or self.headers,
                reply_to=self.reply_to or "",
            )
        else:
            to_send: Iterable[SendableMessage]
            if not messages:
                if not isinstance(message, Sequence):
                    raise SetupError(
                        f"Message: {message} should be Sequence type to send in batch"
                    )
                else:
                    to_send = message
            else:
                to_send = messages

            await self._producer.publish_batch(
                *to_send,
                topic=self.topic,
                partition=partition or self.partition,
                timestamp_ms=timestamp_ms or self.timestamp_ms,
                headers=headers or self.headers,
            )
            return None
