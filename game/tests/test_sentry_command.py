import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings


@override_settings(SENTRY_DSN="")
def test_sentry_command_requires_dsn(monkeypatch):
    from game.management.commands import test_sentry as cmd

    monkeypatch.setattr(cmd.sentry_sdk, "capture_message", lambda *a, **k: "msg-id")

    with pytest.raises(CommandError, match="SENTRY_DSN is empty"):
        call_command("test_sentry")


@override_settings(SENTRY_DSN="https://examplePublicKey@o0.ingest.sentry.io/0")
def test_sentry_command_sends_message_and_exception(monkeypatch):
    from game.management.commands import test_sentry as cmd

    called = {"message": None, "exception": False, "flush": None}

    def fake_capture_message(message, level="warning"):
        called["message"] = (message, level)
        return "message-event-id"

    def fake_capture_exception(exc):
        called["exception"] = isinstance(exc, RuntimeError)
        return "exception-event-id"

    def fake_flush(timeout=2.0):
        called["flush"] = timeout

    monkeypatch.setattr(cmd.sentry_sdk, "capture_message", fake_capture_message)
    monkeypatch.setattr(cmd.sentry_sdk, "capture_exception", fake_capture_exception)
    monkeypatch.setattr(cmd.sentry_sdk, "flush", fake_flush)

    out = io.StringIO()
    call_command(
        "test_sentry",
        "--message",
        "smoke-check",
        "--level",
        "error",
        "--with-exception",
        stdout=out,
    )

    output = out.getvalue()
    assert "Sentry message event sent" in output
    assert "Sentry exception event sent" in output
    assert "Sentry flush finished" in output

    assert called["message"] == ("smoke-check", "error")
    assert called["exception"] is True
    assert called["flush"] == 2.0
