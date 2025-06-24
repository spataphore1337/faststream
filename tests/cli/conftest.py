import os
import subprocess
import threading
import time
from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from textwrap import dedent
from typing import Protocol

import pytest

from faststream import FastStream


@pytest.fixture()
def broker():
    # separate import from e2e tests
    from faststream.rabbit import RabbitBroker

    return RabbitBroker()


@pytest.fixture()
def app_without_logger(broker) -> FastStream:
    return FastStream(broker, logger=None)


@pytest.fixture()
def app_without_broker() -> FastStream:
    return FastStream()


@pytest.fixture()
def app(broker) -> FastStream:
    return FastStream(broker)


@pytest.fixture
def faststream_tmp_path(tmp_path: "Path"):
    faststream_tmp = tmp_path / "faststream_templates"
    faststream_tmp.mkdir(exist_ok=True)
    return faststream_tmp


class GenerateTemplateFactory(Protocol):
    def __call__(
        self, code: str, filename: str = "temp_app.py"
    ) -> AbstractContextManager[Path]: ...


@pytest.fixture()
def generate_template(
    faststream_tmp_path: "Path",
) -> GenerateTemplateFactory:
    @contextmanager
    def factory(
        code: str, filename: str = "temp_app.py"
    ) -> Generator["Path", None, None]:
        file_path: Path = faststream_tmp_path / filename
        cleaned_code = dedent(code).strip()

        file_path.write_text(cleaned_code)

        try:
            yield file_path
        finally:
            file_path.unlink(missing_ok=True)

    return factory


class CliThread(Protocol):
    process: subprocess.Popen

    def stop(self) -> None: ...


class FastStreamCLIFactory(Protocol):
    def __call__(
        self,
        *cmd: str,
        wait_time: float = 2.0,
        extra_env: dict[str, str] | None = None,
    ) -> AbstractContextManager[CliThread]: ...


@pytest.fixture()
def faststream_cli(faststream_tmp_path: Path) -> FastStreamCLIFactory:
    @contextmanager
    def factory(
        *cmd: str,
        wait_time: float = 2.0,
        extra_env: dict[str, str] | None = None,
    ) -> Generator[CliThread, None, None]:
        class RealCLIThread(threading.Thread):
            def __init__(self, command: tuple[str, ...], env: dict[str, str]) -> None:
                super().__init__()

                self.process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    shell=False,
                    env=env,
                )

            def stop(self) -> None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()

        extra_env = extra_env or {}
        env = os.environ.copy()

        if extra_env:
            env.update(**extra_env)

        env.update(
            PATH=f"{faststream_tmp_path}:{os.environ['PATH']}",
            PYTHONPATH=str(faststream_tmp_path),
        )

        cli = RealCLIThread(cmd, env)
        cli.start()

        wait_for_startup(cli.process, wait_time)

        try:
            yield cli
        finally:
            cli.stop()
            cli.join()

    return factory


def wait_for_startup(
    process: subprocess.Popen,
    timeout: float = 10,
    check_interval: float = 0.1,
) -> None:
    start_time = time.time()

    while time.time() - start_time < timeout:
        if process.poll() is not None:
            return

        time.sleep(check_interval)

    return
