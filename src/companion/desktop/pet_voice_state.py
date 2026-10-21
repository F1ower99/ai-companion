"""Render existing voice state on the character; never control a device."""
from PySide6.QtCore import QObject, Slot

from companion.domain.pet_activity import pet_activity


class PetVoiceStateBridge(QObject):
    def __init__(self, pet, voice=None, speech=None):
        super().__init__(pet)
        self._pet, self._voice, self._speech = pet, voice, speech
        self._closed = False
        pet.destroyed.connect(self._detach)
        if voice is not None:
            voice.stateChanged.connect(self._refresh)
            voice.destroyed.connect(self._voice_destroyed)
        if speech is not None:
            speech.stateChanged.connect(self._refresh)
            speech.destroyed.connect(self._speech_destroyed)
        self._refresh()

    @Slot()
    @Slot(str)
    def _refresh(self, *_args):
        if self._closed:
            return
        self._pet.set_activity(pet_activity(
            getattr(self._voice, 'state', None), getattr(self._speech, 'state', None),
        ))

    @Slot()
    def _voice_destroyed(self):
        self._voice = None
        self._refresh()

    @Slot()
    def _speech_destroyed(self):
        self._speech = None
        self._refresh()

    @Slot()
    def _detach(self):
        if self._closed:
            return
        self._closed = True
        for controller, destroyed_slot in (
            (self._voice, self._voice_destroyed), (self._speech, self._speech_destroyed),
        ):
            if controller is not None:
                controller.stateChanged.disconnect(self._refresh)
                controller.destroyed.disconnect(destroyed_slot)
        # Release source wrappers before Qt destroys this child renderer.
        self._voice = self._speech = self._pet = None
