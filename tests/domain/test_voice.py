import pytest

from companion.domain.errors import ValidationError
from companion.domain.voice import AudioChunk, VoiceTranscript


def test_pcm_duration_boundary_and_explicit_clear():
    pcm = bytearray(120)
    audio = AudioChunk(pcm, sample_rate_hz=1, channels=1, sample_width_bytes=2)
    assert audio.duration_seconds == 60
    audio.clear()
    assert pcm == bytearray()


@pytest.mark.parametrize('pcm,rate,channels,width', [
    (b'ab', 1, 1, 2), (bytearray(), 1, 1, 2),
    (bytearray(2), 0, 1, 2), (bytearray(2), True, 1, 2),
    (bytearray(2), 1, 0, 2), (bytearray(2), 1, 1, 0),
    (bytearray(3), 1, 1, 2), (bytearray(122), 1, 1, 2),
])
def test_invalid_pcm_is_rejected(pcm, rate, channels, width):
    with pytest.raises(ValidationError):
        AudioChunk(pcm, rate, channels, width)


def test_voice_content_is_excluded_from_repr():
    assert 'private' not in repr(AudioChunk(bytearray(b'private!'), 8, 1, 1))
    assert 'private' not in repr(VoiceTranscript('private'))


def test_cleanup_erases_pcm_even_if_provider_retains_a_memoryview():
    audio = AudioChunk(bytearray(b'private!'), 8, 1, 1)
    retained = memoryview(audio.pcm)
    audio.clear()
    assert retained.tobytes() == bytes(8)
    retained.release()


def test_transcript_is_trimmed_and_fits_chat_composer_limit():
    assert VoiceTranscript(' hello ').text == 'hello'
    assert len(VoiceTranscript('x' * 8000).text) == 8000


@pytest.mark.parametrize('text', ['', '  ', 'x' * 8001, None])
def test_invalid_transcript_is_rejected(text):
    with pytest.raises(ValidationError):
        VoiceTranscript(text)
