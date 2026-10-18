# Local STT assets and verification

Date: 2026-10-18. These public assets are local development files under ignored `.models/`; weights and recordings are not committed or distributed with this repository.

## Model

Publisher: [Systran/faster-whisper-base](https://huggingface.co/Systran/faster-whisper-base). Revision: `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`. The publisher model card declares MIT; retain the model card and applicable [Whisper license](https://github.com/openai/whisper/blob/main/LICENSE) when distributing weights. Native dependencies and their notices still require release review.

| File | Bytes | Verified SHA-256 |
| --- | ---: | --- |
| model.bin | 145217532 | d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9 |
| config.json | 2309 | 56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a |
| tokenizer.json | 2203239 | fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab |
| vocabulary.txt | 459861 | 34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913 |
| README.md | 1991 | b922acef3616e27b1d416260b63ba7114c732f0315012006781af2da69cd1ebf |

Weights matched the publisher API's LFS SHA-256; the smaller files matched the publisher's Git blob identifiers before the above SHA-256 values were recorded. Downloading was an explicit development action, separate from app execution.

## Actual local inference

Runtime: faster-whisper 1.2.1, CTranslate2 4.8.3, numpy 2.2.6, CPU int8, 4 threads, one worker. Optional dependency inventory generation succeeded for 31 installed distributions; some metadata lacks license expressions and requires review before release. It does not certify native FFmpeg/Qt/Python licensing.

Public fixture: [upstream JFK FLAC](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/tests/data/jfk.flac), 1,152,693 bytes; SHA-256 `63a4b1e4c1dc655ac70961ffbf518acd249df237e5a0152faae9a4a836949715`. Its downloaded bytes matched the publisher's Git blob hash. Used only as a local test asset, not redistributed.

- Decoded the public fixture to 16kHz mono PCM in memory; no microphone or private audio.
- Set HF_HUB_OFFLINE and disabled telemetry in the smoke subprocess; replaced Python socket connection methods with failures before loading the model/inferencing.
- Adapter run: 11.0 seconds audio, 0.951 seconds processing, 106 characters, expected phrase “ask not” present.
- Full WAV CLI run on a temporary converted public fixture: 11.0 seconds audio, 0.76 seconds processing, 106 characters; default output contained no transcript. Temporary WAV removed after the check.
- These two runs demonstrate local inference and CLI integration on this machine, not Chinese accuracy or a general performance benchmark. No claim is made about native-library internal immutable copies or zeroization at OS level.

## Uncompleted checks

Chinese public fixture download was not executed: automatic approval review failed because its service usage limit was exhausted. The message explicitly described an approval-review failure, not an unsafe-action determination. No bypass was attempted. Chinese pronunciation/recognition quality, real microphone handling, TTS, Qt worker integration and packaged runtime remain untested.
