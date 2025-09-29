import pytest
from app.services.qwen_service import QwenService
from app.services.whisper_service import WhisperService
from app.services.tts_service import TTSService


@pytest.mark.asyncio
async def test_tts_empty_text():
    tts = TTSService()
    with pytest.raises(Exception):
        await tts.synthesize_speech("")


def test_qwen_init():
    svc = QwenService()
    assert hasattr(svc, 'client')


def test_whisper_init():
    svc = WhisperService()
    assert hasattr(svc, 'client')

