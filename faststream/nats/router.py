from typing import TYPE_CHECKING, Callable, Iterable, Optional, Union

from nats.js import api
from typing_extensions import Annotated, Doc, deprecated

from faststream.broker.router import BrokerRouter, SubscriberRoute
from faststream.broker.utils import default_filter
from faststream.nats.broker.registrator import NatsRegistrator

if TYPE_CHECKING:
    from fast_depends.dependencies import Depends
    from nats.aio.msg import Msg

    from faststream.broker.message import StreamMessage
    from faststream.broker.types import (
        BrokerMiddleware,
        CustomDecoder,
        CustomParser,
        Filter,
        SubscriberMiddleware,
    )
    from faststream.nats.schemas import JStream, PullSub
    from faststream.types import SendableMessage



class NatsRoute(SubscriberRoute):
    """Class to store delaied RabbitBroker subscriber registration."""

    def __init__(
        self,
        call: Annotated[
            Callable[..., "SendableMessage"],
            Doc("Message handler function."),
        ],
        subject: Annotated[
            str,
            Doc("NATS subject to subscribe."),
        ],
        queue: Annotated[
            str,
            Doc(
                "Subscribers' NATS queue name. Subscribers with same queue name will be load balanced by the NATS "
                "server."
            ),
        ] = "",
        pending_msgs_limit: Annotated[
            Optional[int],
            Doc(
                "Limit of messages, considered by NATS server as possible to be delivered to the client without "
                "been answered. In case of NATS Core, if that limits exceeds, you will receive NATS 'Slow Consumer' "
                "error. "
                "That's literally means that your worker can't handle the whole load. In case of NATS JetStream, "
                "you will no longer receive messages until some of delivered messages will be acked in any way."
            ),
        ] = None,
        pending_bytes_limit: Annotated[
            Optional[int],
            Doc(
                "The number of bytes, considered by NATS server as possible to be delivered to the client without "
                "been answered. In case of NATS Core, if that limit exceeds, you will receive NATS 'Slow Consumer' "
                "error."
                "That's literally means that your worker can't handle the whole load. In case of NATS JetStream, "
                "you will no longer receive messages until some of delivered messages will be acked in any way."
            ),
        ] = None,
        # Core arguments
        max_msgs: Annotated[
            int,
            Doc("Consuming messages limiter. Automatically disconnect if reached."),
        ] = 0,
        # JS arguments
        durable: Annotated[
            Optional[str],
            Doc(
                "Name of the durable consumer to which the the subscription should be bound."
            ),
        ] = None,
        config: Annotated[
            Optional["api.ConsumerConfig"],
            Doc("Configuration of JetStream consumer to be subscribed with."),
        ] = None,
        ordered_consumer: Annotated[
            bool,
            Doc("Enable ordered consumer mode."),
        ] = False,
        idle_heartbeat: Annotated[
            Optional[float],
            Doc("Enable Heartbeats for a consumer to detect failures."),
        ] = None,
        flow_control: Annotated[
            bool,
            Doc("Enable Flow Control for a consumer."),
        ] = False,
        deliver_policy: Annotated[
            Optional["api.DeliverPolicy"],
            Doc("Deliver Policy to be used for subscription."),
        ] = None,
        headers_only: Annotated[
            Optional[bool],
            Doc(
                "Should be message delivered without payload, only headers and metadata."
            ),
        ] = None,
        # pull arguments
        pull_sub: Annotated[
            Optional["PullSub"],
            Doc(
                "NATS Pull consumer parameters container. "
                "Should be used with `stream` only."
            ),
        ] = None,
        inbox_prefix: Annotated[
            bytes,
            Doc(
                "Prefix for generating unique inboxes, subjects with that prefix and NUID."
            ),
        ] = api.INBOX_PREFIX,
        # custom
        ack_first: Annotated[
            bool,
            Doc("Whether to `ack` message at start of consuming or not."),
        ] = False,
        stream: Annotated[
            Union[str, "JStream", None],
            Doc("Subscribe to NATS Stream with `subject` filter."),
        ] = None,
        # broker arguments
        dependencies: Annotated[
            Iterable["Depends"],
            Doc("Dependencies list (`[Depends(),]`) to apply to the subscriber."),
        ] = (),
        parser: Annotated[
            Optional["CustomParser[Msg]"],
            Doc("Parser to map original **nats-py** Msg to FastStream one."),
        ] = None,
        decoder: Annotated[
            Optional["CustomDecoder[StreamMessage[Msg]]"],
            Doc("Function to decode FastStream msg bytes body to python objects."),
        ] = None,
        middlewares: Annotated[
            Iterable["SubscriberMiddleware"],
            Doc("Subscriber middlewares to wrap incoming message processing."),
        ] = (),
        filter: Annotated[
            "Filter[StreamMessage[Msg]]",
            Doc(
                "Overload subscriber to consume various messages from the same source."
            ),
            deprecated(
                "Deprecated in **FastStream 0.5.0**. "
                "Please, create `subscriber` object and use it explicitly instead. "
                "Argument will be removed in **FastStream 0.6.0**."
            ),
        ] = default_filter,
        max_workers: Annotated[
            int,
            Doc("Number of workers to process messages concurrently."),
        ] = 1,
        retry: Annotated[
            bool,
            Doc("Whether to `nack` message at processing exception."),
        ] = False,
        no_ack: Annotated[
            bool,
            Doc("Whether to disable **FastStream** autoacknowledgement logic or not."),
        ] = False,
        # AsyncAPI information
        title: Annotated[
            Optional[str],
            Doc("AsyncAPI subscriber object title."),
        ] = None,
        description: Annotated[
            Optional[str],
            Doc(
                "AsyncAPI subscriber object description. "
                "Uses decorated docstring as default."
            ),
        ] = None,
        include_in_schema: Annotated[
            bool,
            Doc("Whetever to include operation in AsyncAPI schema or not."),
        ] = True,
    ) -> None:
        super().__init__(
            call,
            subject=subject,
            pending_msgs_limit=pending_msgs_limit,
            pending_bytes_limit=pending_bytes_limit,
            max_msgs=max_msgs,
            durable=durable,
            config=config,
            ordered_consumer=ordered_consumer,
            idle_heartbeat=idle_heartbeat,
            flow_control=flow_control,
            deliver_policy=deliver_policy,
            headers_only=headers_only,
            pull_sub=pull_sub,
            inbox_prefix=inbox_prefix,
            ack_first=ack_first,
            stream=stream,
            max_workers=max_workers,
            queue=queue,
            dependencies=dependencies,
            parser=parser,
            decoder=decoder,
            middlewares=middlewares,
            filter=filter,
            retry=retry,
            no_ack=no_ack,
            title=title,
            description=description,
            include_in_schema=include_in_schema,
        )


class NatsRouter(
    BrokerRouter["Msg"],
    NatsRegistrator,
):
    """Includable to NatsBroker router."""

    def __init__(
        self,
        prefix: Annotated[
            str,
            Doc("String prefix to add to all subscribers subjects."),
        ] = "",
        handlers: Annotated[
            Iterable[NatsRoute],
            Doc("Route object to include."),
        ] = (),
        *,
        dependencies: Annotated[
            Iterable["Depends"],
            Doc(
                "Dependencies list (`[Depends(),]`) to apply to all routers' publishers/subscribers."
            ),
        ] = (),
        middlewares: Annotated[
            Iterable["BrokerMiddleware[Msg]"],
            Doc("Router middlewares to apply to all routers' publishers/subscribers."),
        ] = (),
        parser: Annotated[
            Optional["CustomParser[Msg]"],
            Doc("Parser to map original **IncomingMessage** Msg to FastStream one."),
        ] = None,
        decoder: Annotated[
            Optional["CustomDecoder[StreamMessage[Msg]]"],
            Doc("Function to decode FastStream msg bytes body to python objects."),
        ] = None,
        include_in_schema: Annotated[
            Optional[bool],
            Doc("Whetever to include operation in AsyncAPI schema or not."),
        ] = None,
    ) -> None:
        super().__init__(
            handlers=handlers,
            # basic args
            prefix=prefix,
            dependencies=dependencies,
            middlewares=middlewares,
            parser=parser,
            decoder=decoder,
            include_in_schema=include_in_schema,
        )
