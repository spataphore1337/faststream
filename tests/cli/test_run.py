import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import psutil
import pytest
from dirty_equals import IsPartialDict
from typer.testing import CliRunner

from faststream import FastStream
from faststream._internal.cli.main import cli as faststream_app
from tests.marks import skip_windows


@pytest.mark.slow()
@skip_windows
def test_run_asgi(generate_template, faststream_cli) -> None:
    app_code = """
    from faststream.asgi import AsgiFastStream, AsgiResponse
    from faststream.nats import NatsBroker

    broker = NatsBroker()

    app = AsgiFastStream(broker, asgi_routes=[
        ("/liveness", AsgiResponse(b"hello world", status_code=200)),
    ])
    """
    with (
        generate_template(app_code) as app_path,
        faststream_cli(
            [
                "faststream",
                "run",
                f"{app_path.stem}:app",
            ],
            extra_env={
                "PATH": f"{app_path.parent}:{os.environ['PATH']}",
                "PYTHONPATH": str(app_path.parent),
            },
        ),
    ):
        response = httpx.get("http://127.0.0.1:8000/liveness")
        assert response.read().decode() == "hello world"
        assert response.status_code == 200


@pytest.mark.slow()
@skip_windows
def test_run_as_asgi_with_single_worker(
    generate_template,
    faststream_cli,
):
    app_code = """
    from faststream.asgi import AsgiFastStream, AsgiResponse
    from faststream.nats import NatsBroker

    broker = NatsBroker()

    app = AsgiFastStream(broker, asgi_routes=[
        ("/liveness", AsgiResponse(b"hello world", status_code=200)),
    ])
    """
    with (
        generate_template(app_code) as app_path,
        faststream_cli(
            [
                "faststream",
                "run",
                f"{app_path.stem}:app",
                "--workers 1",
            ],
            extra_env={
                "PATH": f"{app_path.parent}:{os.environ['PATH']}",
                "PYTHONPATH": str(app_path.parent),
            },
        ),
    ):
        response = httpx.get("http://127.0.0.1:8000/liveness")
        assert response.read().decode() == "hello world"
        assert response.status_code == 200


@pytest.mark.slow()
@skip_windows
def test_run_as_asgi_with_many_workers(generate_template, faststream_cli):
    app_code = """
    from faststream.asgi import AsgiFastStream
    from faststream.nats import NatsBroker

    app = AsgiFastStream(NatsBroker())
    """

    with (
        generate_template(app_code) as app_path,
        faststream_cli(
            [
                "faststream",
                "run",
                f"{app_path.stem}:app",
                "--workers 2",
            ],
            extra_env={
                "PATH": f"{app_path.parent}:{os.environ['PATH']}",
                "PYTHONPATH": str(app_path.parent),
            },
        ) as cli_thread,
    ):
        process = psutil.Process(pid=cli_thread.process.pid)

        assert len(process.children()) == 3  # workers + 1 for the main process


@pytest.mark.slow()
@skip_windows
def test_run_as_asgi_mp_with_log_level(generate_template, faststream_cli) -> None:
    app_code = """
    import logging

    from faststream.asgi import AsgiFastStream
    from faststream.log.logging import logger
    from faststream.nats import NatsBroker

    app = AsgiFastStream(NatsBroker())

    @app.on_startup
    def print_log_level():
        logger.critical(f"Current log level is {logging.getLogger('uvicorn.asgi').level}")
    """

    log_level, numeric_log_level = "critical", logging.CRITICAL

    with (
        generate_template(app_code) as app_path,
        faststream_cli(
            [
                "faststream",
                "run",
                f"{app_path.stem}:app",
                "--workers",
                "3",
                "--log-level",
                log_level,
            ],
            extra_env={
                "PATH": f"{app_path.parent}:{os.environ['PATH']}",
                "PYTHONPATH": str(app_path.parent),
            },
        ) as cli_thread,
    ):
        pass

    stderr = cli_thread.process.stderr.read()
    assert f"Current log level is {numeric_log_level}" in stderr


def test_run_as_factory(generate_template, faststream_cli) -> None:
    app_code = """
    from faststream.asgi import AsgiFastStream, AsgiResponse, get
    from faststream.nats import NatsBroker

    broker = NatsBroker()

    def app_factory():
        return AsgiFastStream(broker, asgi_routes=[
            ("/liveness", AsgiResponse(b"hello world", status_code=200)),
        ])
    """

    with (
        generate_template(app_code) as app_path,
        faststream_cli(
            [
                "faststream",
                "run",
                f"{app_path.stem}:app_factory",
                "--factory",
            ],
            extra_env={
                "PATH": f"{app_path.parent}:{os.environ['PATH']}",
                "PYTHONPATH": str(app_path.parent),
            },
        )
    ):
        response = httpx.get("http://127.0.0.1:8000/liveness")
        assert response.read().decode() == "hello world"
        assert response.getcode() == 200


def test_run_reloader_with_factory(runner: CliRunner, mock: MagicMock) -> None:
    app = FastStream(MagicMock())
    app.run = AsyncMock()
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"app": {"format": "%(message)s"}},
        "handlers": {
            "app": {
                "class": "logging.StreamHandler",
                "formatter": "app",
                "level": "INFO",
            }
        },
        "loggers": {"app": {"level": "INFO", "handlers": ["app"]}},
    }
    with patch(
        "faststream._internal.cli.utils.logs._get_log_config",
        return_value=logging_config,
    ):
        app_str = "faststream:app"

        result = runner.invoke(
            faststream_app,
            [
                "run",
                app_str,
                "-f",
                "-r",
                "--app-dir",
                "test",
                "--extension",
                "yaml",
            ],
        )

        assert result.exit_code == 0

        assert mock.call_args.kwargs == IsPartialDict({
            "args": (app_str, {}, True, None, logging.NOTSET),
            "reload_dirs": ["test"],
            "extra_extensions": ["yaml"],
        })
