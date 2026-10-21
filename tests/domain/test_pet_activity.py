import pytest

from companion.domain.pet_activity import PetActivity, pet_activity


@pytest.mark.parametrize('voice,speech,expected', [
    (None, None, PetActivity.IDLE),
    ('listening', 'playing', PetActivity.LISTENING),
    ('transcribing', 'playing', PetActivity.SPEAKING),
    ('transcribing', 'idle', PetActivity.PROCESSING),
    ('idle', 'synthesizing', PetActivity.PROCESSING),
    ('permission', 'idle', PetActivity.IDLE),
    ('cancelling', 'cancelling', PetActivity.IDLE),
    ('error', 'error', PetActivity.IDLE),
    ('unknown', 'unavailable', PetActivity.IDLE),
])
def test_only_actual_voice_work_drives_pet(voice, speech, expected):
    assert pet_activity(voice, speech) is expected
