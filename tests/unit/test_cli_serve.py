import argparse

import pytest

from src.cli import cmd_serve


def test_cmd_serve_invokes_uvicorn(monkeypatch):
    called = {}

    def fake_run(app, host, port, reload):  # pragma: no cover
        called.update({"app": app, "host": host, "port": port, "reload": reload})

    monkeypatch.setattr("src.cli.uvicorn.run", fake_run)

    args = argparse.Namespace(app="src.agents.http_api:app", host="127.0.0.1", port=9000, reload=True)
    cmd_serve(args, {})

    assert called == {
        "app": "src.agents.http_api:app",
        "host": "127.0.0.1",
        "port": 9000,
        "reload": True,
    }

