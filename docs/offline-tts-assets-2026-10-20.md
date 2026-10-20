# Offline Chinese synthesis assets and actual execution

Original [Kokoro v1.1-zh](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh) declares Apache 2.0 and Chinese/English support. Converter [int8 bundle](https://huggingface.co/csukuangfj/kokoro-int8-multi-lang-v1_1), pinned revision `155831f1b4ba23b1f5c058be6a61df90cefb2a37`; [official runtime/speaker documentation](https://k2-fsa.github.io/sherpa/onnx/tts/all/Chinese-English/kokoro-multi-lang-v1_1.html). These declarations do not certify all native/data redistribution obligations: eSpeak/phonemizer/dictionary notices need separate release review. The model/LICENSE file is not a blanket license for every dependency.

365 selected public files, 194,382,580 bytes: runtime model, voices, tokens, US English/Chinese lexicons, three normalization FSTs, eSpeak data, model LICENSE and README. Every selected file matched pinned publisher LFS SHA-256 or Git blob SHA-1 before use. Local ignored `verified-assets.json` SHA-256: `a2b17b44331300462b09c88154c7e488744ae987853a3c8f62af5a5c6afebb0d`. No model/data files committed or redistributed.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| model.int8.onnx | 114299010 | bda15858163726a492d02a9a727bc263551b86ac77f90812c4b30ff41d380e26 |
| voices.bin | 53790720 | e64a5a581d8c2a350d848f51c3121657cd83aa07ed6109172177345874a7244c |
| tokens.txt | 1111 | 931ab2df2400cd65d580a22402024c2347ced8ae9ea300e545144b1aacc48e14 |
| lexicon-us-en.txt | 5956885 | 7daaab53a181be9885b853a8582bf1838186317e5dadacbcef9c426d6fa0da14 |
| lexicon-zh.txt | 2119465 | 11111d8cd695fba2ace1367a1d0a708b586e6ef5c1f9be91da5d7eef129b651c |
| date-zh.fst | 59154 | eb8aa079ae3cb81d8f4404992f39d61a0cb990947512b5b8d1e54d1f6980e718 |
| number-zh.fst | 64482 | 743f402181fcfebf76cc2f0546b71fa26476e626fbe4e460fb7b4c3a7a8bd5bd |
| phone-zh.fst | 88630 | 1ac2b6fa56b1442320c4de7db08353bab8963a2b57f365eebcdd3a2d3562f8d7 |
| LICENSE | 11358 | cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30 |

The first model download failed verification; it was not saved/used. Official pinned resolve download=true returned HTTP 200 with the correct 114,299,010 bytes and exact SHA-256. Auxiliaries were retained only after verification; no mirrors or disabled checks.

## Actual no-device smoke

- Installed optional sherpa-onnx/core 1.13.8 from official PyPI; numpy 2.2.6 already available.
- Fixed public sentence: `你好，这是离线中文语音合成测试。` Voice 3 (`zf_001`), CPU 2 threads, speed 1.0.
- Used the real parent adapter, process runner, pinned native runtime and model. A static smoke wrapper disabled Python socket.create_connection/connect/connect_ex in the child before invoking the same worker main. No credentials or user conversations were passed.
- Output: 24,000 Hz mono PCM16, 163,538 bytes, **3.407 seconds**, nonzero PCM; **5.255 seconds** total including validation, helper startup and weight loading on this machine. Not a general performance benchmark.
- Audio stayed in memory and was cleared. No file, microphone, speaker, Windows output-device query or cloud request. Python connection blocking does not certify OS-wide native network isolation; no download/network code exists in this runtime path.
- This proves actual generation/protocol execution, not intelligibility, voice preference, latency acceptance or playback. Native/immutable/pipe internal copies cannot be guaranteed physically zeroized. Packaged executable helpers are not yet implemented.
