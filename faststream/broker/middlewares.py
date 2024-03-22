from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any, AsyncIterator, Optional, Type, cast

from typing_extensions import Self

from faststream.types import DecodedMessage, LoggerProtocol, SendableMessage
from faststream.utils.context.repository import context


class BaseMiddleware:
    """A base middleware class.

    Attributes:
        msg: Any - a message

    Methods:
        on_receive() -> None:
            Called when a message is received.

        after_processed(exc_type: Optional[Type[BaseException]] = None, exc_val: Optional[BaseException] = None, exc_tb: Optional[TracebackType] = None) -> Optional[bool]:
            Called after processing a message.

        __aenter__() -> Self:
            Called when entering a context.

        __aexit__(exc_type: Optional[Type[BaseException]] = None, exc_val: Optional[BaseException] = None, exc_tb: Optional[TracebackType] = None) -> Optional[bool]:
            Called when exiting a context.

        on_consume(msg: DecodedMessage) -> DecodedMessage:
            Called before consuming a message.

        after_consume(err: Optional[Exception]) -> None:
            Called after consuming a message.

        consume_scope(msg: DecodedMessage) -> AsyncIterator[DecodedMessage]:
            Context manager for consuming a message.

        on_publish(msg: SendableMessage) -> SendableMessage:
            Called before publishing a message.

        after_publish(err: Optional[Exception]) -> None:
            Asynchronous function to handle the after publish event.
    """

    def __init__(self, msg: Optional[Any] = None) -> None:
        """Initialize the class."""
        self.msg = msg

    async def on_receive(self) -> None:
        pass

    async def after_processed(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_val: Optional[BaseException] = None,
        exc_tb: Optional[TracebackType] = None,
    ) -> Optional[bool]:
        """Asynchronously called after processing.

        Args:
            exc_type: Optional exception type
            exc_val: Optional exception value
            exc_tb: Optional traceback

        Returns:
            Optional boolean value indicating whether the processing was successful or not.
        """
        return False

    async def __aenter__(self) -> Self:
        await self.on_receive()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_val: Optional[BaseException] = None,
        exc_tb: Optional[TracebackType] = None,
    ) -> Optional[bool]:
        """Exit the asynchronous context manager.

        Args:
            exc_type: The type of the exception raised, if any.
            exc_val: The exception instance raised, if any.
            exc_tb: The traceback for the exception raised, if any.

        Returns:
            A boolean indicating whether the exception was handled or not.
        """
        return await self.after_processed(exc_type, exc_val, exc_tb)

    async def on_consume(
        self, msg: Optional[DecodedMessage]
    ) -> Optional[DecodedMessage]:
        """Asynchronously consumes a message.

        Args:
            msg: The message to be consumed.

        Returns:
            The consumed message.
        """
        return msg

    async def after_consume(self, err: Optional[Exception]) -> None:
        """A function to handle the result of consuming a resource asynchronously.

        Args:
            err : Optional exception that occurred during consumption

        Raises:
            err : If an exception occurred during consumption
        """
        if err is not None:
            raise err

    @asynccontextmanager
    async def consume_scope(
        self, msg: Optional[DecodedMessage]
    ) -> AsyncIterator[Optional[DecodedMessage]]:
        """Asynchronously consumes a message and returns an asynchronous iterator of decoded messages.

        Args:
            msg: The decoded message to consume.

        Yields:
            An asynchronous iterator of decoded messages.

        Returns:
            An asynchronous iterator of decoded messages.

        Raises:
            Exception: If an error occurs while consuming the message.

        AsyncIterator:
            An asynchronous iterator that yields decoded messages.

        Note:
            This function is an async function.
        """
        err: Optional[Exception]
        try:
            yield await self.on_consume(msg)
        except Exception as e:
            err = e
        else:
            err = None
        await self.after_consume(err)

    async def on_publish(self, msg: Any, *args: Any, **kwargs: Any) -> Any:
        """Asynchronously handle a publish event.

        Args:
            msg: The message to be published.

        Returns:
            The published message.
        """
        return msg

    async def after_publish(self, err: Optional[Exception]) -> None:
        """Asynchronous function to handle the after publish event.

        Args:
            err: Optional exception that occurred during the publish

        Returns:
            None

        Raises:
            Exception: If an error occurred during the publish
        """
        if err is not None:
            raise err

    @asynccontextmanager
    async def publish_scope(
        self, msg: Any, *args: Any, **kwargs: Any
    ) -> AsyncIterator[SendableMessage]:
        """Publish a message and return an async iterator.

        Args:
            msg: The message to be published.

        Yields:
            A sendable message.

        Returns:
            An async iterator of sendable messages.

        Raises:
            Exception: If an error occurs during publishing.

        """
        err: Optional[Exception]
        try:
            yield cast(SendableMessage, await self.on_publish(msg, *args, **kwargs))
        except Exception as e:
            err = e
        else:
            err = None
        await self.after_publish(err)


class CriticalLogMiddleware(BaseMiddleware):
    """A middleware class for logging critical errors.

    Args:
        logger: The logger object to use for logging

    Methods:
        __call__(msg: Any) -> Self: Returns the middleware instance
        after_processed(exc_type: Optional[Type[BaseException]] = None, exc_val: Optional[BaseException] = None, exc_tb: Optional[TracebackType] = None) -> bool: Logs critical errors if they occur and returns True
    """

    def __init__(
        self,
        logger: Optional[LoggerProtocol],
        log_level: int,
    ) -> None:
        """Initialize the class.

        Args:
            logger: an instance of the logging.Logger class
            log_level: the log level to use for logging

        Returns:
            None
        """
        self.logger = logger
        self.log_level = log_level

    def __call__(self, *args: Any) -> Self:
        """Call the object with a message.

        Returns:
            The object itself.
        """
        return self

    async def on_consume(
        self, msg: Optional[DecodedMessage]
    ) -> Optional[DecodedMessage]:
        if self.logger is not None:
            c = context.get_local("log_context") or {}
            self.logger.log(self.log_level, "Received", extra=c)

        return await super().on_consume(msg)

    async def after_processed(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_val: Optional[BaseException] = None,
        exc_tb: Optional[TracebackType] = None,
    ) -> bool:
        """Asynchronously called after processing.

        Args:
            exc_type (Optional[Type[BaseException]]): Type of the exception raised during processing.
            exc_val (Optional[BaseException]): Value of the exception raised during processing.
            exc_tb (Optional[TracebackType]): Traceback of the exception raised during processing.

        Returns:
            bool: True if the method is successfully executed.
        """
        if self.logger is not None:
            c = context.get_local("log_context") or {}

            if exc_type and exc_val:
                self.logger.error(
                    f"{exc_type.__name__}: {exc_val}",
                    exc_info=exc_val,
                    extra=c,
                )

            self.logger.log(self.log_level, "Processed", extra=c)

        await super().after_processed(exc_type, exc_val, exc_tb)
        return True
