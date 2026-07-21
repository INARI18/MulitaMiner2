# Scanner Configs — Reference and Rationale

A scanner is defined by ONE JSON file in `src/mulitaminer/configs/scanners/`
plus ONE prompt file in `configs/prompts/`. Users can plug additional scanners
with no Python: drop `<name>.json` + `<name>.txt` into a directory and point
the `MULITAMINER_SCANNERS_DIR` env var at it. The field reference lives in
`scanner_engine.py`; this document records **why** each built-in value is what
it is — all of it verified empirically against the baseline reports.

## Adding a scanner in short

Start minimal — `name`, `source`, `max_vulns_per_chunk`, and the
`marker_pattern` (the line that opens every finding; one match = one block).
The prompt file defaults to `<name>.txt` next to the JSON (or in a sibling
`prompts/` folder); an explicit `prompt` key overrides.
Then look at YOUR report and answer three questions; each "yes" adds one key:

1. Is the finding's NAME on the line above the marker? → `name_above_marker`
   (+ `name_stop_pattern` if that line is sometimes previous-block content).
2. Is there information valid for SEVERAL findings printed above them
   (port headers, a single host line)? → `context`.
3. Is one finding printed as TWO OR MORE blocks to re-join? → `pair`.

Verify offline, free, no LLM: `mulitaminer segment report.pdf --scanner
<name>` — the block count must equal the report's finding count; iterate on
the config until it does. For the prompt, copy the closest built-in from
`configs/prompts/` and adapt the INPUT FORMAT and field rules, keeping the
`### BLOCK` / `block_id` contract and one worked example.

## OpenVAS (`openvas.json`)

**Marker `^\s*(Critical|High|Medium|Low|Log)\s+\(CVSS:`** — one match line is
one finding. The marker is the `Severity (CVSS: X.Y)` line that sits
immediately ABOVE each `NVT:` line, so the severity header travels with its
NVT. Marking at `NVT:` instead leaves the header in the previous block and
the LLM guesses severity (usually LOG).

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

**`max_vulns_per_chunk: 4`** — empirical calibration.

## Tenable WAS (`tenable.json`)

**Marker `VULNERABILITY <SEV> PLUGIN ID <n>`** (case-insensitive via `(?i)`)
— one match line is one block; a finding appears as TWO consecutive blocks,
Base (Description/Solution/Risk/Plugin Details) and `Name Instances (N)`
(per-URL evidence).

**`name_above_marker: true` + `name_stop_pattern`** — the vulnerability NAME
is the ONE line immediately before the VULNERABILITY header. Names never wrap
(max 56 chars in the ground truth); a multi-line walk-back pollutes names
with the previous block's reference tail (`BID -`, `CVE -`), breaking
pairing. The stop pattern rejects section headers and reference-content lines
as a second guard. Long `<name> Instances (N)` titles DO wrap — the engine
climbs past a lone `(1)`/`Instances` fragment to the real name.

**`pair`** — base + instances blocks are merged by normalized name (with the
`Instances (N)` suffix stripped) and the fields in `by` (`plugin`, Tenable's
stable numeric ID). Pairing is structure, not deduplication: it always runs;
without it every finding is two broken halves.

**`severity_map INFO→LOG`** — both scanners share one informational tier:
a Tenable record is INFO before pairing, LOG after.

**`max_vulns_per_chunk: 3`** — empirical calibration.

## Engine-wide rules (not configurable)

- **Duplicate = fully identical record** (name compared normalized). Same key
  with different content is two real findings and never merges (e.g. OpenVAS
  `Services` legitimately repeats on the same host/port, one record per
  detected service; two distinct plugins can even share a display name).
  Legitimate OpenVAS repeats live on different hosts/ports and are therefore
  never merged; Tenable should have no true duplicates at all — a dedup merge
  in a Tenable run's `merge_log` is an anomaly worth investigating.
- **Oversized single blocks** (e.g. Tenable `Instances (25)` — input alone
  exceeding the model's output budget) are truncated at the input tail with an
  explicit `[TRUNCATED: ...]` marker and a per-block warning: partial data
  beats a dropped finding, and the truncation is declared, never silent.
