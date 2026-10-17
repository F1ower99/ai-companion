import pytest

from companion.application.voice_session import VoiceSession
from companion.domain.errors import ValidationError
from companion.domain.voice import (
    AudioChunk, VoiceErrorCode, VoiceOperationError, VoiceState, VoiceTranscript,
)


class Capture:
    def __init__(self):
        self.events = []
        self.audio = AudioChunk(bytearray(b'private!'), 8, 1, 1)
        self.failure = None

    def start(self):
        self.events.append('start')
        if self.failure:
            raise self.failure

    def stop(self):
        self.events.append('stop')
        if self.failure:
            raise self.failure
        return self.audio

    def cancel(self):
        self.events.append('cancel')
        self.audio.clear()


class STT:
    local_only = True

    def __init__(self):
        self.calls = 0
        self.callback = None

    def transcribe(self, audio, cancellation_token):
        self.calls += 1
        assert audio.pcm == bytearray(b'private!')
        if self.callback:
            return self.callback(cancellation_token)
        return VoiceTranscript('背单词')


class TTS:
    local_only = True

    def __init__(self):
        self.text = None
        self.stops = 0
        self.callback = None

    def speak(self, text, cancellation_token):
        self.text = text
        if self.callback:
            self.callback(cancellation_token)

    def stop(self):
        self.stops += 1


def configured():
    capture, stt, tts = Capture(), STT(), TTS()
    return VoiceSession(capture, stt, tts), capture, stt, tts


def test_unconfigured_voice_stays_unavailable():
    session = VoiceSession()
    assert not session.can_capture and not session.can_speak
    assert session.start_push_to_talk().state is VoiceState.UNAVAILABLE
    assert session.stop_capture() is None
    assert session.speak('hello').error_code is VoiceErrorCode.NOT_CONFIGURED


@pytest.mark.parametrize('local_only', [False, None, 1, 'true'])
@pytest.mark.parametrize('kind', ['stt', 'tts'])
def test_nonlocal_or_malformed_provider_is_rejected(local_only, kind):
    provider = STT() if kind == 'stt' else TTS()
    provider.local_only = local_only
    with pytest.raises(ValidationError):
        VoiceSession(**{kind: provider})


def test_stop_releases_capture_then_returns_transcript_and_clears_pcm():
    session, capture, stt, _ = configured()
    assert session.start_push_to_talk().state is VoiceState.LISTENING
    stt.callback = lambda token: (
        VoiceTranscript('背单词') if capture.events == ['start', 'stop'] else None
    )
    assert session.stop_capture().text == '背单词'
    assert session.status.state is VoiceState.TRANSCRIPT_READY
    assert capture.audio.pcm == bytearray()


def test_cancel_discards_audio_without_transcription():
    session, capture, stt, _ = configured()
    session.start_push_to_talk()
    assert session.cancel_capture().state is VoiceState.IDLE
    assert session.stop_capture() is None
    assert stt.calls == 0
    assert capture.audio.pcm == bytearray()


def test_cancel_during_transcription_discards_late_result_and_blocks_overlap():
    session, capture, stt, _ = configured()
    session.start_push_to_talk()

    def cancel(token):
        session.cancel_capture()
        assert token.is_cancelled()
        assert session.start_push_to_talk().error_code is VoiceErrorCode.BUSY
        return VoiceTranscript('late private transcript')

    stt.callback = cancel
    assert session.stop_capture() is None
    assert session.status.state is VoiceState.IDLE
    assert capture.audio.pcm == bytearray()


@pytest.mark.parametrize('failure,code', [
    (RuntimeError('private device detail'), VoiceErrorCode.CAPTURE_FAILED),
    (VoiceOperationError(VoiceErrorCode.PERMISSION_DENIED), VoiceErrorCode.PERMISSION_DENIED),
])
def test_failed_start_releases_capture_with_safe_error(failure, code):
    session, capture, _, _ = configured()
    capture.failure = failure
    result = session.start_push_to_talk()
    assert result.state is VoiceState.ERROR
    assert result.error_code is code
    assert capture.events[-1] == 'cancel'
    assert capture.audio.pcm == bytearray()
    assert 'private' not in repr(result)


def test_failed_stop_releases_capture():
    session, capture, stt, _ = configured()
    session.start_push_to_talk()
    capture.failure = RuntimeError('private capture error')
    assert session.stop_capture() is None
    assert session.status.error_code is VoiceErrorCode.CAPTURE_FAILED
    assert stt.calls == 0
    assert capture.audio.pcm == bytearray()


@pytest.mark.parametrize('result', [None, 'unexpected raw text'])
def test_bad_stt_response_is_safe_and_audio_is_cleared(result):
    session, capture, stt, _ = configured()
    stt.callback = lambda token: result
    session.start_push_to_talk()
    assert session.stop_capture() is None
    assert session.status.error_code is VoiceErrorCode.TRANSCRIPTION_FAILED
    assert capture.audio.pcm == bytearray()


def test_stt_exception_does_not_expose_private_detail():
    session, capture, stt, _ = configured()

    def fail(token):
        raise RuntimeError('private transcript')

    stt.callback = fail
    session.start_push_to_talk()
    assert session.stop_capture() is None
    assert session.status.error_code is VoiceErrorCode.TRANSCRIPTION_FAILED
    assert capture.audio.pcm == bytearray()


def test_push_to_talk_interrupts_speech_and_late_speech_completion_cannot_reset_it():
    session, capture, _, tts = configured()

    def interrupt(token):
        assert session.start_push_to_talk().state is VoiceState.LISTENING
        assert token.is_cancelled()

    tts.callback = interrupt
    session.speak('assistant text')
    assert tts.stops >= 1
    assert capture.events == ['start']
    assert session.status.state is VoiceState.LISTENING


def test_speech_failure_preserves_text_and_has_safe_status():
    session, _, _, tts = configured()
    text = 'assistant reply remains intact'

    def fail(token):
        raise RuntimeError('private voice detail')

    tts.callback = fail
    assert session.speak(text).error_code is VoiceErrorCode.SPEECH_FAILED
    assert text == 'assistant reply remains intact'


def test_duplicate_start_does_not_start_another_capture():
    session, capture, _, _ = configured()
    session.start_push_to_talk()
    assert session.start_push_to_talk().error_code is VoiceErrorCode.BUSY
    assert capture.events == ['start']
    assert session.speak('hello').error_code is VoiceErrorCode.BUSY


def test_close_cleans_up_and_permanently_disables_session():
    session, capture, stt, _ = configured()
    session.start_push_to_talk()
    session.close()
    assert capture.audio.pcm == bytearray()
    assert stt.calls == 0
    assert not session.can_capture and not session.can_speak
    assert session.start_push_to_talk().state is VoiceState.UNAVAILABLE


def test_capture_can_recover_after_a_completed_speech_failure():
    session, capture, _, tts = configured()
    tts.callback = lambda token: (_ for _ in ()).throw(RuntimeError('speech failed'))
    session.speak('hello')
    assert session.start_push_to_talk().state is VoiceState.LISTENING
    assert capture.events == ['start']


def test_new_capture_cannot_overlap_cancel_cleanup():
    session, capture, _, _ = configured()
    session.start_push_to_talk()
    original_cancel = capture.cancel

    def cancel():
        assert session.start_push_to_talk().error_code is VoiceErrorCode.BUSY
        original_cancel()

    capture.cancel = cancel
    session.cancel_capture()
    assert session.status.state is VoiceState.IDLE
