# Evaluation report

- results: `output_experiments\tenable\deepseek\run_3\TenableWAS_JuiceShop\results.json`
- baseline: `resources\tenable\TenableWAS_JuiceShop.xlsx`
- source: TENABLEWAS — threshold 0.7 — text metrics: token_f1, rouge_l, bertscore

## Coverage

- baseline findings: 76
- extracted records: 76
- matched: 76  (recall 1.000, precision 1.000)

## Field scores (measured mean — vacuous empty×empty pairs excluded)

```
field                     exact  set_f1  set_f1_ids  structural  bertscore  rouge_l  token_f1
-----                     -----  ------  ----------  ----------  ---------  -------  --------
name                      -      -       -           -           1.000      1.000    1.000   
description               -      -       -           -           0.978      0.952    0.953   
solution                  -      -       -           -           0.801      0.795    0.795   
impact                    -      -       -           -           n/a        n/a      n/a     
insight                   -      -       -           -           n/a        n/a      n/a     
references                -      0.998   0.996       -           -          -        -       
detection_result          -      -       -           -           n/a        n/a      n/a     
detection_method          -      -       -           -           n/a        n/a      n/a     
product_detection_result  -      -       -           -           n/a        n/a      n/a     
log_method                -      -       -           -           n/a        n/a      n/a     
plugin                    1.000  -       -           -           -          -        -       
plugin_details            -      -       -           0.000       -          -        -       
instances                 -      -       -           0.889       -          -        -       
cvss                      -      1.000   1.000       -           -          -        -       
severity                  0.974  -       -           -           -          -        -       
port                      n/a    -       -           -           -          -        -       
protocol                  n/a    -       -           -           -          -        -       
```

`n/a` = every matched pair was empty on both sides for that field (nothing to measure). Inclusive means and per-pair detail live in `evaluation.json`.

## Worst pairs per field

- **description**: Apache 2.4.x < 2.4.43 Multiple Vulnerabilities (0.35); Interesting Response  (0.352); Apache 2.4.x < 2.4.55 Multiple Vulnerabilities (0.439); Apache 2.4.x < 2.4.62 Multiple Vulnerabilities (0.649); Web.config File Information Disclosure (0.828)
- **solution**: Cookies Collected (0.0); Target Information (0.0); Screenshot (0.0); Form Detected (0.0); External URLs (0.0)
- **references**: Apache 2.4.x < 2.4.48 Multiple Vulnerabilities (0.962); Apache 2.4.x < 2.4.16 Multiple Vulnerabilities (0.971); Apache 2.4.x < 2.4.25 Multiple Vulnerabilities (httpoxy) (0.979); Apache 2.4.x < 2.4.60 Multiple Vulnerabilities (0.984); Apache 2.4.x < 2.4.54 Multiple Vulnerabilities (0.986)
- **plugin_details**: PHP Unsupported Version (0.0); Apache 2.4.x < 2.4.41 Multiple Vulnerabilities (0.0); Apache 2.4.x < 2.4.26 Multiple Vulnerabilities (0.0); Apache 2.4.x < 2.4.27 Multiple Vulnerabilities (0.0); Apache 2.4.x < 2.4.33 Multiple Vulnerabilities (0.0)
- **instances**: HTTP Header Information Disclosure (0.0); SSL/TLS Server Cipher Suite Preference Not Detected (0.0); Allowed HTTP Versions (0.0); Missing HTTP Strict Transport Security Policy (0.464); Missing Content Security Policy (0.491)
- **severity**: Apache 2.4.x < 2.4.35 Denial of Service (0.0); Apache 2.4.x < 2.4.43 Multiple Vulnerabilities (0.0)

## Notes

- `instances`, `cvss`, `references` ground truth taken from `resources\tenable\TenableWAS_JuiceShop_instances_generated.xlsx` (deterministic re-annotation from the PDF).
- baseline never fills `impact`, `insight`, `detection_result`, `detection_method`, `product_detection_result`, `log_method`, `plugin_details`, `port`, `protocol` — scores there only measure presence agreement: 1.0 means the extraction also left the field empty; low values mean it filled a field the ground truth does not annotate.
- baseline columns outside the record schema (not scored): `http_info`, `identification`
