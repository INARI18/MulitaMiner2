"""Build a baseline XLSX from a Nessus "Vulnerabilities by Host" HTML report.

The HTML export carries the same fields as the (trial-locked) CSV export, so it
is the ground truth for the paired PDF. Field mapping follows the OpenVAS
baseline semantics: Nessus Synopsis is a one-line summary like OpenVAS Summary
(-> description), and Nessus Description is the deeper explanation like OpenVAS
Vulnerability Insight (-> insight).

Usage: uv run python tools/nessus_html_to_baseline.py <report.html> <out.xlsx>
"""
import html
import json
import re
import sys
from pathlib import Path

import openpyxl

# Nessus record columns in schema order (no foreign union columns).
COLUMNS = [
    "Name", "description", "solution", "impact", "references", "severity",
    "host", "port", "protocol", "source", "cvss", "insight", "detection_result",
    "plugin", "plugin_details",
]

HOST_RE = re.compile(
    r'<div xmlns="" id="id\d+" style="font-size: 22px[^>]*>([0-9.]+)<')
HEAD_RE = re.compile(r"onclick=\"toggleSection\('id\d+-container'\);\"[^>]*>(\d+) - ([^<]+)<")
PORT_RE = re.compile(r"<h2>([^<]+)</h2>")
# monospace block right after the port heading holds the plugin output
OUTPUT_RE = re.compile(r"font-family: monospace;[^\"]*\">(.*?)<div class=\"clear\">", re.S)


def text(fragment: str) -> str:
    """HTML fragment -> plain text, <br> becoming newlines."""
    s = re.sub(r"<br\s*/?>", "\n", fragment)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def _severity(risk: str) -> str:
    """Nessus Risk Factor -> the shared Severity literal, source-faithful:
    Critical/High/Medium/Low/None just uppercase (None -> NONE)."""
    return risk.upper()


def paragraphs(fragment: str) -> list[str]:
    """Split a field into the paragraph list the baseline schema expects."""
    body = text(fragment)
    return [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]


def field(segment: str, label: str) -> str | None:
    m = re.search(
        re.escape(label) + r'<div class="clear"></div>\s*</div>\s*'
        r'<div[^>]*>(.*?)<div class="clear">', segment, re.S)
    return m.group(1) if m else None


def table_rows(segment: str, label: str) -> list[str]:
    """See Also / References render as a table instead of a plain div."""
    m = re.search(
        re.escape(label) + r'<div class="clear"></div>\s*</div>\s*'
        r'<div[^>]*class="table-wrapper see-also">(.*?)</table>', segment, re.S)
    if not m:
        return []
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.S):
        cells = [text(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        cells = [c for c in cells if c]
        if cells:
            out.append(" ".join(cells))
    return out


def parse(path: Path) -> list[dict]:
    raw = open(path, encoding="utf-8", errors="replace").read()
    body = raw[raw.find('id="id1"'):]

    hosts = [(m.start(), m.group(1)) for m in HOST_RE.finditer(body)]
    bounds = [m.start() for m in HEAD_RE.finditer(body)] + [len(body)]

    def owner(pos: int) -> str:
        cur = ""
        for start, ip in hosts:
            if start < pos:
                cur = ip
            else:
                break
        return cur

    rows = []
    for i in range(len(bounds) - 1):
        seg = body[bounds[i]:bounds[i + 1]]
        head = HEAD_RE.search(seg)
        plugin_id, name = head.group(1), head.group(2).strip()

        proto, port = "", ""
        if p := PORT_RE.search(seg):
            parts = p.group(1).split("/")
            proto, port = parts[0], (parts[1] if len(parts) > 1 else "")

        cvss = []
        for label in ("CVSS v2.0 Base Score", "CVSS v2.0 Temporal Score",
                      "CVSS v3.0 Base Score", "CVSS v3.0 Temporal Score"):
            if v := field(seg, label):
                cvss.append(f"{label} {text(v)}")

        # Plugin Information is always "Published: <date>, Modified: <date>".
        details = {"plugin_id": int(plugin_id)}
        if info := field(seg, "Plugin Information"):
            keys = {"published": "publication_date", "modified": "modification_date"}
            for part in text(info).split(","):
                if ":" in part:
                    k, v = part.split(":", 1)
                    if key := keys.get(k.strip().lower()):
                        details[key] = v.strip()

        out_block = OUTPUT_RE.search(seg)
        risk = field(seg, "Risk Factor")

        rows.append({
            "Name": name,
            "description": paragraphs(field(seg, "Synopsis") or ""),
            "solution": paragraphs(field(seg, "Solution") or ""),
            "impact": [],
            "references": table_rows(seg, "See Also") + table_rows(seg, "References"),
            "severity": _severity(text(risk)) if risk else "",
            "host": owner(bounds[i]),
            "port": port,
            "protocol": proto,
            "source": "NESSUS",
            "cvss": cvss,
            "insight": paragraphs(field(seg, "Description") or ""),
            "detection_result": paragraphs(out_block.group(1)) if out_block else [],
            "detection_method": [],
            "product_detection_result": [],
            "log_method": [],
            "plugin_details": json.dumps(details) if details else "",
            "instances": [],
            "plugin": int(plugin_id),
        })
    return rows


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    rows = parse(src)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(COLUMNS)
    for r in rows:
        ws.append([r[c] if isinstance(r[c], (int, str)) else str(r[c]) for c in COLUMNS])
    wb.save(dst)

    hosts = len({r["host"] for r in rows})
    plugins = len({r["plugin"] for r in rows})
    print(f"{dst.name}: {len(rows)} findings, {hosts} hosts, {plugins} plugin IDs")


if __name__ == "__main__":
    main()
