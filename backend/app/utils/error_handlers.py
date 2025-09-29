"""
Custom exception types for services and audio processing
"""


class WhisperServiceError(Exception):
    pass


class QwenServiceError(Exception):
    pass


class TTSServiceError(Exception):
    pass


class InvalidAudioFormatError(Exception):
    pass


