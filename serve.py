from faststream import FastStream, Logger
from faststream.confluent import KafkaBroker, KafkaMessage

from loguru import logger
broker = KafkaBroker(logger=logger)


@broker.subscriber("test", auto_offset_reset="earliest")
async def handle_message(
    message: KafkaMessage,
    logger: Logger,
) -> None:
    logger.info(f"Received message: {message.raw_message.timestamp()}")


app = FastStream(broker)
