# Evaluation baselines

Each `<stem>.xlsx` is the ground truth for the sibling `<stem>.pdf`, in the
record-model column layout the evaluator expects.

Provenance: baselines are derived from the scanner's own machine export
(OpenVAS CSV, Qualys CSV, Nessus HTML, ZAP XML) wherever one exists; the
generators live in the training repository
(<https://github.com/INARI18/Mulita-Training>, `src/sources/` +
`src/make_heldout_baselines.py`). Tenable/Acunetix have no export and their
baselines are hand-made. All baselines are trimmed to input-faithfulness by
`tools/trim_baselines.py`: text the PDF layout never renders is removed, so
the ruler never demands content the extractor cannot see.
