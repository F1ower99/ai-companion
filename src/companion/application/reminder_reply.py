"""Narrow complete-utterance reminder proposals; never schedules or executes."""
from dataclasses import dataclass
import re
import unicodedata

from companion.domain.errors import ValidationError
from companion.domain.reminders import ReminderAction


def _unsupported():
    raise ValidationError('Unsupported reminder reply.')


@dataclass(frozen=True)
class ParsedReminderReply:
    action: ReminderAction
    minutes: int | None = None

    def __post_init__(self):
        if not isinstance(self.action, ReminderAction) or self.action is ReminderAction.CLOSE:
            _unsupported()
        if self.action is ReminderAction.EXTEND:
            if type(self.minutes) is not int or not 1 <= self.minutes <= 120:
                _unsupported()
        elif self.minutes is not None:
            _unsupported()


def _number_word(number):
    digits = '零一二三四五六七八九'
    if number < 10:
        return digits[number]
    if number < 100:
        tens, ones = divmod(number, 10)
        return (digits[tens] if tens > 1 else '') + '十' + (digits[ones] if ones else '')
    if number == 100:
        return '一百'
    if number < 110:
        return '一百零' + digits[number - 100]
    tens, ones = divmod(number - 100, 10)
    return '一百' + digits[tens] + '十' + (digits[ones] if ones else '')


_MINUTE_WORDS = {_number_word(number): number for number in range(1, 121)}
_MINUTE_WORDS['两'] = 2
_HOURS = {
    '半小时': 30, '半个小时': 30, '0.5小时': 30,
    '一小时': 60, '一个小时': 60, '1小时': 60, '1个小时': 60,
    '一个半小时': 90, '一小时半': 90, '1.5小时': 90,
    '两小时': 120, '两个小时': 120, '二小时': 120, '2小时': 120, '2个小时': 120,
}
_ACTIONS = {
    '现在做': ReminderAction.NOW, '现在就做': ReminderAction.NOW, '马上做': ReminderAction.NOW,
    '稍后': ReminderAction.LATER, '稍后提醒': ReminderAction.LATER,
    '今天跳过': ReminderAction.SKIP_TODAY,
    '已完成': ReminderAction.DONE, '完成了': ReminderAction.DONE, '做完了': ReminderAction.DONE,
}


def parse_reminder_reply(text: str) -> ParsedReminderReply:
    if not isinstance(text, str) or not 1 <= len(text) <= 128:
        _unsupported()
    normalized = unicodedata.normalize('NFKC', text)
    if len(normalized) > 128 or any(unicodedata.category(char).startswith('C') for char in normalized):
        _unsupported()
    normalized = normalized.replace(' ', '').rstrip('。.!')
    if normalized in _ACTIONS:
        return ParsedReminderReply(_ACTIONS[normalized])
    extension = normalized.removeprefix('请')
    if extension.endswith('吧'):
        extension = extension[:-1]
    match = re.fullmatch(r'(?:再给我|再延长|延长)(.+)', extension)
    if match is None:
        _unsupported()
    duration = match.group(1)
    minutes = _HOURS.get(duration)
    if minutes is None and duration.endswith('分钟'):
        number = duration[:-2]
        minutes = int(number) if re.fullmatch(r'[0-9]{1,3}', number) else _MINUTE_WORDS.get(number)
    return ParsedReminderReply(ReminderAction.EXTEND, minutes)
