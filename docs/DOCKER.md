# Docker

`docker compose up` runs an experiment against the fine-tuned local model
(`mulita-qwen2.5-1.5b-v4`, served by Ollama) with nothing installed on the
host except Docker.

## Requirements

- Docker with Compose 2.24 or newer.
- About 3 GB of disk: the model is downloaded once (~1 GB) and Ollama keeps
  its own copy.
- Optional: an NVIDIA GPU with the
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
  (Docker Desktop on Windows only needs the NVIDIA driver). See
  [Using the GPU](#using-the-gpu).

## Run

```bash
docker compose up --build
```

The first run downloads the model; later runs reuse it. Results land in
`./output_docker`, one folder per (model, report, run) plus the
experiment's `report.html`.

### Using the GPU

By default Ollama runs on the CPU: a container only sees the GPU when Compose
is told to hand it over, and Compose cannot do that conditionally, so the
NVIDIA reservation lives in `docker-compose.gpu.yml`. Add it to the command:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

On a machine without an NVIDIA GPU this fails to create the `ollama`
container (`could not select device driver "nvidia"`): drop the extra file.

To skip the two `-f` flags on a machine that always uses the GPU, put
`COMPOSE_FILE=docker-compose.yml;docker-compose.gpu.yml` in `.env`; plain
`docker compose up --build` then picks both files.

On the CPU the model works but is much slower, and the default 120 s request
timeout can cut healthy calls short. Raise `request_timeout_s` in
`src/mulitaminer/configs/llms/mulita-qwen2.5-1.5b-v4.json` and rebuild
(see [ADDING_A_MODEL.md](ADDING_A_MODEL.md)).

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

```bash
MODELS=mulita-qwen2.5-1.5b-v4,deepseek RUNS=5 docker compose up --build
```

### API keys

Cloud models read their key from `.env` (gitignored) at the repo root, the
same file the local install uses. The container receives every variable in
it, so any profile's key works (`DEEPSEEK_API_KEY`, `OPENAI_API_KEY`,
`GROQ_API_KEY`, `CLAUDE_API_KEY`, or the `api_key_env` of your own profile;
see [CONFIG.md](CONFIG.md#api-keys)). The file is optional: a run with only
local models needs no key, and an experiment skips (does not fail) a cloud
model whose key is missing. Keys passed on the command line do not reach the container.

## What the services do

| Service | Image | Role |
| --- | --- | --- |
| `ollama` | `ollama/ollama:0.34.0` | Model server (CPU, or GPU with `docker-compose.gpu.yml`). Not published on the host, so it does not clash with a local Ollama on 11434 |
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

## Cleaning up

```bash
docker compose down      # stop the containers, keep the model
docker compose down -v   # also delete the downloaded and registered model
```
