from faststream import FastStream
from faststream.redis import RedisBroker
from faststream.specification.asyncapi.generate import get_app_schema
from faststream.specification.schema.tag import Tag


def test_base():
    schema = get_app_schema(
        FastStream(
            RedisBroker(
                "redis://localhost:6379",
                protocol="plaintext",
                protocol_version="0.9.0",
                description="Test description",
                tags=(Tag(name="some-tag", description="experimental"),),
            ),
        ),
        version="3.0.0",
    ).to_jsonable()

    assert schema == {
        "asyncapi": "3.0.0",
        "channels": {},
        "operations": {},
        "components": {"messages": {}, "schemas": {}},
        "defaultContentType": "application/json",
        "info": {"description": "", "title": "FastStream", "version": "0.1.0"},
        "servers": {
            "development": {
                "description": "Test description",
                "protocol": "plaintext",
                "protocolVersion": "0.9.0",
                "tags": [{"description": "experimental", "name": "some-tag"}],
                "host": "localhost:6379",
                "pathname": "",
            }
        },
    }, schema


def test_custom():
    schema = get_app_schema(
        FastStream(
            RedisBroker(
                "redis://localhost:6379", specification_url="rediss://127.0.0.1:8000"
            ),
        ),
        version="3.0.0",
    ).to_jsonable()

    assert schema == {
        "asyncapi": "3.0.0",
        "channels": {},
        "operations": {},
        "components": {"messages": {}, "schemas": {}},
        "defaultContentType": "application/json",
        "info": {"description": "", "title": "FastStream", "version": "0.1.0"},
        "servers": {
            "development": {
                "protocol": "rediss",
                "protocolVersion": "custom",
                "host": "127.0.0.1:8000",
                "pathname": "",
            }
        },
    }