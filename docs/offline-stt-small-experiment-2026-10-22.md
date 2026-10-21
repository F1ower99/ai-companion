# Offline STT small-model experiment — 2026-10-22

Development-only candidate; not a changed application default or general Chinese/device acceptance.

Source: [Systran/faster-whisper-small](https://huggingface.co/Systran/faster-whisper-small), fixed revision `536b0662742c02347bc0e980a01041f333bce120`. Model card declares MIT. No redistribution approval is implied.

All five files were downloaded to a new E directory and verified against upstream LFS SHA-256 or Git blob IDs. Recorded SHA-256 below also covers non-LFS files. No private audio, microphone, playback or credentials were used. Existing base files remain untouched. Total 486214370 bytes.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| README.md | 1998 | `329373481008c7c38654aff8ecdcf0163c211557cc7ba8e2ef6f2f84b4f75ec8` |
| config.json | 2370 | `b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828` |
| model.bin | 483546902 | `3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671` |
| tokenizer.json | 2203239 | `fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab` |
| vocabulary.txt | 459861 | `34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913` |

## Public fixture comparison

Same CPU int8/4threads and decoder options as the existing adapter; no new dependencies. Warm-model timings exclude model load. Both models passed the expected public English phrase.

| Chinese fixture, 13 reference characters | Beam1 normalized distance | Beam5 normalized distance | Warm inference beam1 / beam5 |
| --- | ---: | ---: | --- |
| Existing base | 2 | 2 | 0.562s / 0.594s |
| Candidate small | 0 | 0 | 1.718s / 1.813s |

The comparison explicitly maps only this fixture’s known traditional characters 開/時/間/點 to simplified and 九/五 to digits, then removes punctuation/whitespace. Raw exact matching still fails for small; do not erase that result. The earlier digits-only metric reported5/13 for small because it counted script differences. Base beam5 digits-only distance7 becomes2 with script equivalence. Neither metric is a general semantic accuracy score. One short public sample cannot establish representative Chinese recognition quality.

The unchanged source adapter also passed small-model English, normalized Chinese and pre-cancellation, with PCM clearing; isolated-process inference including model load was3.188s/3.000s. The separate standalone compiled probe also passed English expected phrase (12.031s), Chinese normalized equivalence (3.047s; raw exact reference false), pre-cancellation before native load and PCM clearing. Compilation exited 0 after 475.672s. These process-level timings include model load and cannot be directly compared with warm-model timings. Evidence: `compiled-stt-small-final.json` in the same E lab evidence directory. Existing compiled GUI uses explicit external model configuration; its default and existing acceptance boundaries are unchanged.

Evidence remains on E in the owned build lab: `whisper-small-quality-assets.json`, `decoder-quality*.json`; no models or private recordings are committed.

## Reproduction provenance

Public audio sources and their original byte hashes are recorded in [the asset ledger](offline-stt-assets-2026-10-18.md): JFK at faster-whisper tag v1.2.1, and SenseVoiceSmall revision `3847d57b6bdf2dd8875cb1508d2af43d80a16bf7`. Local 16 kHz mono PCM16 WAV hashes are `b9e1ae4e0837e7b99f05e4f61f70f5732320a56614ab4514d803fa85f9a563c4` (jfk.wav, 11 seconds) and `1c92a4a54368e0371bfa2dbf50304b0b0b42738a2fe9832b59c41db2e86fe23f` (zh.wav, 5.616 seconds). The Chinese reference is `开放时间早上9点至下午5点`.

Owned development harnesses live under `E:/AICompanionVoiceLab/build-lab/`: `probe_decoder_quality_script.py` and `probe_decoder_quality_script_small.py`; adapter probe `probe_small_source_adapter.py`; compiled driver `run_stt_small_probe_build.py` and runner `run_compiled_stt_small_evidence.py`. They are local lab artifacts, not shipped application code or a portable benchmark suite.

Normalization applies Unicode NFKC, translates exactly `九→9, 五→5, 開→开, 時→时, 間→间, 點→点`, and removes whitespace and characters whose Unicode category starts with P. Standard character Levenshtein distance is then computed against the normalized reference. Decoder settings: CPU int8, four threads, one worker, language explicitly en/zh, task transcribe, beam 1 or 5, temperature 0, condition_on_previous_text false, VAD false, without_timestamps true, word_timestamps false. Model loading uses local_files_only, offline environment flags and blocked Python socket connection methods. This does not certify every native library's networking behavior.
