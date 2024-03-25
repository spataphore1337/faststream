import pytest

from faststream import TestApp
from faststream.nats import TestNatsBroker


@pytest.mark.asyncio()
@pytest.mark.nats()
async def test_basic():
    from docs.docs_src.nats.js.object import app, broker, handler

    async with TestNatsBroker(broker, with_real=True), TestApp(app):
        await handler.wait_call(3.0)
        handler.mock.assert_called_once_with("Hi!")
