"""Writers: schema-derived columns, round-trippable JSON."""
import json

from mulitaminer2.models import OpenVASRecord
from mulitaminer2.writers import columns_for, write_csv, write_json, write_xlsx

RECORDS = [
    OpenVASRecord(name="A", severity="HIGH", cvss=7.5, port=443, protocol="tcp",
                  description=["first", "second"]),
    OpenVASRecord(name="B", severity="LOG", cvss=0.0),
]


def test_columns_derived_from_schema_include_severity():
    cols = columns_for(OpenVASRecord)
    assert "Name" in cols and "severity" in cols and "source" in cols


def test_json_round_trip(tmp_path):
    out = tmp_path / "results.json"
    write_json(RECORDS, out)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[0]["Name"] == "A"
    assert data[0]["severity"] == "HIGH"
    assert data[1]["cvss"] == 0.0
    assert data[0]["source"] == "OPENVAS"


def test_xlsx_and_csv_write(tmp_path):
    import pandas as pd

    write_xlsx(RECORDS, OpenVASRecord, tmp_path / "r.xlsx")
    write_csv(RECORDS, OpenVASRecord, tmp_path / "r.csv")
    df = pd.read_excel(tmp_path / "r.xlsx")
    assert list(df.columns) == columns_for(OpenVASRecord)
    assert df.iloc[0]["Name"] == "A"
    # list fields are newline-joined in tabular formats
    assert df.iloc[0]["description"] == "first\nsecond"
