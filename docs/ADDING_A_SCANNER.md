# Adding a Scanner — Step by Step

No Python needed: a scanner is one JSON config + one prompt file. This guide
takes you from a new scanner's PDF to a working config.

## 0. What you need

- A PDF report from the scanner, ideally one where you know how many findings
  it contains.
- 15 minutes. Every step below is testable offline — no LLM calls, no cost —
  using `mulitaminer2 segment`.

## 1. Create the files

Make a folder anywhere (e.g. `my-scanners/`) and create:

```
my-scanners/
├── acmescan.json
└── acmescan_prompt.txt
```

Point the tool at it:

```bash
# Windows (PowerShell): $env:MULITAMINER2_SCANNERS_DIR = "C:\path\to\my-scanners"
export MULITAMINER2_SCANNERS_DIR=/path/to/my-scanners
uv run mulitaminer2 scanners   # "acmescan" should now be listed
```

## 2. Find the marker (the only mandatory decision)

Open the report and look at two or three findings. There is always a line
that starts every finding — a severity header, a rule id, a plugin line.
That line is your `marker_pattern`: **one match = one finding**.

Start minimal:

```json
{
  "name": "acmescan",
  "source": "ACMESCAN",
  "prompt": "acmescan_prompt.txt",
  "max_vulns_per_chunk": 4,
  "marker_pattern": "^FINDING\\s+(CRITICAL|HIGH|MEDIUM|LOW)\\b"
}
```

If the pattern has a capture group 1, it is used as the severity hint.
Add `(?i)` at the start for case-insensitive matching.

Now test — this is the core loop you will repeat:

```bash
uv run mulitaminer2 segment report.pdf --scanner acmescan
```

It prints how many blocks were found and a preview of the first ones.
**The block count must equal the report's finding count.** Too many blocks →
your marker also matches summary/TOC lines (anchor it more, e.g. `^\s*`
plus something unique). Too few → the marker line varies (check case,
spacing, wrapped lines).

## 3. Two questions decide the optional keys

**Q1 — Does the finding's name sit OUTSIDE the block, on the line above the
marker?** (Tenable does this.)
→ add `"name_above_marker": true`, and if the line above is sometimes
content from the previous finding (references, URLs), list those shapes in
`"name_stop_pattern"`. Check with `segment`: the first line of each block
preview must be the finding's name.

**Q2 — Does information VALID FOR SEVERAL findings appear above them, rather
than inside each one?** (OpenVAS does this: `High 443/tcp` port headers, one
host line for the whole report.)
→ add a `"context"` object with `header_patterns` (regexes with named groups
`sev` / `port` / `proto`) and/or `host_anchor` + `host_line`. The engine
tracks the latest match while scanning and attaches it to each block —
`segment` shows the captured host/port per block so you can verify.

**Q3 — Is ONE finding printed as TWO OR MORE blocks that must be re-joined?**
(Tenable prints a Base block + an `Instances (N)` block.)
→ add a `"pair"` object: `strip_name_suffix` (regex removing the suffix that
differs between the halves) and `by` (the field(s) that identify the pair,
e.g. a plugin/rule id). Pairing always runs — it is structure, not
deduplication.

Most scanners need none or one of these. Use `docs/SCANNER_CONFIGS.md` to see
how the built-ins answered the three questions and why.

## 4. Write the prompt

Copy the built-in prompt closest to your scanner
(`src/mulitaminer2/configs/prompts/`) and adapt:

- the INPUT FORMAT section to your report's section headers;
- the field rules (where does the name come from? where does the score live?);
- keep the OUTPUT CONTRACT part untouched — the `### BLOCK n` / `block_id`
  mechanics are what the pipeline enforces;
- keep one worked example (input block → expected object). Examples measurably
  improve extraction quality.

## 5. First real run

```bash
uv run mulitaminer2 extract report.pdf --scanner acmescan --model deepseek --debug
```

`--debug` writes `blocks.txt` and the raw LLM traffic into the run directory —
if a field comes out wrong, look there first: is the information inside the
block (prompt problem) or missing from it (segmentation problem)?

Check `run.json`: `raw_record_count` should equal the block count, and
`merge_log` should be empty unless your report genuinely repeats findings.
