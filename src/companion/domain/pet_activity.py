"""Ephemeral visual activity derived only from explicit voice operations."""
from enum import Enum


class PetActivity(str, Enum):
    IDLE = 'idle'
    LISTENING = 'listening'
    PROCESSING = 'processing'
    SPEAKING = 'speaking'


def pet_activity(voice_state: str | None, speech_state: str | None) -> PetActivity:
    if voice_state == 'listening':
        return PetActivity.LISTENING
    if speech_state == 'playing':
        return PetActivity.SPEAKING
    if voice_state == 'transcribing' or speech_state == 'synthesizing':
        return PetActivity.PROCESSING
    return PetActivity.IDLE
