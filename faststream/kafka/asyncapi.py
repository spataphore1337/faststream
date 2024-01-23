from typing import Dict

from faststream.asyncapi.base import AsyncAPIOperation
from faststream.asyncapi.schema import (
    Channel,
    ChannelBinding,
    CorrelationId,
    Message,
    Operation,
)
from faststream.asyncapi.schema.bindings import kafka
from faststream.asyncapi.utils import resolve_payloads
from faststream.kafka.handler import LogicHandler
from faststream.kafka.publisher import LogicPublisher


class Handler(LogicHandler, AsyncAPIOperation):
    """A class to handle logic and async API operations.

    Methods:
        schema() -> Dict[str, Channel]: Returns a dictionary of channels.
    """

    def get_name(self) -> str:
        return f'{",".join(self.topics)}:{self.call_name}'

    def get_schema(self) -> Dict[str, Channel]:
        channels = {}

        payloads = self.get_payloads()

        for t in self.topics:
            handler_name = self._title or f"{t}:{self.call_name}"
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
                bindings=ChannelBinding(kafka=kafka.ChannelBinding(topic=t)),
            )

        return channels


class Publisher(LogicPublisher, AsyncAPIOperation):
    """A class representing a publisher.

    Attributes:
        name : name of the publisher

    Methods:
        schema() : returns the schema for the publisher
    """

    def get_name(self) -> str:
        return f"{self.topic}:Publisher"

    def get_schema(self) -> Dict[str, Channel]:

        payloads = self.get_payloads()

        return {
            self.name: Channel(
                description=self.description,
                publish=Operation(
                    message=Message(
                        title=f"{self.name}:Message",
                        payload=resolve_payloads(payloads, "Publisher"),
                        correlationId=CorrelationId(
                            location="$message.header#/correlation_id"
                        ),
                    ),
                ),
                bindings=ChannelBinding(kafka=kafka.ChannelBinding(topic=self.topic)),
            )
        }
