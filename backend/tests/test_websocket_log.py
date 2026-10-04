"""A browser tab closing or reloading is normal: it must not be logged as an error (it was, with an empty message, on every reload),
while an unexpected failure still is, and says what it was."""
import asyncio
import logging

from fastapi import WebSocketDisconnect

import main


class FakeSocket:
    def __init__(self, failure):
        self.failure = failure
        self.accepted = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        raise self.failure

    async def close(self):
        pass


def run(failure, caplog):
    socket = FakeSocket(failure)
    with caplog.at_level(logging.INFO):
        asyncio.run(main.websocket_dose_stream(socket))
    assert socket not in main.active_websockets                         # always cleaned up
    return [r for r in caplog.records if r.levelno >= logging.ERROR], [r.getMessage() for r in caplog.records]


def test_a_client_leaving_is_not_an_error(caplog):
    errors, messages = run(WebSocketDisconnect(1001), caplog)
    assert not errors
    assert any("Client disconnected" in m for m in messages)


def test_an_unexpected_failure_is_still_an_error_and_names_its_type(caplog):
    errors, _ = run(RuntimeError("boom"), caplog)
    assert len(errors) == 1 and "RuntimeError: boom" in errors[0].getMessage()
