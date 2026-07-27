from mulitaminer.models import Block, VulnRecord
from mulitaminer.negation import gate_records


def _setup(block_text: str, **fields) -> tuple[dict, dict]:
    record = VulnRecord(name="Finding", severity="High", **fields)
    block = Block(id=0, text=block_text)
    return {0: record}, {0: block}


def test_dropped_negation_is_flagged():
    records, blocks = _setup(
        "The service is not vulnerable to CVE-2024-1. Update is optional.",
        description=["The service is vulnerable to CVE-2024-1."],
    )
    flags = gate_records(records, blocks, confirm=False)
    assert len(flags) == 1
    f = flags[0]
    assert f["kind"] == "dropped"
    assert f["field"] == "description"
    assert f["block_id"] == 0
    assert f["nli_score"] is None  # confirm=False leaves it unscored


def test_invented_negation_is_flagged():
    records, blocks = _setup(
        "The service is vulnerable to CVE-2024-1.",
        description=["The service is not vulnerable to CVE-2024-1."],
    )
    flags = gate_records(records, blocks, confirm=False)
    assert [f["kind"] for f in flags] == ["invented"]


def test_symmetric_cues_do_not_flag():
    records, blocks = _setup(
        "No known exploits are available for this issue.",
        description=["No known exploits are available for this issue."],
    )
    assert gate_records(records, blocks, confirm=False) == []


def test_lexical_cue_asymmetry_is_flagged():
    # "fails to" on the source side, dropped in the extraction
    records, blocks = _setup(
        "The server fails to validate the certificate chain.",
        description=["The server validates the certificate chain."],
    )
    flags = gate_records(records, blocks, confirm=False)
    assert [f["kind"] for f in flags] == ["dropped"]


def test_unrelated_sentences_do_not_flag():
    # cue present but the sentences describe different things: no alignment
    records, blocks = _setup(
        "The FTP banner reveals the product version.",
        description=["Authentication is not enforced on the admin panel."],
    )
    assert gate_records(records, blocks, confirm=False) == []


def test_skip_fields_are_ignored():
    records, blocks = _setup(
        "The service is not vulnerable to CVE-2024-1.",
        references=["https://example.org/not-a-vulnerability"],
    )
    assert gate_records(records, blocks, confirm=False) == []


def test_hard_wrap_does_not_split_sentences():
    # the negation lives across a hard-wrapped line; still one sentence
    records, blocks = _setup(
        "The certificate is self-signed and was not\nfound in the list of authorities.",
        description=["The certificate is self-signed and was found in the list of authorities."],
    )
    flags = gate_records(records, blocks, confirm=False)
    assert [f["kind"] for f in flags] == ["dropped"]
