from aio_pika import IncomingMessage

from faststream.broker.fastapi.router import StreamRouter
from faststream.rabbit.broker import RabbitBroker as RB


class RabbitRouter(StreamRouter[IncomingMessage]):
    """A class to represent a RabbitMQ router for incoming messages.

    Attributes:
        broker_class : the class representing the RabbitMQ broker

    Methods:
        _setup_log_context : sets up the log context for the main broker and the including broker
    """

    broker_class = RB

    @staticmethod
    def _setup_log_context(
        main_broker: RB,
        including_broker: RB,
    ) -> None:
        """Sets up the log context for a main broker and an including broker.

        Args:
            main_broker: The main broker object.
            including_broker: The including broker object.

        Returns:
            None
        """
        for h in including_broker.handlers.values():
            main_broker._setup_log_context(h.queue, h.exchange)
