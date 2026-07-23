# experiments/

One-off studies and data-prep utilities kept **out of the core pipeline**
(`src/mulitaminer/`) on purpose, so experimental prompting/serving and ground-truth
preparation do not mix with the tool proper.

Each subfolder is self-contained and has its own README:

| Subfolder | What it is |
| --- | --- |
| [`small_model_study/`](small_model_study/) | Can a small local model match the DeepSeek API on coverage and per-field fidelity? Task-specialized (NuExtract) vs general-instruct, prompted differently. |
| [`baselines/`](baselines/) | Provenance of the ground-truth baseline XLSX: scripts that derive them from each scanner's native CSV export, plus a schema normalizer. The tool *consumes* baselines; it does not build them, so this lives here, not in `src/`. |
