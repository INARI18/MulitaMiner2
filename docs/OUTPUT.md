# Output reference

Every field the tool emits, and what it means. For where the files land see
[USAGE.md](USAGE.md#run-artifacts); for export formats see [EXPORTS.md](EXPORTS.md).

A run produces three things worth reading: the extracted **records**
(`results.json` / `results.xlsx`), the run **metadata** (`run.json`), and, if you
evaluate, the **scores** (`evaluation.json` / `evaluation.md`).

## The extracted record

One object per finding. `results.json` is the list; `results.xlsx` is the same
data as a sheet. Columns are the **union across all scanners**, so every file has
the same shape; a scanner leaves the columns it does not fill empty.

| Field | Type | Filled by | Meaning |
| --- | --- | --- | --- |
| `Name` | str | all | The finding/plugin name, verbatim. |
| `description` | list[str] | all | The short summary (one paragraph per element). Nessus Synopsis, OpenVAS Summary. |
| `solution` | list[str] | all | Remediation text. |
| `impact` | list[str] | all | Consequence of the finding. Empty for Nessus (no Impact section). |
| `references` | list[str] | all | External ids/links: `CVE ...`, `XREF CWE:...`, BID, URLs. One per element. |
| `severity` | enum | all | `CRITICAL/HIGH/MEDIUM/LOW` plus each scanner's informational word: `LOG` (OpenVAS), `INFO` (Tenable), `NONE` (Nessus). Source word, never derived from CVSS. |
| `host` | str \| None | all | The scanned host. Recovered from the report layout, never asked of the LLM. |
| `port` | int \| str \| None | all | Port number; `0` means host-wide, a real value (not null). |
| `protocol` | str \| None | all | `tcp` / `udp` / `icmp` / ...; free string so non-tcp/udp survives. `None` when there is no port line. |
| `source` | str | all | The scanner: `NESSUS`, `OPENVAS`, `TENABLEWAS`, `QUALYS`. Stamped, never prompted. |
| `cvss` | see note | nessus, openvas, tenable | The CVSS score(s). **Type differs by scanner** (see below). |
| `insight` | list[str] | nessus, openvas | The deeper explanation. Nessus Description, OpenVAS Vulnerability Insight. |
| `detection_result` | list[str] | nessus, openvas | Evidence the scanner saw (Nessus Plugin Output, OpenVAS Detection Result). |
| `plugin` | int \| None | nessus, qualys, tenable | The scanner's native finding id (Nessus/Tenable plugin id, Qualys QID). OpenVAS has none. |
| `plugin_details` | object | nessus, tenable | `{publication_date, modification_date, plugin_id, ...}`. |
| `detection_method` | list[str] | openvas | How OpenVAS detected it (OID line). |
| `product_detection_result` | list[str] | openvas | OpenVAS product-detection block. |
| `log_method` | list[str] | openvas | OpenVAS log-method block. |
| `category` | str | qualys | Qualys finding category (CGI, Web server, ...). |
| `instances` | list[object] | tenable | Tenable WAS per-URL instances the finding was seen on. |

### cvss carries a different type per scanner

This is deliberate, to stay faithful to each source:

- **OpenVAS** emits one numeric score, so `cvss` is a **number** (`9.8`).
- **Nessus / Tenable** emit several CVSS lines (v2 base, v3 base, vectors), so
  `cvss` is a **list of strings** (`["CVSS v3.0 Base Score 6.5 (CVSS:3.0/...)", ...]`).

The types never mix within a scanner. They only coexist as text in a combined
sheet. A dataset that pools scanners should carry the `source` column so the
per-scanner type is recoverable.

### Example (Nessus)

```json
{
  "Name": "IP Forwarding Enabled",
  "description": ["The remote host has IP forwarding enabled."],
  "insight": ["The remote host has IP forwarding enabled. An attacker can exploit this to route packets through the host and potentially bypass some firewalls / routers / NAC filtering."],
  "solution": ["On Linux, you can disable IP forwarding by doing :", "echo 0 > /proc/sys/net/ipv4/ip_forward"],
  "impact": [],
  "references": ["CVE CVE-1999-0511"],
  "severity": "MEDIUM",
  "host": "172.30.14.2",
  "port": 0,
  "protocol": "tcp",
  "source": "NESSUS",
  "cvss": ["CVSS v3.0 Base Score 6.5 (CVSS:3.0/AV:A/AC:L/PR:L/UI:N/S:C/C:L/I:L/A:L)", "CVSS v2.0 Base Score 5.8 (CVSS2#AV:A/AC:L/Au:N/C:P/I:P/A:P)"],
  "plugin": 50686,
  "plugin_details": {"publication_date": "2010/11/23", "modification_date": "2023/10/17", "plugin_id": 50686}
}
```

Inspect the effective schema any time with `mulitaminer schema`.

## run.json

Run metadata, one per run.

| Key | Meaning |
| --- | --- |
| `config` | Snapshot of the run's inputs (model, scanner, formats, ...). |
| `block_count` | Findings the segmenter produced from the PDF. |
| `raw_record_count` | Records before consolidation. |
| `final_record_count` | Records after consolidation (duplicate merges). |
| `usage` | Tokens (prompt/completion), API calls, cost in USD. |
| `duration_s` | Wall-clock seconds. |
| `warnings` | Human-readable strings for every drop, truncation, and validation miss. |
| `drops` | block_id reconciliation drops by category (see below). Absent/empty on a clean run. |
| `merge_log` | What consolidation merged, one line per merge. |
| `negation_flags` | Flip candidates from the negation gate: extracted sentences whose negation cues disagree with the source block. Each flag has `block_id`, `field`, `kind` (`dropped`/`invented`), the two sentences, `overlap`, and `nli_score` (close to 0 = contradiction confirmed by the NLI model; `null` when the eval deps are not installed). Flag-only: the record itself is not changed. |
| `pdf` | `{pages, backend}` of the PDF read. |

### drops

The block_id loop rejects any LLM output that does not map to a real input
block, so hallucinations cannot slip in. What it drops is counted here:

| Category | Meaning |
| --- | --- |
| `unknown_id` | The LLM returned a block_id that was not in the chunk (invented or wrong). |
| `duplicate_id` | The LLM returned the same block_id twice; the later copy is dropped. |
| `validation_error` | The record failed schema validation; the block is retried. |
| `unrecovered` | A block produced no record after all retry rounds: real data loss. |

A high `unknown_id`/`duplicate_id` means the model does not respect the contract;
useful for comparing models and prompts. A clean run has no `drops` key.

## Evaluation output

`evaluate` (or `experiment`, which evaluates each run) writes `evaluation.json`
(machine) and `evaluation.md` (human). The markdown has:

- **Coverage**: baseline vs extracted counts, `matched`, `recall`, `precision`,
  and false negatives/positives.
- **block_id drops**: the same tally from run.json, if any.
- **Field scores**: the measured mean per field per metric (see
  [EVALUATION.md](EVALUATION.md#per-field-metrics) for which metric each field
  gets and what each measures). `n/a` = every matched pair was empty on both
  sides, so there was nothing to measure.
- **Worst pairs per field**: the lowest-scoring matches, for eyeballing misses.
- **False negatives / positives**: findings in the baseline but not extracted,
  and vice versa, classified by likely cause.

Coverage is the honest headline; per-field scores say how faithful the content
of matched findings is. Read both, and read them stratified: an aggregate mean
hides a class that is 80% of the data (Nessus is ~83% informational).
