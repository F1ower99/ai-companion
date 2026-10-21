"""Privacy boundary tests with real controllers and public, fake device data."""
import pytest

from companion.application.voice_session import VoiceSession
from companion.desktop.voice_controller import VoiceController
from companion.desktop.speech_controller import SpeechController
from test_chat_window import (
    FakeChatService, FakeSpeechController, FakeVoiceController, add_reply, make_window,
)
from test_speech_controller import Synth, Playback, Pool
from test_voice_controller import Capture, STT, Permission


@pytest.mark.parametrize('phase', ['queued', 'result_queued', 'playing'])
def test_clear_cancels_speech_and_discards_old_audio(qtbot, qapp, phase):
    synth, player, pool = Synth(), Playback(), Pool()
    speech = SpeechController(synth, player, pool=pool)
    service = FakeChatService(); add_reply(service, '公开的测试回复')
    window, _ = make_window(qtbot, service, speech_controller=speech,
                            confirmation_handler=lambda _: True)
    window.speak_reply_button.click()
    if phase != 'queued':
        pool.workers[-1].run()
    if phase == 'playing':
        qapp.processEvents()
        assert player.plays == 1
    plays_before = player.plays
    window.clear_conversation()
    if phase == 'queued':
        pool.workers[-1].run()
    qapp.processEvents()
    assert service.clear_calls == ['conversation-1']
    assert player.plays == plays_before and player.audio is None
    assert synth.audio is None or not synth.audio.pcm
    assert not window.speak_reply_button.isEnabled()
    speech.close()


@pytest.mark.parametrize('phase', ['permission', 'transcribing', 'result_queued'])
def test_clear_invalidates_pending_capture_and_transcript(qtbot, qapp, phase):
    capture, stt, permission, pool = Capture(), STT(), Permission(), Pool()
    voice = VoiceController(VoiceSession(capture, stt), capture,
                            permission_requester=permission, pool=pool)
    window, service = make_window(qtbot, voice_controller=voice,
                                  confirmation_handler=lambda _: True)
    voice.press()
    if phase != 'permission':
        permission.callbacks[-1](True)
        voice.release()
    if phase == 'result_queued':
        pool.workers[-1].run()
    window.composer.setPlainText('公开的旧草稿')
    window.clear_conversation()
    if phase == 'permission':
        permission.callbacks[-1](True)
        assert capture.starts == 0
    elif phase == 'transcribing':
        pool.workers[-1].run()
    qapp.processEvents()
    assert service.clear_calls == ['conversation-1']
    assert window.composer.toPlainText() == '' and service.send_calls == []
    if capture.last_audio is not None:
        assert not capture.last_audio.pcm
    voice.close()


@pytest.mark.parametrize('blocked_by', ['declined', 'busy'])
def test_unconfirmed_clear_does_not_cancel_voice(qtbot, blocked_by):
    voice, speech = FakeVoiceController(), FakeSpeechController()
    window, service = make_window(qtbot, voice_controller=voice, speech_controller=speech,
                                  confirmation_handler=lambda _: blocked_by != 'declined')
    window.is_busy = blocked_by == 'busy'
    window.clear_conversation()
    assert service.clear_calls == [] and voice.cancels == speech.cancels == 0


@pytest.mark.parametrize('failure', ['false', 'speech_exception', 'voice_exception'])
def test_failed_voice_stop_attempts_both_and_does_not_claim_clear(qtbot, failure):
    voice, speech = FakeVoiceController(), FakeSpeechController()
    service = FakeChatService(); add_reply(service, '公开回复')
    window, _ = make_window(qtbot, service, voice_controller=voice, speech_controller=speech,
                            confirmation_handler=lambda _: True)
    attempts = []
    def stop_speech():
        attempts.append('speech')
        if failure == 'speech_exception':
            raise RuntimeError('private device details')
        return failure != 'false'
    def stop_voice():
        attempts.append('voice')
        if failure == 'voice_exception':
            raise RuntimeError('private capture details')
    speech.cancel, voice.cancel = stop_speech, stop_voice
    try:
        window.clear_conversation()
        assert attempts == ['speech', 'voice'] and service.clear_calls == []
        assert service.messages and 'private' not in window.status_label.text()
        assert '停止' in window.status_label.text()
    finally:
        # Restore safe cleanup handlers even when an assertion fails.
        speech.cancel, voice.cancel = lambda: True, lambda: None


def test_storage_failure_keeps_messages_after_voice_has_been_cancelled(qtbot):
    voice, speech = FakeVoiceController(), FakeSpeechController()
    service = FakeChatService(); add_reply(service, '公开回复')
    window, _ = make_window(qtbot, service, voice_controller=voice, speech_controller=speech,
                            confirmation_handler=lambda _: True)
    def fail_clear(_conversation_id):
        raise RuntimeError('private database path')
    service.clear = fail_clear
    window.composer.setPlainText('公开草稿')
    window.clear_conversation()
    assert voice.cancels == speech.cancels == 1 and service.messages
    assert window.composer.toPlainText() == '公开草稿'
    assert '未能清空' in window.status_label.text() and 'private' not in window.status_label.text()
