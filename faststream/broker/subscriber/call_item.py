from contextlib import AsyncExitStack
from inspect import unwrap
from itertools import chain
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generic,
    Iterable,
    Optional,
    cast,
)

from typing_extensions import override

from faststream.broker.proto import SetupAble
from faststream.broker.types import MsgType
from faststream.exceptions import IgnoredException, SetupError

if TYPE_CHECKING:
    from fast_depends.dependencies import Depends

    from faststream.broker.message import StreamMessage
    from faststream.broker.types import (
        AsyncDecoder,
        AsyncFilter,
        AsyncParser,
        CustomDecoder,
        CustomParser,
        SubscriberMiddleware,
    )
    from faststream.broker.wrapper.call import HandlerCallWrapper


class HandlerItem(SetupAble, Generic[MsgType]):
    """A class representing handler overloaded item."""

    __slots__ = (
        "handler",
        "filter",
        "dependant",
        "dependencies",
        "item_parser",
        "item_decoder",
        "item_middlewares",
    )

    dependant: Optional[Any]

    def __init__(
        self,
        *,
        handler: "HandlerCallWrapper[MsgType, ..., Any]",
        filter: "AsyncFilter[StreamMessage[MsgType]]",
        item_parser: Optional["CustomParser[MsgType]"],
        item_decoder: Optional["CustomDecoder[StreamMessage[MsgType]]"],
        item_middlewares: Iterable["SubscriberMiddleware"],
        dependencies: Iterable["Depends"],
    ) -> None:
        self.handler = handler
        self.filter = filter
        self.item_parser = item_parser
        self.item_decoder = item_decoder
        self.item_middlewares = item_middlewares
        self.dependencies = dependencies
        self.dependant = None

    def __repr__(self) -> str:
        filter_call = unwrap(self.filter)
        filter_name = getattr(filter_call, "__name__", str(filter_call))
        return f"<'{self.call_name}': filter='{filter_name}'>"

    @override
    def setup(  # type: ignore[override]
        self,
        *,
        parser: "AsyncParser[MsgType]",
        decoder: "AsyncDecoder[StreamMessage[MsgType]]",
        broker_dependencies: Iterable["Depends"],
        apply_types: bool,
        is_validate: bool,
        _get_dependant: Optional[Callable[..., Any]],
    ) -> None:
        if self.dependant is None:
            self.item_parser = parser
            self.item_decoder = decoder

            dependencies = (*broker_dependencies, *self.dependencies)

            dependant = self.handler.set_wrapped(
                apply_types=apply_types,
                is_validate=is_validate,
                dependencies=dependencies,
                _get_dependant=_get_dependant,
            )

            if _get_dependant is None:
                self.dependant = dependant
            else:
                self.dependant = _get_dependant(self.handler._original_call, dependencies)

    @property
    def call_name(self) -> str:
        """Returns the name of the original call."""
        if self.handler is None:
            return ""

        caller = unwrap(self.handler._original_call)
        name = getattr(caller, "__name__", str(caller))
        return name

    @property
    def description(self) -> Optional[str]:
        """Returns the description of original call."""
        if self.handler is None:
            return None

        caller = unwrap(self.handler._original_call)
        description = getattr(caller, "__doc__", None)
        return description

    async def is_suitable(
        self,
        msg: MsgType,
        cache: Dict[Any, Any],
    ) -> Optional["StreamMessage[MsgType]"]:
        """Check is message suite for current filter."""
        if not (
            parser := cast(Optional["AsyncParser[MsgType]"], self.item_parser)
        ) or not (
            decoder := cast(
                Optional["AsyncDecoder[StreamMessage[MsgType]]"], self.item_decoder
            )
        ):
            raise SetupError("You should setup `HandlerItem` at first.")

        message = cache[parser] = cast(
            "StreamMessage[MsgType]", cache.get(parser) or await parser(msg)
        )

        message.decoded_body = cache[decoder] = cache.get(decoder) or await decoder(
            message
        )

        if await self.filter(message):
            return message

        return None

    async def call(
        self,
        /,
        message: "StreamMessage[MsgType]",
        extra_middlewares: Iterable["SubscriberMiddleware"],
    ) -> Any:
        """Execute wrapped handler with consume middlewares."""
        async with AsyncExitStack() as consume_stack:
            for middleware in chain(self.item_middlewares, extra_middlewares):
                message.decoded_body = await consume_stack.enter_async_context(
                    middleware(message.decoded_body)
                )

            try:
                result = await self.handler.call_wrapped(message)

            except (IgnoredException, SystemExit):
                self.handler.trigger()
                raise

            except Exception as e:
                self.handler.trigger(error=e)
                raise e

            else:
                self.handler.trigger(result=result)
                return result
