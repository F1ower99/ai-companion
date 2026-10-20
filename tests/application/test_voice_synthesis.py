from threading import Event, Thread
import pytest
from companion.application.voice_synthesis import SynthesisJob
from companion.domain.voice import AudioChunk, VoiceErrorCode, VoiceOperationError

class Synth:
    local_only = True
    def __init__(self):
        self.calls = 0
        self.audio = AudioChunk(bytearray(b"\x01\x02" * 10), 24000, 1, 2)
        self.callback = None
    def synthesize(self, text, token):
        self.calls += 1
        if self.callback: self.callback(token)
        return self.audio

def test_single_use_and_explicit_ownership_transfer():
    synth = Synth(); job = SynthesisJob(synth, '你好')
    assert job.take_audio() is None
    assert job.run() is None and job.run() is None and synth.calls == 1
    assert job.take_audio() is synth.audio and job.take_audio() is None
    job.cancel()
    assert synth.audio.pcm
    synth.audio.clear()

@pytest.mark.parametrize('when', ['pending', 'completed'])
def test_cancel_clears_or_prevents_owned_result(when):
    synth = Synth(); job = SynthesisJob(synth, '你好')
    if when == 'completed': job.run()
    job.cancel(); job.run()
    assert job.take_audio() is None
    assert synth.calls == (1 if when == 'completed' else 0)
    if when == 'completed': assert not synth.audio.pcm

def test_running_cancel_does_not_mutate_provider_buffer_but_rejects_result():
    synth = Synth(); entered, resume = Event(), Event()
    def block(token):
        entered.set(); assert resume.wait(3)
        assert token.is_cancelled() and synth.audio.pcm
    synth.callback = block
    job = SynthesisJob(synth, '你好'); worker = Thread(target=job.run)
    worker.start(); assert entered.wait(3)
    job.cancel(); assert synth.audio.pcm
    resume.set(); worker.join(3)
    assert not worker.is_alive() and not synth.audio.pcm and job.take_audio() is None

def test_provider_error_is_sanitized_and_job_not_retryable():
    synth = Synth()
    def fail(token): raise RuntimeError('private text/path')
    synth.callback = fail; job = SynthesisJob(synth, '你好')
    with pytest.raises(VoiceOperationError) as error: job.run()
    assert error.value.code == VoiceErrorCode.SPEECH_FAILED
    assert 'private' not in str(error.value)
    assert job.run() is None and job.take_audio() is None and synth.calls == 1

@pytest.mark.parametrize('local', [False, 1, None])
def test_only_explicit_local_backend_allowed(local):
    synth = Synth(); synth.local_only = local
    with pytest.raises(VoiceOperationError): SynthesisJob(synth, '你好')
