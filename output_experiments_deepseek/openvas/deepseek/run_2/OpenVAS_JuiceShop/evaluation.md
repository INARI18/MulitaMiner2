# Evaluation report

- results: `output_experiments\openvas\deepseek\run_2\OpenVAS_JuiceShop\results.json`
- baseline: `resources\openvas\OpenVAS_JuiceShop.xlsx`
- source: OPENVAS — threshold 0.7 — text metrics: token_f1, rouge_l, bertscore

## Coverage

- baseline findings: 34
- extracted records: 34
- matched: 34  (recall 1.000, precision 1.000)

## Field scores (measured mean — vacuous empty×empty pairs excluded)

```
field                     exact  set_f1  set_f1_ids  structural  bertscore  rouge_l  token_f1
-----                     -----  ------  ----------  ----------  ---------  -------  --------
name                      -      -       -           -           1.000      1.000    1.000   
description               -      -       -           -           0.985      0.968    0.968   
solution                  -      -       -           -           0.944      0.775    0.775   
impact                    -      -       -           -           1.000      1.000    1.000   
insight                   -      -       -           -           0.986      0.946    0.946   
references                -      0.375   1.000       -           -          -        -       
detection_result          -      -       -           -           0.987      0.986    0.986   
detection_method          -      -       -           -           0.644      0.617    0.617   
product_detection_result  -      -       -           -           0.923      0.667    0.667   
log_method                -      -       -           -           0.989      0.988    0.988   
plugin                    n/a    -       -           -           -          -        -       
plugin_details            -      -       -           n/a         -          -        -       
instances                 -      -       -           -           n/a        n/a      n/a     
cvss                      0.971  -       -           -           -          -        -       
severity                  1.000  -       -           -           -          -        -       
port                      0.941  -       -           -           -          -        -       
protocol                  0.971  -       -           -           -          -        -       
```

`n/a` = every matched pair was empty on both sides for that field (nothing to measure). Inclusive means and per-pair detail live in `evaluation.json`.

## Worst pairs per field

- **description**: SSL/TLS: Collect and Report Certificate Details (0.669); SSL/TLS: Collect and Report Certificate Details (0.764); Postfix SMTP Server Detection (0.939); SMTP too long line (0.957); Traceroute (0.959)
- **solution**: Check if Mailserver answer to VRFY and EXPN requests (0.459); SSL/TLS: Certificate Expired (0.822); SSL/TLS: Certificate Expired (0.822); SMTP antivirus scanner DoS (0.828); OpenVAS / Greenbone Vulnerability Manager Default Credentials (0.874)
- **insight**: OpenVAS / Greenbone Vulnerability Manager Default Credentials (0.849); SSL/TLS: Certificate Expired (0.967); SSL/TLS: Certificate Expired (0.967); Check if Mailserver answer to VRFY and EXPN requests (0.97)
- **references**: Check if Mailserver answer to VRFY and EXPN requests (0.5); CGI Scanning Consolidation (0.5); HTTP Security Headers Detection (0.5); SSL/TLS: HTTP Public Key Pinning (HPKP) Missing (0.5); SSL/TLS: HTTP Strict Transport Security (HSTS) Missing (0.5)
- **detection_result**: wapiti (NASL wrapper) (0.941); SMTP Server type and version (0.945); Greenbone Security Assistant (GSA) Detection (0.949); CGI Scanning Consolidation (0.952); SSL/TLS: Collect and Report Certificate Details (0.965)
- **detection_method**: CGI Scanning Consolidation (0.0); Greenbone Security Assistant (GSA) Detection (0.0); HTTP Security Headers Detection (0.0); SSL/TLS: Certificate Expired (0.857); SSL/TLS: Certificate Expired (0.896)
- **product_detection_result**: OpenVAS / Greenbone Vulnerability Manager Default Credentials (0.752)
- **log_method**: SSL/TLS: HTTP Public Key Pinning (HPKP) Missing (0.911); wapiti (NASL wrapper) (0.912); SSL/TLS: Report Medium Cipher Suites (0.923); Services (0.992); Services (0.992)
- **cvss**: Services (0.0)
- **port**: SSL/TLS: Report Non Weak Cipher Suites (0.0); SSL/TLS: Report Supported Cipher Suites (0.0)
- **protocol**: CPE Inventory (0.0)

## Notes

- baseline never fills `plugin`, `plugin_details`, `instances` — scores there only measure presence agreement: 1.0 means the extraction also left the field empty; low values mean it filled a field the ground truth does not annotate.
