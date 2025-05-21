from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from faststream._internal.endpoint.usecase import EndpointConfig
from faststream.middlewares import AckPolicy

if TYPE_CHECKING:
    from fast_depends.dependencies import Dependant

    from faststream._internal.types import AsyncCallable


@dataclass
class SubscriberUsecaseConfig(EndpointConfig):
    broker_dependencies: Iterable["Dependant"]

    default_parser: Optional["AsyncCallable"]
    default_decoder: Optional["AsyncCallable"]

    no_reply: bool

    _ack_policy: AckPolicy = field(repr=False)

    @property
    def ack_policy(self) -> AckPolicy:
        raise NotImplementedError
