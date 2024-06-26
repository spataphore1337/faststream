import logging
from inspect import Parameter
from typing import TYPE_CHECKING, Any, ClassVar, Optional, Tuple, Union

from faststream.broker.core.usecase import BrokerUsecase
from faststream.kafka.schemas.params import ConsumerConnectionParams
from faststream.log.logging import get_broker_logger

if TYPE_CHECKING:
    import aiokafka

    from faststream.types import LoggerProto


class KafkaLoggingBroker(
    BrokerUsecase[
        Union["aiokafka.ConsumerRecord", Tuple["aiokafka.ConsumerRecord", ...]],
        ConsumerConnectionParams,
    ]
):
    """A class that extends the LoggingMixin class and adds additional functionality for logging Kafka related information."""

    _max_topic_len: int
    _max_group_len: int
    __max_msg_id_ln: ClassVar[int] = 10

    def __init__(
        self,
        *args: Any,
        logger: Union["LoggerProto", object, None] = Parameter.empty,
        log_level: int = logging.INFO,
        log_fmt: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the class."""
        super().__init__(
            *args,
            logger=logger,
            # TODO: generate unique logger names to not share between brokers
            default_logger=get_broker_logger(
                name="kafka",
                default_context={
                    "topic": "",
                    "group_id": "",
                },
                message_id_ln=self.__max_msg_id_ln,
            ),
            log_level=log_level,
            log_fmt=log_fmt,
            **kwargs,
        )
        self._max_topic_len = 4
        self._max_group_len = 0

    def get_fmt(self) -> str:
        return (
            "%(asctime)s %(levelname)-8s - "
            + f"%(topic)-{self._max_topic_len}s | "
            + (f"%(group_id)-{self._max_group_len}s | " if self._max_group_len else "")
            + f"%(message_id)-{self.__max_msg_id_ln}s "
            + "- %(message)s"
        )

    def _setup_log_context(
        self,
        *,
        topic: str = "",
        group_id: Optional[str] = None,
    ) -> None:
        """Set up log context."""
        self._max_topic_len = max((self._max_topic_len, len(topic)))
        self._max_group_len = max((self._max_group_len, len(group_id or "")))
