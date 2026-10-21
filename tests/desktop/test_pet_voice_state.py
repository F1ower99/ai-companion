import pytest
from PySide6.QtCore import QObject, Signal
import shiboken6
import gc
import weakref

from companion.desktop.chat_window import ChatWindow
from companion.desktop.pet_window import PetWindow
from companion.desktop.pet_voice_state import PetVoiceStateBridge
from companion.domain.pet_activity import PetActivity


class Controller(QObject):
    stateChanged = Signal(str)
    def __init__(self, state='idle'):
        super().__init__(); self.state = state
    def change(self, state):
        self.state = state; self.stateChanged.emit(state)


@pytest.fixture
def pet(qtbot):
    chat = ChatWindow(); pet = PetWindow(chat)
    qtbot.addWidget(chat); qtbot.addWidget(pet); pet.show()
    return pet


def test_idle_pet_has_no_animation_and_active_cues_do_not_move_or_focus(pet, qapp):
    assert pet.activity is PetActivity.IDLE and not pet.animation_timer.isActive()
    geometry, flags = pet.geometry(), pet.windowFlags()
    idle = pet.grab().toImage()
    pet.set_activity(PetActivity.SPEAKING)
    assert pet.animation_timer.isActive() and '朗读' in pet.toolTip()
    active = pet.grab().toImage()
    pet._animate(); qapp.processEvents()
    assert active != pet.grab().toImage() and idle != active
    assert pet.geometry() == geometry and pet.windowFlags() == flags
    assert not pet.chat_window.isVisible()
    pet.set_activity(PetActivity.IDLE)
    assert not pet.animation_timer.isActive() and pet.grab().toImage() == idle


def test_hidden_pet_stops_visual_work_and_resumes_only_active_state(pet):
    pet.set_activity(PetActivity.LISTENING)
    assert pet.animation_timer.isActive()
    pet.hide(); assert not pet.animation_timer.isActive()
    pet.set_activity(PetActivity.PROCESSING)
    assert not pet.animation_timer.isActive()
    pet.show(); assert pet.animation_timer.isActive()
    pet.hide(); pet.set_activity(PetActivity.IDLE); pet.show()
    assert not pet.animation_timer.isActive()


def test_bridge_reflects_existing_and_live_controller_state_without_commands(pet):
    voice, speech = Controller('permission'), Controller('synthesizing')
    bridge = PetVoiceStateBridge(pet, voice, speech)
    assert pet.activity is PetActivity.PROCESSING
    voice.change('listening'); assert pet.activity is PetActivity.LISTENING
    voice.change('transcribing'); speech.change('playing')
    assert pet.activity is PetActivity.SPEAKING
    speech.change('cancelling'); assert pet.activity is PetActivity.PROCESSING
    voice.change('cancelling'); assert pet.activity is PetActivity.IDLE
    voice.change('error'); speech.change('error')
    assert pet.activity is PetActivity.IDLE and not pet.animation_timer.isActive()
    assert bridge.parent() is pet


def test_destroyed_controller_cannot_leave_pet_recording_or_playing(pet):
    voice, speech = Controller('listening'), Controller('playing')
    bridge = PetVoiceStateBridge(pet, voice, speech)
    assert pet.activity is PetActivity.LISTENING
    shiboken6.delete(voice); assert pet.activity is PetActivity.SPEAKING
    shiboken6.delete(speech); assert pet.activity is PetActivity.IDLE
    assert not pet.animation_timer.isActive()


def test_absent_controllers_leave_idle(pet):
    bridge = PetVoiceStateBridge(pet)
    assert pet.activity is PetActivity.IDLE and not pet.animation_timer.isActive()
    assert bridge.parent() is pet


def test_destroying_pet_disconnects_late_controller_signals(qtbot):
    # This test owns/deletes the pet itself; qtbot must not close it again.
    chat = ChatWindow(); qtbot.addWidget(chat)
    pet = PetWindow(chat); pet.show()
    voice, speech = Controller(), Controller()
    bridge = PetVoiceStateBridge(pet, voice, speech)
    shiboken6.delete(pet)
    assert not shiboken6.isValid(bridge)
    voice.change('listening')
    speech.change('playing')


def test_destroyed_pet_releases_bridge_controller_references(qtbot):
    chat = ChatWindow(); qtbot.addWidget(chat)
    pet = PetWindow(chat)
    voice = Controller('listening'); reference = weakref.ref(voice)
    bridge = PetVoiceStateBridge(pet, voice)
    del voice
    shiboken6.delete(pet)
    gc.collect()
    assert reference() is None
