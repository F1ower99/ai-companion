# MVP acceptance status — 2026-10-21

This ledger distinguishes implemented behavior from end-user acceptance. A rough percentage is not evidence that the original MVP scope is complete.

| Capability | Verified implementation | Remaining acceptance or work |
| --- | --- | --- |
| Desktop companion shell | Transparent, draggable, topmost pet and chat surface; compiled default-off startup | Actual desktop dragging, tray exit and login startup |
| Local data and memory | SQLite tasks/goals, conversation persistence, explicit memory controls | User workflow evaluation; automatic semantic memory remains deferred |
| Proactive decisions | Clock-injected deterministic rules, priorities, deadlines, cooldown and reminder lifecycle | Real daily-plan experience |
| Reminder responses | Deterministic Chinese text proposal, preview and explicit confirmation; reevaluation after extension; explicit voice/chat draft pull in Stage 7O | Hands-free spoken routing is not implemented |
| Activity awareness | Optional session idle/recent-input signal; no collection while disabled | Real opt-in experience; foreground application and application usage duration are not implemented |
| Text model integration | Provider boundary and explicit configuration | User-selected provider and credentials; no fabricated live acceptance |
| Offline recognition | Local Whisper adapter, bounded audio lifecycle; compiled public English inference/cancellation and GUI default-off startup verified | Real microphone, GUI-driven recognition and Chinese accuracy remain unaccepted |
| Offline speech | Explicit synthesis/playback controls; compiled Qwen public synthesis and cancellation | Natural soft female voice audition and full device interaction; synthesis latency remains substantial |
| Voice-to-reminder loop | Transcription goes to an empty draft; explicit pull into current reminder, then Preview and Confirm, verified with fake-device transcript | Real recording-to-action experience and hands-free routing remain unaccepted |

The Stage 6 privacy contract deliberately excludes application names and activity history. Its `focused` state means recent session input, not proof of coding or of a particular foreground task. The original application-name/duration requirements therefore cannot be counted as satisfied by Stage 6. Any implementation needs a separate spec and privacy review; existing idle-awareness consent must not silently expand.

No microphone capture, audio playback, private conversation upload or real credential use is required to complete the independent packaging checks. Those checks do not substitute for the outstanding human acceptance items above.
