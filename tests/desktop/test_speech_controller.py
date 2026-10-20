from threading import get_ident
import pytest
from PySide6.QtCore import QObject, QThreadPool, Signal
from companion.desktop.speech_controller import SpeechController
from companion.domain.voice import AudioChunk, VoiceErrorCode

class Synth:
    local_only=True
    def __init__(self): self.calls=0; self.audio=None; self.owner=None; self.callback=None
    def synthesize(self,text,token):
        self.calls+=1; self.owner=get_ident()
        if self.callback: self.callback(token)
        self.audio=AudioChunk(bytearray(b'12'*40),24000,1,2)
        return self.audio
class Playback(QObject):
    finished=Signal()
    failed=Signal(object)
    def __init__(self): super().__init__(); self.audio=None; self.plays=0; self.stops=0; self.stop_ok=True; self.callback=None
    def play(self,audio):
        self.plays+=1; self.audio=audio
        if self.callback: self.callback()
    def stop(self):
        self.stops+=1
        if self.audio: self.audio.clear(); self.audio=None
        return self.stop_ok
class Pool:
    def __init__(self): self.workers=[]; self.fail=False
    def start(self,worker):
        if self.fail: raise RuntimeError('private native error')
        self.workers.append(worker)

@pytest.fixture
def speech(qapp):
    synth,player,pool=Synth(),Playback(),Pool()
    controller=SpeechController(synth,player,pool=pool)
    yield controller,synth,player,pool
    import shiboken6
    player.stop_ok=True
    if shiboken6.isValid(controller): controller.close()
    for worker in pool.workers: worker.run()
    qapp.processEvents()

def finish(speech,qapp):
    speech[3].workers[-1].run(); qapp.processEvents()

def test_explicit_synthesis_then_playback_ownership(speech,qapp):
    controller,synth,player,pool=speech
    assert controller.can_speak and not synth.calls and not player.plays
    controller.speak('你好')
    assert controller.state=='synthesizing' and not controller.can_speak
    finish(speech,qapp)
    assert controller.state=='playing' and player.audio is synth.audio
    player.stop(); player.finished.emit()
    assert controller.state=='idle' and controller.can_speak

@pytest.mark.parametrize('method',['cancel','close'])
@pytest.mark.parametrize('when',['queued','complete'])
def test_cancel_or_close_never_plays_late_audio(speech,qapp,method,when):
    controller,synth,player,pool=speech
    controller.speak('你好')
    if when=='complete': pool.workers[-1].run()
    getattr(controller,method)()
    finish(speech,qapp)
    assert player.plays==0
    if synth.audio: assert not synth.audio.pcm
    assert controller.state==('unavailable' if method=='close' else 'idle')

def test_cancel_keeps_worker_reservation_until_completion(speech,qapp):
    controller,synth,player,pool=speech
    controller.speak('你好'); controller.cancel(); controller.speak('new')
    assert len(pool.workers)==1 and not controller.can_speak
    finish(speech,qapp)
    assert controller.can_speak

def test_stop_failure_blocks_capture_outcome_and_new_synthesis(speech,qapp):
    controller,synth,player,pool=speech
    controller.speak('你好'); finish(speech,qapp); player.stop_ok=False
    assert controller.cancel() is False and controller.state=='error' and not controller.can_speak
    controller.speak('another'); assert len(pool.workers)==1
    player.stop_ok=True; assert controller.cancel() is True and controller.can_speak

def test_pool_failure_cleans_job_and_can_retry(speech):
    controller,synth,player,pool=speech; pool.fail=True
    errors=[]; controller.errorOccurred.connect(errors.append)
    controller.speak('你好')
    assert controller.state=='error' and controller.can_speak and not synth.calls
    assert errors==[VoiceErrorCode.SPEECH_FAILED]

def test_state_notification_cancel_before_worker_submission(speech):
    controller,synth,player,pool=speech
    controller.stateChanged.connect(lambda state: controller.cancel() if state=='synthesizing' else None)
    controller.speak('你好')
    assert not pool.workers and not synth.calls and controller.can_speak

def test_state_notification_cancel_before_play(speech,qapp):
    controller,synth,player,pool=speech
    controller.stateChanged.connect(lambda state: controller.cancel() if state=='playing' else None)
    controller.speak('你好'); finish(speech,qapp)
    assert not player.plays and not synth.audio.pcm and controller.can_speak

def test_error_and_preflight_failures_do_not_expose_detail(speech,qapp):
    controller,synth,player,pool=speech
    def fail(token): raise RuntimeError('private path')
    synth.callback=fail; controller.speak('你好'); finish(speech,qapp)
    assert controller.error_code==VoiceErrorCode.SPEECH_FAILED and controller.can_speak
    other=SpeechController(synth,player,preflight=lambda:(_ for _ in ()).throw(RuntimeError('path')),pool=pool)
    other.speak('你好'); assert other.error_code==VoiceErrorCode.NOT_CONFIGURED
    other.close()

def test_real_pool_synthesizes_off_ui_thread(speech,qapp,qtbot):
    controller,synth,player,pool=speech; controller._pool=QThreadPool()
    controller.speak('你好')
    qtbot.waitUntil(lambda:player.plays==1,timeout=3000)
    assert synth.owner!=get_ident()
    controller._pool.waitForDone(3000)

def test_synchronous_playback_finish_leaves_idle(speech,qapp):
    controller,synth,player,pool=speech
    player.callback=lambda:(player.stop(),player.finished.emit())
    controller.speak('你好'); finish(speech,qapp)
    assert controller.state=='idle' and controller.can_speak


def test_destroyed_controller_clears_completed_result_before_queued_delivery(speech,qapp):
    import shiboken6
    controller,synth,player,pool=speech
    controller.speak('你好'); pool.workers[-1].run()
    assert synth.audio.pcm
    shiboken6.delete(controller)
    assert not synth.audio.pcm and not player.plays
    # Fixture cannot call methods on this deleted QObject.
    speech[0]._closed=True

def test_playback_error_stops_output_and_can_retry(speech,qapp):
    controller,synth,player,pool=speech
    controller.speak('你好'); finish(speech,qapp)
    player.failed.emit(VoiceErrorCode.SPEECH_FAILED)
    assert not synth.audio.pcm and controller.error_code==VoiceErrorCode.SPEECH_FAILED
    assert controller.can_speak


def test_destroy_on_playing_notification_never_starts_output(speech,qapp):
    import shiboken6
    controller,synth,player,pool=speech
    def destroy(state):
        if state=='playing': shiboken6.delete(controller)
    controller.stateChanged.connect(destroy)
    controller.speak('你好'); pool.workers[-1].run(); qapp.processEvents()
    assert not player.plays and not synth.audio.pcm


def test_destroyed_playing_controller_stops_independent_output(speech,qapp):
    import shiboken6
    controller,synth,player,pool=speech
    controller.speak('你好'); finish(speech,qapp)
    before=player.stops
    shiboken6.delete(controller)
    assert player.stops==before+1 and not synth.audio.pcm
