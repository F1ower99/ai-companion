import struct
import wave

import pytest

from companion.domain.voice import VoiceOperationError, VoiceTranscript
from test_third_party_notices import load_script


def wav_file(tmp_path, *, rate=16000, channels=1, width=2):
    path = tmp_path / 'input.wav'
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(channels)
        output.setsampwidth(width)
        output.setframerate(rate)
        output.writeframes(bytes([1]) * channels * width * 8)
    return path


def test_valid_wav_stays_bounded_pcm(tmp_path):
    module = load_script('smoke_local_stt')
    value = module.read_pcm_wav(wav_file(tmp_path))
    assert (value.sample_rate_hz, value.channels, value.sample_width_bytes) == (16000, 1, 2)
    assert len(value.pcm) == 16


@pytest.mark.parametrize('rate,channels,width', [(8000, 1, 2), (16000, 2, 2), (16000, 1, 1)])
def test_wrong_wav_format_is_rejected(tmp_path, rate, channels, width):
    module = load_script('smoke_local_stt')
    with pytest.raises(VoiceOperationError):
        module.read_pcm_wav(wav_file(tmp_path, rate=rate, channels=channels, width=width))


@pytest.mark.parametrize('size,payload', [(1920002, b''), (4, b'\x01\x00'), (0, b'')])
def test_oversized_or_truncated_wav_header_is_rejected(tmp_path, size, payload):
    module = load_script('smoke_local_stt')
    path = tmp_path / 'bad.wav'
    path.write_bytes(struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 36 + size, b'WAVE', b'fmt ', 16, 1, 1, 16000, 32000, 2, 16, b'data', size) + payload)
    with pytest.raises(VoiceOperationError):
        module.read_pcm_wav(path)


@pytest.mark.parametrize('size', [1, 3, 17])
def test_partial_pcm_frame_is_not_silently_discarded(tmp_path, size):
    module = load_script('smoke_local_stt')
    path = tmp_path / 'partial-frame.wav'
    path.write_bytes(struct.pack(
        '<4sI4s4sIHHIIHH4sI', b'RIFF', 36 + size, b'WAVE', b'fmt ',
        16, 1, 1, 16000, 32000, 2, 16, b'data', size,
    ) + bytes(size))
    with pytest.raises(VoiceOperationError):
        module.read_pcm_wav(path)


@pytest.mark.parametrize('fail', [False, True])
def test_cli_clears_audio_and_never_prints_transcript_or_backend_errors_by_default(tmp_path, capsys, fail):
    module = load_script('smoke_local_stt')
    seen = []
    class Provider:
        def transcribe(self, audio, token):
            seen.append(audio)
            if fail:
                raise RuntimeError('private input file detail')
            return VoiceTranscript('private transcript')
    code = module.main(['--model-dir', str(tmp_path), '--wav', str(wav_file(tmp_path))], provider_factory=lambda *a, **kw: Provider())
    output = capsys.readouterr()
    assert code == (1 if fail else 0)
    assert 'private' not in output.out + output.err
    assert seen[0].pcm == bytearray()
