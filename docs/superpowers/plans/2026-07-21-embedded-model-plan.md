# MulitaMiner2 — Embedded Specialist Model Plan

**Status:** planned (design note; no implementation started).
**Goal:** an optional, tiny (0.5–2B), task-specialized local model embedded in
the tool for the user with **no API budget and no GPU** (plain notebook, CPU,
8 GB RAM) — running in-process, with no external runtime to install.

## 1. Motivation and target user

The tool currently serves two profiles: API budget (DeepSeek/GPT) or a
reasonable GPU (4–8B local models via Ollama/LM Studio). The missing third
profile is CPU-only with zero budget. For that regime:

- A tiny model is genuinely bad zero-shot at structured extraction; prompting
  does not rescue a 0.6B. Narrow-task fine-tuning is the only lever that
  works at this size — and the task is the ideal distillation case: mostly
  **copying spans from text into the right field**, not reasoning. A 1B
  specialist can plausibly tie a generic 7B *on this task*.
- The project is unusually well positioned: curated ground-truth baselines,
  a native evaluation subsystem (`mulitaminer evaluate`: measured means,
  set_f1 + set_f1_ids, NLI contradiction check, coverage), and training GPUs
  available. The usual killers of fine-tuning projects (no labels, no
  referee) are already solved.
- Architecturally the tuned model is just another model profile + one
  provider — it enters through the same seam as every other LLM.

**Specialization risk:** tuning on OpenVAS+Tenable data may hurt on unseen
scanners, and plugability is the tool's purpose. Mitigations: the embedded
model is an **optional profile**, never the universal default; and the
evaluation protocol (§6) includes an unseen-scanner cut measuring the
specialization cost honestly before any promotion.

## 2. Cost/benefit ladder (execute in order)

Each step is independent, delivers value alone, and informs the next. The
expensive decision (training) happens only after the cheap steps establish
the real gap.

- **L0 — Constrained decoding (zero training, do first):** enforce the output
  format at decode time (JSON-schema/grammar), not in the prompt.
  `extraction_model_for(record_type)` already produces the closed JSON schema
  per scanner — feed it to the decoder (GBNF for llama.cpp; `format` for
  Ollama). This eliminates by construction the dominant small-model error
  class (invalid JSON, missing fields); whatever gap remains becomes
  precisely measurable.
- **L1 — External tuned baseline (zero training of ours, timeboxed):** run
  **NuExtract** (one model, not a survey) through the evaluation battery.
  Generic-extraction skill ≠ vulnerability-report skill, so this does not
  replace our fine-tuning — it is a baseline row that either raises the bar
  for our training or kills the hypothesis cheaply.
- **L2 — Own light fine-tuning (QLoRA):** the central experiment, §3–§5.

## 3. Training recipe

- **Base model:** re-survey candidates when L2 starts (small-model releases
  age in months; a name list written today would be stale). The selection
  criteria are what stays fixed, in order: (1) permissive redistribution
  license (Apache 2.0/MIT) — the tuned artifact will be published; (2)
  context ≥ 32k — chunks are 4–10k tokens with long outputs; (3) mature
  QLoRA (Unsloth) + GGUF/llama.cpp support; (4) size 0.5–2B for the CPU-only
  target (≈4B as the absolute ceiling). Also evaluate one **warm start**
  candidate (an already-extraction-tuned small model as the LoRA base) —
  it may need less data than a generic base.
- **Method:** QLoRA adapter (Unsloth or HF TRL), trained on available GPUs;
  merge → quantize **GGUF Q4** → publish.
- **One multi-scanner adapter** (decision, not an open question): N adapters
  are N artifacts to version, publish and keep in sync with N prompts.
  Revisit only if the single adapter fails the gate.
- **Train with the tool's real prompts** — the model learns the task exactly
  as served in production, not a variant.
- **Compose with L0 at serving time:** the smaller the model, the more the
  grammar guarantees form so the model spends capacity on content only.

## 4. Data engine (the real problem)

The evaluation baselines are a few hundred records — insufficient for
training and **untouchable** (contamination rule below). Two sources:

1. **Distillation (silver data):** the best available API model extracts
   from many reports; a hand-checked sample quantifies the teacher error
   rate (goes into the dataset report). Two hard requirements:
   - Silver data must **conform to the prompt contract** (e.g. references
     one-per-element, verbatim cvss lines) — teachers violate formatting
     contracts intermittently, and distilling raw teacher output would bake
     that jitter into the student. Normalize before training.
   - The deterministic annotators (`annotate_cvss_refs`, `annotate_instances`
     line-grammar parsers) **clean/verify the silver data** on the fields
     they cover — teacher-independent validation for free, citable in the
     dataset chapter.
2. **Synthetic report generation:** the Greenbone NVT feed is public — build
   synthetic OpenVAS reports covering thousands of NVTs the few real PDFs
   never show (varying hosts, ports, present/absent sections, layout
   breaks). Synthesize the **extracted text**, not PDFs (the pipeline sees
   post-extraction text) — but with a **PDF-noise model**: deliberately
   inject the artifacts real PDF extraction produces (broken ligatures such
   as `￾`, mid-name line wraps, wrapped title suffixes). Training on
   clean text would create a distribution mismatch with production input.
   Tenable synthesis is limited (commercial format) — declare the
   OpenVAS-heavy training mix as a limitation.

> **Contamination rule (non-negotiable):** the evaluation baselines (all
> PDFs and XLSX under `resources/`) never enter training — not the PDFs,
> not the records. They are the test set; training on them invalidates the
> entire comparative table.

## 5. Serving inside the tool (no external runtime)

- **Provider:** `llama-cpp-python` in-process (pip wheel, CPU-first, loads
  GGUF directly, native grammar support = L0 for free). ~30 lines
  implementing the existing client seam + one model profile entry.
- **Distribution:** never commit the binary (0.5–1 GB). Publish the GGUF on
  Hugging Face; the provider downloads on first run (`huggingface_hub`),
  cached in a gitignored local dir. Air-gapped hosts copy the `.gguf`
  manually into that dir (same philosophy as the KEV/EPSS feeds). Also
  publish a Modelfile for users who prefer Ollama — both paths serve the
  same GGUF.
- **Install UX:** an optional dependency extra (e.g. `uv sync --group local`)
  pulls llama-cpp-python; then
  `mulitaminer extract report.pdf -s openvas -m mulita-local`.

## 6. Evaluation (the thesis chapter)

Run the native evaluator as-is. Minimum comparison table:

| Row | What it measures |
| --- | --- |
| mulita-extractor (tuned + constrained decode) | the proposal |
| same base model, NO fine-tune, + constrained decode | ablation: training vs grammar |
| generic 4–8B local model (current setup) | what the GPU user already has |
| large API model (DeepSeek) | practical ceiling |
| NuExtract | external tuned-for-extraction baseline |

Mandatory cuts:

- **Unseen scanner** (a scanner absent from training): measures the
  specialization cost. This number decides whether the embedded model can
  ever be a default or stays an optional profile.
- **CPU execution cost:** tokens/s and minutes/report on a modest machine
  (~10–20 tok/s at 1B Q4 means minutes per chunk with long outputs — fine
  for batch, but document the expectation).

**Promotion gate:** the embedded model becomes the recommended profile for
the no-GPU user only if (a) it ties or beats the generic 4–8B on supported
scanners and (b) it does not collapse on the unseen scanner (documented,
acceptable degradation).

## 7. Repository split (decided)

Training lives in a **dedicated repository**; the tool ships only the
finished artifact. Rationale:

- **Dependencies:** training pulls torch/CUDA/Unsloth — none of it may touch
  the tool's dependency tree (the tool keeps even BERTScore optional).
- **Lifecycle:** the model retrains when scanner layouts change; the tool
  versions code. Different cadences, different versioning — the artifact is
  versioned on HF (`mulita-extractor-v{n}`) with a model card recording
  which scanner/prompt versions it was trained against; the tool pins a
  revision.
- **Contamination enforcement:** the baselines live in the tool repo; the
  training repo has no access to them beyond an explicit deny-list.
- **Judge independence:** the evaluator (referee) and the training code
  (trainee) living in separate repositories is both engineering hygiene and
  a methodological argument for the thesis.

In the tool repo: the `llama_cpp` provider, the model profile, the download
+ air-gapped path, docs. In the training repo: data engine (distillation +
synthetic generator + noise model), QLoRA configs, the written contamination
policy, publication scripts.

## 8. Risks and limitations (honest radar)

- **Own maintenance lifecycle:** scanner report layouts change with versions
  → re-distill/re-train. Versioned artifacts with recorded provenance (§7).
- **CPU latency on long outputs** is the real bottleneck, not model loading
  (§6 documents expectations).
- **Tenable data scarcity** → OpenVAS-heavy training mix; declared.
- **The honest alternative for the truly hardware-less user:** for a fixed,
  known scanner, a deterministic parser (regex/state machine) extracts
  without any LLM — the deterministic annotators already prove big pieces
  of this. That is not the thesis (the LLM provides genericity), but the
  trade-off deserves an explicit line in the paper; reviewers will ask.

## 9. Roadmap

| Phase | Delivers | Depends on | Effort |
| --- | --- | --- | --- |
| F0 | Constrained decoding wired into current providers (grammar/`format`), measured with existing local models | schema derivation (ready) | S |
| F1 | NuExtract baseline row in the evaluation table | F0 (fair comparison) | S |
| F2 | Data engine: distillation + contract normalization + annotator cleaning; synthetic OpenVAS generator with PDF-noise model; contamination policy written and enforced | — | M |
| F3 | Candidate re-survey; QLoRA on 1–2 finalists (+ warm-start test); GGUF Q4 export; HF publication + Modelfile | F2 | M |
| F4 | `llama_cpp` in-process provider + first-run download + air-gapped path + `local` dependency group | — (parallel to F2/F3) | S–M |
| F5 | Full evaluation (§6) incl. unseen scanner and CPU cost; gate decision | F1+F3+F4 | M |
| F6 | Writing: comparative experiment for the thesis + user docs ("no-GPU profile") | F5 | M |

Sequencing notes: F0 and F4 need no training and deliver value even if
fine-tuning is postponed (F0 improves today's local models; F4 gives a
pip-only path for *any* GGUF). F1 can kill or reinforce the hypothesis
early and cheaply — that is why it precedes training.

## 10. Open decisions

- [ ] Target size: 0.8B (hardware floor) vs 2B (quality cushion) — or train
  both and let the gate decide.
- [ ] Silver data volume: start ~5–10k examples and measure the curve.
- [ ] Artifact naming/versioning scheme (`mulita-extractor-{size}-v{n}`).
- [ ] Training repository name and skeleton.
