"""Compare PDF backends on the baseline reports: marker counts per backend.

The scanner marker count is the ground truth proxy — each marker line is one
finding occurrence. The backend whose text yields marker counts matching the
known baseline counts (and does it faster) wins the default slot.

Usage: uv run python tools/compare_backends.py
"""
import re
import time
from pathlib import Path

from mulitaminer2.reader import BACKENDS, extract_pdf

MARKERS = {
    "openvas": re.compile(r"^\s*(?:Critical|High|Medium|Low|Log)\s+\(CVSS:", re.MULTILINE),
    "tenable": re.compile(
        r"VULNERABILITY\s+(CRITICAL|HIGH|MEDIUM|LOW|INFO)\s+PLUGIN\s+ID\s+\d+", re.IGNORECASE
    ),
}


def main() -> None:
    baselines = Path("resources")
    rows = []
    for scanner, marker in MARKERS.items():
        for pdf in sorted((baselines / scanner).glob("*.pdf")):
            for backend in BACKENDS:
                start = time.perf_counter()
                try:
                    doc = extract_pdf(pdf, backend=backend)
                    elapsed = time.perf_counter() - start
                    count = len(marker.findall(doc.text))
                    rows.append((pdf.name, backend, count, len(doc.text), f"{elapsed:.1f}s"))
                except Exception as exc:  # a backend failing IS the result here
                    rows.append((pdf.name, backend, "ERROR", str(exc)[:60], "-"))

    width = max(len(r[0]) for r in rows) + 2
    print(f"{'PDF':<{width}}{'backend':<12}{'markers':<9}{'chars':<10}{'time'}")
    for name, backend, count, chars, elapsed in rows:
        print(f"{name:<{width}}{backend:<12}{count!s:<9}{chars!s:<10}{elapsed}")


if __name__ == "__main__":
    main()
