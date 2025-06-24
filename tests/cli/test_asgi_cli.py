import os
import random

import httpx
import pytest

from tests.marks import skip_windows


@pytest.mark.slow()
@skip_windows
def test_run_asgi(generate_template, faststream_cli) -> None:
    app_code = """
    import json

    from faststream import FastStream, specification
    from faststream.rabbit import RabbitBroker
    from faststream.asgi import AsgiResponse, get, make_asyncapi_asgi

    CONTEXT = {}

    @get
    async def context(scope):
        return AsgiResponse(json.dumps(CONTEXT).encode(), status_code=200)

    broker = RabbitBroker()
    app = FastStream(broker).as_asgi(
        asgi_routes=[
            ("/context", context),
            ("/liveness", AsgiResponse(b"hello world", status_code=200)),
            ("/docs", make_asyncapi_asgi(specification.AsyncAPI(broker))),
        ],
    )

    @app.on_startup
    async def start(test: int, port: int):
        CONTEXT["test"] = test
        CONTEXT["port"] = port
    """

    with generate_template(app_code) as app_path:
        port = random.randrange(40000, 65535)
        extra_param = random.randrange(1, 100)

        with faststream_cli(
            [
                "faststream",
                "run",
                f"{app_path.stem}:app",
                "--port",
                f"{port}",
                "--test",
                f"{extra_param}",  # test ASGI extra params
            ],
            extra_env={
                "PATH": f"{app_path.parent}:{os.environ['PATH']}",
                "PYTHONPATH": str(app_path.parent),
            },
        ):
            # Test liveness
            response = httpx.get(f"http://127.0.0.1:{port}/liveness")
            assert response.read().decode() == "hello world"
            assert response.status_code == 200

            # Test documentation
            response = httpx.get(f"http://127.0.0.1:{port}/docs")
            content = response.read().decode()
            assert content.strip().startswith("<!DOCTYPE html>")
            assert len(content) > 1200

            # Test extra context
            response = httpx.get(f"http://127.0.0.1:{port}/context")
            assert response.json() == {"test": extra_param, "port": port}
            assert response.status_code == 200
