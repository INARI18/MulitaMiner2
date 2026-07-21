# Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `No API key for model '...'` | Env var missing from `.env` | Add the var shown in the message (see `mulitaminer models`) |
| `Unknown scanner '...'` | Typo or config not registered | `mulitaminer scanners`; check `MULITAMINER_SCANNERS_DIR` |
| `No finding blocks found` | Wrong `--scanner` for this PDF, or marker mismatch | Run `mulitaminer segment` and check the block count/preview |
| Block count differs from the report | Marker regex too loose or too strict | Iterate on `marker_pattern` with `mulitaminer segment` (see SCANNER_CONFIGS.md) |
| Warning `input truncated ... instances omitted` | A single block exceeds the model's output budget | Expected for findings with many instances; core fields survive. A larger-output model avoids it |
| Warning `block N yielded no record ... dropped` | Model failed that block in every retry | Re-run (transient model variance) or try another model; the block id is named |
| Connection error with `ollama`/`lmstudio` | Local server not running | Start Ollama / LM Studio and confirm the port in `mulitaminer models` |
| Merged records you did not expect | Consolidation found fully identical repeats | Compare `results.raw.json` with `results.json` using `run.json`'s merge log |
| Slow extraction | Many retry rounds (see log) | Normal for payload-heavy reports; consider a model with a larger output cap |

Still stuck? Run with `--debug` and inspect `blocks.txt` (is the information
inside the block?) and `llm_traffic.jsonl` (what did the model actually
return?) in the run directory.
