from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faststream._internal.types import BrokerMiddleware, MsgType


@dataclass
class EndpointConfig:
    broker_middlewares: Sequence["BrokerMiddleware[MsgType]"]
