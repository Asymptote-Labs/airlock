import argparse
import hashlib

import pytest
from fastapi.testclient import TestClient

from airlock.app import create_app
from airlock.artifact import unpack
from airlock.cli import protect


@pytest.fixture
def client(tmp_path, monkeypatch):
    app = create_app(tmp_path / "server")
    tokens = app.state.store.initialize()
    monkeypatch.setenv("AIRLOCK_ADMIN_TOKEN", tokens["admin"])

    def factory(**kwargs):
        return TestClient(app, headers=kwargs["headers"])

    monkeypatch.setattr("airlock.cli.httpx.Client", factory)
    return app.state.store


def test_default_replace_and_keep_source(tmp_path, client):
    source = tmp_path / "employees.csv"
    content = b"\xef\xbb\xbfname\r\nMaya\r\n"
    source.write_bytes(content)
    protect(argparse.Namespace(file=str(source), output=None, keep_source=False))
    target = source.with_name(source.name + ".airlock")
    assert not source.exists()
    artifact = target.read_bytes()
    assert client.decrypt(unpack(artifact)[0]["object_id"], artifact) == content
    source.write_bytes(content)
    with pytest.raises(ValueError, match="overwrite"):
        protect(argparse.Namespace(file=str(source), output=None))
    keep = tmp_path / "kept.airlock"
    protect(argparse.Namespace(file=str(source), output=str(keep), keep_source=True))
    assert source.read_bytes() == content


def test_write_failure_retains_source(tmp_path, client, monkeypatch):
    source = tmp_path / "employees.csv"
    source.write_text("name\nMaya\n")

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr("airlock.cli.os.link", fail)
    with pytest.raises(ValueError, match="Source retained"):
        protect(argparse.Namespace(file=str(source), output=None))
    assert source.read_text() == "name\nMaya\n"
    assert not source.with_name(source.name + ".airlock").exists()


def test_verification_failure_retains_source(tmp_path, client, monkeypatch):
    source = tmp_path / "employees.csv"
    source.write_text("name\nMaya\n")
    monkeypatch.setattr(client, "decrypt", lambda *args: b"different plaintext")
    with pytest.raises(ValueError, match="Round-trip"):
        protect(argparse.Namespace(file=str(source), output=None))
    assert hashlib.sha256(source.read_bytes()).hexdigest()
    assert not source.with_name(source.name + ".airlock").exists()
