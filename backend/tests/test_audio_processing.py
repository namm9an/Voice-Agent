import pytest
from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("status") == "healthy"


def test_invalid_audio_format():
    # Send tiny payload to trigger validation error
    files = {"audio_file": ("tiny.wav", b"123", "audio/wav")}
    r = client.post("/api/v1/process-audio", files=files)
    assert r.status_code in (400, 500)

