# Docker

`docker compose up` runs an experiment against the fine-tuned local model
(`mulita-qwen2.5-1.5b-v4`, served by Ollama on the GPU) with nothing
installed on the host except Docker.

## Requirements

- Docker with Compose v2.
- An NVIDIA GPU and the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
  Without one, see [Running on CPU](#running-on-cpu).
- About 3 GB of disk: the model is downloaded once (~1 GB) and Ollama keeps
  its own copy.

## Run

```bash
docker compose up --build
```

The first run downloads the model; later runs reuse it. Results land in
`./output_docker`, one folder per (model, report, run) plus the
experiment's `report.html`.

The defaults run `mulitaminer experiment resources --models
mulita-qwen2.5-1.5b-v4 --runs 3 --metrics all`. Override them with
environment variables:

| Variable | Default | What |
| --- | --- | --- |
| `REPORTS` | `resources` | PDF file or directory, relative to the repo (mounted at `/app/resources`) |
| `MODELS` | `mulita-qwen2.5-1.5b-v4` | Comma-separated model profiles |
| `RUNS` | `3` | Repetitions per (model, report) |
| `METRICS` | `all` | Text metrics, as in `mulitaminer evaluate --metrics` |
| `INSTALL_EVAL` | `false` | `true` builds the image with BERTScore/NLI (pulls torch) |
| `DEEPSEEK_API_KEY` | empty | Only needed when `deepseek` is in `MODELS` |

```bash
MODELS=mulita-qwen2.5-1.5b-v4,deepseek RUNS=5 docker compose up --build
```

Put `DEEPSEEK_API_KEY` in `.env` (gitignored) rather than on the command
line.

## What the services do

| Service | Image | Role |
| --- | --- | --- |
| `ollama` | `ollama/ollama:0.34.0` | Model server on the GPU. Not published on the host, so it does not clash with a local Ollama on 11434 |
| `model-fetch` | `python:3.11-slim` | Runs `tools/fetch_model.py`: downloads the GGUF and `Modelfile` from [Hugging Face](https://huggingface.co/Inari18/mulita-extractor-qwen2.5-1.5b) at a pinned commit and checks the GGUF's sha256 |
| `model-register` | `ollama/ollama:0.34.0` | `ollama create mulita-qwen2.5-1.5b-v4 -f Modelfile`, then exits |
| `mulita` | built from `Dockerfile` | The tool; starts once the model is registered |

Two things are pinned on purpose:

- **The model** (`REVISION` and `GGUF_SHA256` in `tools/fetch_model.py`). A
  new upload to the Hugging Face repo does not change what runs here until
  those two lines change.
- **The Ollama version.** Changing it moves the scores by a few points, so
  compare numbers only between runs on the same tag.

The `Modelfile` is required, not optional: registering the GGUF without its
chat template silently leaves `references`, `instances` and `plugin` empty.

## Other commands

The `mulita` service's entrypoint is `mulitaminer`, so any command works with
`docker compose run`. Only `resources/` and `output_docker/` are mounted
by default; mount `outputs/` too for `extract`:

```bash
docker compose run --rm -v ./outputs:/app/outputs mulita \
  extract resources/openvas/OpenVAS_JuiceShop.pdf --model mulita-qwen2.5-1.5b-v4
```

## Running on CPU

Remove the `deploy:` block from the `ollama` service and Ollama falls back to
the CPU. It works, but much slower, and the default 120 s request timeout can
cut healthy calls short. Raise `request_timeout_s` in
`src/mulitaminer/configs/llms/mulita-qwen2.5-1.5b-v4.json` and rebuild
(see [ADDING_A_MODEL.md](ADDING_A_MODEL.md)).

## Cleaning up

```bash
docker compose down      # stop the containers, keep the model
docker compose down -v   # also delete the downloaded and registered model
```
