# KorvaTTS — Vietnamese-first, on-device text-to-speech

[🇻🇳 Tiếng Việt](README.vi.md)

KorvaTTS is an open-source text-to-speech system focused on **Vietnamese with natural code-switching** (Vietnamese sentences that contain English words, brand names, tech terms). It runs entirely on-device through ONNX Runtime: no GPU required, no API calls, 44.1 kHz output.

This Orange Pi adaptation is designed to run **fully locally**: the installer stores model files in this repository's `assets/` directory, and normal inference makes no network request after the initial download. It is based on the original project, [dogenthq/KorvaTTS](https://github.com/dogenthq/KorvaTTS).

The model is our own re-implementation of the 99M-parameter [Supertonic 3](https://github.com/supertone-inc/supertonic) architecture (flow-matching TTS), **trained from scratch** on Vietnamese data, with a vocoder based on [BlueCodec](https://github.com/maxmelichov/BlueTTS). Upstream Supertonic is being archived by its authors; KorvaTTS continues the line with a Vietnamese focus and an open roadmap toward voice cloning and training.

## Highlights

- 🇻🇳 **Vietnamese-first** — trained on Vietnamese audiobook speech plus a private code-switching set
- 🔀 **Code-switching** — English words inside Vietnamese sentences are read naturally
- ⚡ **Fast on CPU** — real-time factor well below 1 on a laptop CPU; GPU optional
- 🔊 **44.1 kHz WAV** output, no external upsampler
- 🧩 **Drop-in compatible** with Supertonic 3 runtimes (see [Compatibility](#compatibility-with-supertonic))
- 🪪 **Apache-2.0** for both code and weights

## Voices

10 bundled voices — 5 female, 5 male. Listen to every voice on the [Hugging Face model card](https://huggingface.co/dogenthq/KorvaTTS#voices).

| Female | Male |
|--------|------|
| `bao_kim` — Bảo Kim | `gia_bao` — Gia Bảo |
| `khanh_vy` — Khánh Vy | `hoang_nam` — Hoàng Nam |
| `ngoc_huyen` — Ngọc Huyền | `huu_dat` — Hữu Đạt |
| `phuong_linh` — Phương Linh | `quang_huy` — Quang Huy |
| `quynh_nhu` — Quỳnh Như | `thanh_phong` — Thanh Phong |

## Orange Pi: fully local installation

The following one-time setup targets an Orange Pi (or another Linux ARM64 device) with
Python 3.10+. It creates a project-local `.venv`, installs the package there, and
downloads the model as real files into `./assets/`—not an external Hugging Face cache
or symlink. Internet access is needed only for this setup step.

```bash
cd korvatts-orangepi
./scripts/install-local.sh
```

The installer creates `.env` from `.env.example`, sets
`KORVATTS_ASSETS_DIR=assets`, and creates a private local API token. Start the service
from the repository directory; it uses only `./assets/` and remains offline:

```bash
cd korvatts-orangepi
HF_MODEL_ONLINE=false ./.venv/bin/python web_service.py
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080) on the Orange Pi. Verify that the
model files are present and service is healthy:

```bash
find assets/onnx assets/voice_styles -type f | sort
curl http://127.0.0.1:8080/healthz
```

To use the CLI without network access, start it from the repository directory (where
`./assets` resolves automatically):

```bash
HF_MODEL_ONLINE=false ./.venv/bin/korvatts voices
HF_MODEL_ONLINE=false ./.venv/bin/korvatts synth "Xin chào, đây là KorvaTTS." -v khanh_vy -o hello.wav
```

`KORVATTS_ASSETS_DIR=assets` is intentionally **relative to the process working
directory**. For `web_service.py`, run it from this project directory as shown above.
If you run it from another directory, pass an explicit `--assets-dir` to the CLI or
set `KORVATTS_ASSETS_DIR` to an absolute path.

## Installation

For the published package or environments where model files may be cached outside the
repository:

```bash
pip install korvatts
```

Requires Python ≥ 3.10. For GPU inference install `onnxruntime-gpu` (CUDA) instead of `onnxruntime`.

## Quick start

```python
from korvatts import TTS

tts = TTS()  # first run downloads weights + voices from Hugging Face
print(tts.list_voices())

wav, duration = tts.synthesize(
    "Hôm nay team mình sẽ demo tính năng text-to-speech mới.",
    voice="khanh_vy",
    lang="vi",
    total_steps=32,  # default; best quality. Lower (8-16) for faster synthesis
    speed=1.05,      # default; 0.5 (slow) .. 2.0 (fast)
)
tts.save_audio(wav, "output.wav")
```

Command line:

```bash
korvatts voices
korvatts synth "Xin chào, đây là KorvaTTS." -v khanh_vy -o hello.wav
```

Use local assets instead of downloading: pass `TTS(assets_dir="path/to/assets")` or set `KORVATTS_ASSETS_DIR`. The directory must contain `onnx/` and `voice_styles/`.

## Offline web service and Bearer API

The package is an inference library; this repository also includes a small optional
web demo in `web_service.py`. It serves the UI at `/`, lists voices at
`GET /api/voices`, and produces a WAV from `POST /api/tts`.

For a fully offline deployment, run `./scripts/install-local.sh` once from this
repository. It downloads/copies the model into `./assets/`, creates `.env` with the
relative setting `KORVATTS_ASSETS_DIR=assets`, and configures `HF_MODEL_ONLINE=false`.
After that initial setup, start `web_service.py` from the repository directory; it
uses only the local `assets/onnx/` and `assets/voice_styles/` files.

```dotenv
KORVATTS_ASSETS_DIR=assets
HF_MODEL_ONLINE=false
KORVATTS_WEB_ENABLED=true
KORVATTS_API_TOKEN=replace-with-a-long-random-token
```

`HF_MODEL_ONLINE=false` is the deployment convention: use only the validated local
asset directory. Set it to `true` only when deliberately allowing model refreshes.
The service does not put tokens in source code or browser JavaScript.

All public integration endpoints under `/api/*` require Bearer authentication;
`/healthz` remains unauthenticated for monitoring. Call the API with:

```bash
curl https://YOUR-URL/api/voices \
  -H "Authorization: Bearer $KORVATTS_API_TOKEN"

curl https://YOUR-URL/api/tts \
  -H "Authorization: Bearer $KORVATTS_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"text":"Xin chào, đây là KorvaTTS.","voice":"khanh_vy","speed":1.05}' \
  --output hello.wav
```

When `KORVATTS_WEB_ENABLED=true`, the UI is immediately usable without asking visitors
for a token. It receives an HttpOnly, SameSite session cookie and calls the separate
`/web-api/*` routes; browser code never receives the bearer token. Set
`KORVATTS_WEB_ENABLED=false` to disable the UI; `/` then displays **“Chế độ web đã
tắt.”**, while the Bearer-protected `/api/*` endpoints continue serving requests.

## Language support

- **Primary:** Vietnamese (`lang="vi"`), including English words embedded in Vietnamese text.
- **English (`lang="en"`):** part of the training data is English, so plain English works, but we do **not** guarantee English quality matches — or exceeds — the original Supertonic 3 English voices. Vietnamese is what this model is built for.
- **Other languages:** the Supertonic 3 tag set (31 languages) is still accepted by the text encoder, but those languages were not in the training data; quality is untested.

## Compatibility with Supertonic

The phase-1 weights keep the exact ONNX graph signatures and voice-style JSON format of Supertonic 3. You can copy the KorvaTTS `onnx/` and `voice_styles/` folders into any Supertonic 3 runtime (Python, Node.js, browser/WebGPU, Rust, C++, Swift, Flutter, …) and they will work unchanged.

This compatibility is intentional for phases 1–2. **Phase 3 will change the architecture and will not be loadable by Supertonic runtimes.** Version tags on Hugging Face will make it clear which checkpoints are compatible.

## Licenses

| Component | License |
|-----------|---------|
| Source code in this repository | [Apache-2.0](LICENSE) |
| Model weights & voice styles | [Apache-2.0](MODEL_LICENSE.md) — trained from scratch, not derived from Supertonic weights |

Portions of the inference code are adapted from Supertonic (MIT, © Supertone Inc.); the vocoder follows BlueCodec from BlueTTS (MIT). See [NOTICE](NOTICE). KorvaTTS is not affiliated with Supertone Inc.

## Acknowledgements & citation

KorvaTTS builds on the work of others. If you use it, please also cite them:

- **Supertonic / SupertonicTTS** — architecture and reference implementation. [github.com/supertone-inc/supertonic](https://github.com/supertone-inc/supertonic)
- **BlueTTS / BlueCodec** — vocoder design. [github.com/maxmelichov/BlueTTS](https://github.com/maxmelichov/BlueTTS)
- **PhoAudiobook** — Vietnamese training corpus. [huggingface.co/datasets/thivux/phoaudiobook](https://huggingface.co/datasets/thivux/phoaudiobook)

```bibtex
@misc{korvatts2026,
  title        = {KorvaTTS: Vietnamese-first on-device text-to-speech},
  author       = {dogenthq},
  year         = {2026},
  howpublished = {\url{https://github.com/dogenthq/KorvaTTS}}
}

@article{kim2025supertonictts,
  title   = {SupertonicTTS: Towards Highly Efficient and Streamlined Text-to-Speech System},
  author  = {Kim, Hyeongju and Yang, Jinhyeok and Yu, Yechan and Ji, Seunghun and Morton, Jacob and Bous, Frederik and Byun, Joon and Lee, Juheon},
  journal = {arXiv preprint arXiv:2503.23108},
  year    = {2025}
}

@misc{melichov2025bluetts,
  title        = {BlueTTS},
  author       = {Melichov, Max},
  year         = {2025},
  howpublished = {\url{https://github.com/maxmelichov/BlueTTS}}
}

@inproceedings{vu2025phoaudiobook,
  title     = {Zero-Shot Text-to-Speech for Vietnamese},
  author    = {Vu, Thi and Nguyen, Linh The and Nguyen, Dat Quoc},
  booktitle = {Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Short Papers)},
  year      = {2025}
}
```
