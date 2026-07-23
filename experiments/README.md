# experiments/

One-off studies kept **out of the core pipeline** (`src/mulitaminer/`) on purpose,
so experimental prompting/serving does not mix with the tool proper.

## Small-model study (local, CPU): task-specialized vs general

Question: how small can a **local** model go and stay competitive with the DeepSeek
API, on coverage AND per-field fidelity?

Two model kinds, prompted differently:

| Kind | Models | Prompt | How to run |
| --- | --- | --- | --- |
| Task-specialized | NuExtract 3.8B / `nuextract-smol` 1.7B / `nuextract-tiny` 0.5B | native `<\|input\|>### Template ... ### Text ... <\|output\|>` | `nuextract_native.py` (this dir) |
| General instruct | `qwen2.5-0.5b` / `-1.5b` / `-3b` (also Llama-3.2, Gemma-2, SmolLM2) | the tool's normal prompt | the normal `mulitaminer experiment` |

Why the split: NuExtract ignores the tool's general prompt and leaves body fields
(`impact`, `insight`, `solution`, `references`) empty. It needs its native template.
General instruct models use the normal prompt and drop into the core pipeline as-is.

### Serving on CPU with Ollama

```bash
ollama pull qwen2.5:1.5b            # and 0.5b / 3b
ollama pull sroecker/nuextract-tiny-v1.5
# the OpenAI-compatible endpoint cannot set num_ctx per request, so set the
# server default (avoids per-model Modelfiles):
OLLAMA_CONTEXT_LENGTH=16384 ollama serve
```
`temperature=0` is already the tool default for every model (deterministic extraction),
and it is sent on every call, so it overrides Ollama's own 0.7.

### Run the general models (normal pipeline)

```bash
uv run mulitaminer experiment resources --models qwen2.5-1.5b,qwen2.5-0.5b,qwen2.5-3b --runs 3
```

### Run the NuExtract family (native template, this script)

```bash
uv run python experiments/nuextract_native.py \
    openvas resources/openvas/OpenVAS_JuiceShop.pdf nuextract-tiny out/nu_tiny_juice
uv run mulitaminer evaluate out/nu_tiny_juice --baseline resources/openvas/OpenVAS_JuiceShop.xlsx
```
One call per block (NuExtract-1.5 fills one object per call), so it is slower than the
batched pipeline. First validate the native prompt on the 3.8B (already served via vLLM):
if `impact`/`solution`/`references` fill in, the template is right, then sweep smol/tiny.

### Report

Compare coverage (recall/precision) AND per-field fidelity vs DeepSeek (the same
`evaluate` per-field scores), and note tok/s per model. The known baseline finding:
DeepSeek is perfect on Tenable; NuExtract-3.8B (general prompt) matched coverage but
left body fields empty. This study isolates model size and prompt format.
