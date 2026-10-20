from threading import Thread
from types import SimpleNamespace
import pytest
from PySide6.QtCore import QObject, Signal
from companion.domain.voice import AudioChunk, VoiceOperationError
from companion.infrastructure.qt_playback import QtAudioPlayback, QtAudioOutput

class Driver(QObject):
    finished = Signal()
    failed = Signal()
    def __init__(self, parent):
        super().__init__(parent)
        self.starts = self.stops = 0
        self.fail_start = self.fail_stop = False
        self.on_start = None
    def start(self, audio):
        self.starts += 1
        if self.on_start: self.on_start()
        if self.fail_start: raise RuntimeError('private device path')
    def stop(self):
        self.stops += 1
        if self.fail_stop: raise RuntimeError('device failure')

@pytest.fixture
def playback(qapp):
    drivers = []
    def factory(parent):
        driver=Driver(parent); drivers.append(driver); return driver
    player=QtAudioPlayback(backend_factory=factory)
    yield player, drivers
    for driver in drivers: driver.fail_stop=False
    import shiboken6
    if shiboken6.isValid(player): player.stop()

def audio(): return AudioChunk(bytearray(b'\x01\x02' * 40),24000,1,2)

def test_lazy_start_finish_and_repeat_stop_clear_owned_audio(playback):
    player, drivers=playback
    assert not drivers
    result=audio(); player.play(result)
    assert drivers[0].starts == 1 and result.pcm
    drivers[0].finished.emit()
    assert not result.pcm and player.stop() is True

@pytest.mark.parametrize('fmt',[(16000,1,2),(24000,2,2),(24000,1,1)])
def test_reject_format_without_device_query_and_clear(playback, fmt):
    player, drivers=playback
    result=AudioChunk(bytearray(b'1234'),*fmt)
    with pytest.raises(VoiceOperationError): player.play(result)
    assert not drivers and not result.pcm

def test_start_failure_is_safe_and_clears(qapp):
    result=audio()
    def factory(parent):
        driver=Driver(parent); driver.fail_start=True; return driver
    player=QtAudioPlayback(backend_factory=factory)
    with pytest.raises(VoiceOperationError) as error: player.play(result)
    assert 'private' not in str(error.value) and not result.pcm
    assert player.stop()

def test_stop_failure_returns_false_retains_retry_and_blocks_new_output(playback):
    player, drivers=playback
    result=audio(); player.play(result); drivers[0].fail_stop=True
    assert player.stop() is False and not result.pcm
    newer=audio()
    with pytest.raises(VoiceOperationError): player.play(newer)
    assert not newer.pcm and len(drivers)==1
    drivers[0].fail_stop=False
    assert player.stop() is True

def test_stale_failure_does_not_stop_new_playback(playback):
    player, drivers=playback
    player.play(audio()); old=drivers[0]
    player.stop(); result=audio(); player.play(result)
    old.failed.emit(); old.finished.emit()
    assert result.pcm and drivers[1].stops==0

def test_sync_finish_and_reentrant_new_play_survive(qapp):
    drivers=[]
    def factory(parent):
        driver=Driver(parent); drivers.append(driver)
        if len(drivers)==1: driver.on_start=driver.finished.emit
        return driver
    player=QtAudioPlayback(backend_factory=factory)
    newer=audio(); player.finished.connect(lambda: player.play(newer))
    first=audio(); player.play(first)
    assert not first.pcm and newer.pcm and len(drivers)==2
    player.stop()

def test_wrong_thread_never_queries_device(playback):
    player, drivers=playback; errors=[]; result=audio()
    def run():
        try: player.play(result)
        except VoiceOperationError as e: errors.append(e)
    thread=Thread(target=run); thread.start(); thread.join(2)
    assert errors and not drivers
    result.clear()

class Format:
    SampleFormat=SimpleNamespace(Int16=16)
    def setSampleRate(self,v): self.rate=v
    def setChannelCount(self,v): self.channels=v
    def setSampleFormat(self,v): self.format=v
class Sink(QObject):
    stateChanged=Signal(object)
    def __init__(self,device,fmt,parent):
        super().__init__(parent); self.fmt=fmt; self.resets=0; self.err=0
    def setBufferSize(self,v): pass
    def start(self,source): self.source=source
    def error(self): return self.err
    def reset(self): self.resets+=1

def native_module(*,null=False,supported=True):
    calls=[]; sinks=[]
    device=SimpleNamespace(isNull=lambda:null,isFormatSupported=lambda fmt:supported)
    def discover(): calls.append('device'); return device
    def sink(*args):
        instance=Sink(*args); sinks.append(instance); return instance
    return SimpleNamespace(QAudioFormat=Format,QAudioSink=sink,
        QMediaDevices=SimpleNamespace(defaultAudioOutput=discover),
        QtAudio=SimpleNamespace(Error=SimpleNamespace(NoError=0),State=SimpleNamespace(IdleState=2))),calls,sinks

@pytest.mark.parametrize('null,supported',[(True,True),(False,False)])
def test_native_missing_or_unsupported_device_safe(qapp,null,supported):
    module,calls,sinks=native_module(null=null,supported=supported)
    driver=QtAudioOutput(multimedia_loader=lambda:module)
    assert not calls
    with pytest.raises(VoiceOperationError): driver.start(audio())
    assert calls==['device'] and not sinks
    driver.stop()

def test_native_memory_buffer_format_finish_and_reset(qapp):
    module,calls,sinks=native_module(); driver=QtAudioOutput(multimedia_loader=lambda:module)
    done=[]; driver.finished.connect(lambda:done.append(True))
    result=audio(); driver.start(result)
    sink=sinks[0]
    assert (sink.fmt.rate,sink.fmt.channels,sink.fmt.format)==(24000,1,16)
    assert sink.source.readAll().data()==bytes(result.pcm)
    sink.stateChanged.emit(2)
    assert done==[True]
    driver.stop(); assert sink.resets==1
    result.clear()


def test_native_reset_failure_can_be_retried(qapp):
    module,calls,sinks=native_module(); driver=QtAudioOutput(multimedia_loader=lambda:module)
    result=audio(); driver.start(result); sink=sinks[0]
    reset=sink.reset
    def fail(): raise RuntimeError('reset failed')
    sink.reset=fail
    with pytest.raises(RuntimeError): driver.stop()
    sink.reset=reset
    driver.stop()
    assert sink.resets==1
    result.clear()

def test_playback_deadline_is_failure_and_clears(playback):
    player,drivers=playback; failures=[]
    player.failed.connect(failures.append)
    result=audio(); player.play(result)
    player._resources.timer.timeout.emit()
    assert failures and not result.pcm and drivers[0].stops==1


def test_destroyed_playback_stops_driver_and_clears_owned_pcm(playback):
    import shiboken6
    player,drivers=playback; result=audio(); player.play(result)
    shiboken6.delete(player)
    assert drivers[0].stops==1 and not result.pcm
