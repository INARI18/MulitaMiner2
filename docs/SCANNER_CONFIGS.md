# Scanner Configs — Reference and Rationale

A scanner is defined by ONE JSON file in `src/mulitaminer2/configs/scanners/`
plus ONE prompt file in `configs/prompts/`. Users can plug additional scanners
with no Python: drop `<name>.json` + `<name>_prompt.txt` into a directory and
point the `MULITAMINER2_SCANNERS_DIR` env var at it. The field reference lives
in `scanners/engine.py`; this document records **why** each built-in value is
what it is — most of it was learned empirically, first in MulitaMiner v1 and
then during the v2 validation runs.

## OpenVAS (`openvas.json`)

**Marker `^\s*(Critical|High|Medium|Low|Log)\s+\(CVSS:`** — one match line is
one finding. The marker is the `Severity (CVSS: X.Y)` line that sits
immediately ABOVE each `NVT:` line. v1 originally marked at `NVT:` itself,
which left the severity header in the previous segment and forced the LLM to
guess severity (often defaulting to LOG) — misclassification on
Ingreslock/Telnet in the bWAPP report. Breaking one line earlier makes the
header travel with its NVT.

**`context.header_patterns`** — port/protocol headers (`High 443/tcp`) appear
in three layouts: plain, reversed order (`443/tcp High`, markdown extractor),
and with a `2.1.1 ` section-number prefix. The latest header above a marker
becomes that block's port/protocol context, rendered into its `### BLOCK`
prompt line. OpenVAS also emits pseudo-protocols in headers
(`general/CPE-T`) — those stay LLM context but never enter the typed
`protocol` field.

**`context.host_anchor` / `host_line`** — the scanned IP sits on the nearest
non-blank line above `Host scan start`, in the report preamble (before any
marker); context tracking is the only way to recover it.

**`max_vulns_per_chunk: 4`** — v1 calibration.

## Tenable WAS (`tenable.json`)

**Marker `VULNERABILITY <SEV> PLUGIN ID <n>`** (case-insensitive via `(?i)`)
— one match line is one block; a finding appears as TWO consecutive blocks,
Base (Description/Solution/Risk/Plugin Details) and `Name Instances (N)`
(per-URL evidence).

**`name_above_marker: true` + `name_stop_pattern`** — the vulnerability NAME
is the ONE line immediately before the VULNERABILITY header (mirror image of
the OpenVAS NVT lesson). Verified against the ground truth: names never wrap
(max 56 chars). A speculative 2-line walk-back polluted names with the
previous block's reference tail (`BID -`, `CVE -`) on the JuiceShop report —
22 broken base/instances pairings and 8 dropped blocks. The stop pattern
rejects section headers and reference-content lines as a second guard.

**`pair`** — base + instances blocks are merged by normalized name (with the
`Instances (N)` suffix stripped) and the fields in `by` (`plugin`, Tenable's
stable numeric ID). Pairing is structure, not deduplication: it always runs;
without it every finding is two broken halves.

**`severity_map INFO→LOG`** — both scanners share one informational tier
(v1 decision): a Tenable record is INFO before pairing, LOG after.

**`max_vulns_per_chunk: 3`** — v1 calibration.

## Engine-wide rules (not configurable)

- **Duplicate = fully identical record** (name compared normalized). Same key
  with different content is two real findings and never merges — generalizes
  v1's `Services` exception (findings that legitimately repeat on the same
  host/port with different content, one record per detected service).
  Legitimate OpenVAS repeats live on different hosts/ports and are therefore
  never merged; Tenable should have no true duplicates at all — a dedup merge
  in a Tenable run's `merge_log` is an anomaly worth investigating.
- **Oversized single blocks** (e.g. Tenable `Instances (25)` — input alone
  exceeding the model's output budget) are truncated at the input tail with an
  explicit `[TRUNCATED: ...]` marker and a per-block warning: partial data
  beats a dropped finding, and the truncation is declared, never silent.
