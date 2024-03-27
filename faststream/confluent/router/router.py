from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, Optional

from typing_extensions import override

from faststream.broker.core.call_wrapper import HandlerCallWrapper
from faststream.broker.router import BrokerRoute, BrokerRouter
from faststream.broker.types import P_HandlerParams, T_HandlerReturn
from faststream.confluent.asyncapi import Publisher

if TYPE_CHECKING:
    from aiokafka import ConsumerRecord


class KafkaRouter(BrokerRouter[str, "ConsumerRecord"]):
    """A class to represent a Kafka router.

    Attributes:
        _publishers : Dictionary of publishers

    Methods:
        _update_publisher_prefix : Update the prefix of a publisher
        publisher : Create a new publisher
    """

    _publishers: Dict[str, Publisher]  # type: ignore[assignment]

    def __init__(
        self,
        prefix: str = "",
        handlers: Iterable[BrokerRoute] = (),
        **kwargs: Any,
    ) -> None:
        """Initialize the class.

        Args:
            prefix (str): Prefix string.
            handlers (Sequence[KafkaRoute[ConsumerRecord, SendableMessage]]): Sequence of KafkaRoute objects.
            **kwargs (Any): Additional keyword arguments.
        """
        for h in handlers:
            h.args = tuple(prefix + x for x in h.args)
        super().__init__(prefix, handlers, **kwargs)

    def subscriber(
        self,
        *topics: str,
        **broker_kwargs: Any,
    ) -> Callable[
        [Callable[P_HandlerParams, T_HandlerReturn]],
        HandlerCallWrapper["ConsumerRecord", P_HandlerParams, T_HandlerReturn],
    ]:
        """A function to subscribe to topics.

        Args:
            *topics : variable number of topic names
            **broker_kwargs : keyword arguments for the broker

        Returns:
            A callable function that wraps the handler function

        """
        return self._wrap_subscriber(
            *(self.prefix + x for x in topics),
            **broker_kwargs,
        )

    @override
    def publisher(  # type: ignore[override]
        self,
        topic: str,
        key: Optional[bytes] = None,
        partition: Optional[int] = None,
        timestamp_ms: Optional[int] = None,
        headers: Optional[Dict[str, str]] = None,
        reply_to: str = "",
        batch: bool = False,
        # AsyncAPI information
        title: Optional[str] = None,
        description: Optional[str] = None,
        schema: Optional[Any] = None,
        include_in_schema: bool = True,
    ) -> Publisher:
        """Publishes a message to a topic.

        Args:
            topic (str): The topic to publish the message to.
            key (bytes, optional): The key associated with the message.
            partition (int, optional): The partition to publish the message to.
            timestamp_ms (int, optional): The timestamp of the message in milliseconds.
            headers (Dict[str, str], optional): Additional headers for the message.
            reply_to (str, optional): The topic to reply to.
            batch (bool, optional): Whether to publish the message as part of a batch.
            title (str, optional): The title of the message.
            description (str, optional): The description of the message.
            schema (Any, optional): The schema of the message.
            include_in_schema (bool, optional): Whether to include the message in the schema.

        Returns:
            Publisher: The publisher object used to publish the message.

        """
        new_publisher = self._update_publisher_prefix(
            self.prefix,
            Publisher(
                topic=topic,
                key=key,
                partition=partition,
                timestamp_ms=timestamp_ms,
                headers=headers,
                reply_to=reply_to,
                title=title,
                batch=batch,
                _description=description,
                _schema=schema,
                include_in_schema=(
                    include_in_schema
                    if self.include_in_schema is None
                    else self.include_in_schema
                ),
            ),
        )
        publisher_key = hash(new_publisher)
        publisher = self._publishers[publisher_key] = self._publishers.get(
            publisher_key, new_publisher
        )
        return publisher
