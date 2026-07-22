# Evaluation report

- results: `output_experiments\tenable\deepseek\run_3\TenableWAS_bWAAP\results.json`
- baseline: `resources\tenable\TenableWAS_bWAAP.xlsx`
- source: TENABLEWAS — threshold 0.7 — text metrics: token_f1, rouge_l, bertscore

## Coverage

- baseline findings: 64
- extracted records: 64
- matched: 64  (recall 1.000, precision 1.000)

## Field scores (measured mean — vacuous empty×empty pairs excluded)

```
field                     exact  set_f1  set_f1_ids  structural  bertscore  rouge_l  token_f1
-----                     -----  ------  ----------  ----------  ---------  -------  --------
name                      -      -       -           -           1.000      1.000    1.000   
description               -      -       -           -           0.990      0.983    0.983   
solution                  -      -       -           -           0.992      1.000    1.000   
impact                    -      -       -           -           n/a        n/a      n/a     
insight                   -      -       -           -           n/a        n/a      n/a     
references                -      1.000   1.000       -           -          -        -       
detection_result          -      -       -           -           n/a        n/a      n/a     
detection_method          -      -       -           -           n/a        n/a      n/a     
product_detection_result  -      -       -           -           n/a        n/a      n/a     
log_method                -      -       -           -           n/a        n/a      n/a     
plugin                    1.000  -       -           -           -          -        -       
plugin_details            -      -       -           1.000       -          -        -       
instances                 -      -       -           0.862       -          -        -       
cvss                      -      1.000   1.000       -           -          -        -       
severity                  1.000  -       -           -           -          -        -       
port                      n/a    -       -           -           -          -        -       
protocol                  n/a    -       -           -           -          -        -       
```

`n/a` = every matched pair was empty on both sides for that field (nothing to measure). Inclusive means and per-pair detail live in `evaluation.json`.

## Worst pairs per field

- **description**: Interesting Response (0.563); Virtual Hosts Detected (0.671); Blind SQL Injection (differential analysis) (0.986); Missing 'X-Content-Type-Options' Header (0.988); jQuery 1.2.0 < 3.5.0 Cross-Site Scripting (0.989)
- **solution**: Blind SQL Injection (differential analysis) (0.989); Missing Permissions Policy (0.99); Path Relative Stylesheet Import (0.99); Allowed HTTP Methods (0.991); Missing Referrer Policy (0.991)
- **plugin_details**: Scan Information (0.971)
- **instances**: Unvalidated Redirection (0.0); HTTP Header Information Disclosure (0.32); Missing HTTP Strict Transport Security Policy (0.324); Missing Referrer Policy (0.388); Insecure 'Access-Control-Allow-Origin' Header (0.396)

## Notes

- `instances`, `cvss`, `references` ground truth taken from `resources\tenable\TenableWAS_bWAAP_instances_generated.xlsx` (deterministic re-annotation from the PDF).
- baseline never fills `impact`, `insight`, `detection_result`, `detection_method`, `product_detection_result`, `log_method`, `port`, `protocol` — scores there only measure presence agreement: 1.0 means the extraction also left the field empty; low values mean it filled a field the ground truth does not annotate.
