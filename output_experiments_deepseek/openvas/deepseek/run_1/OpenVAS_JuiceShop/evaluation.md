# Evaluation report

- results: `output_experiments\openvas\deepseek\run_1\OpenVAS_JuiceShop\results.json`
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
description               -      -       -           -           0.986      0.970    0.970   
solution                  -      -       -           -           0.943      0.775    0.775   
impact                    -      -       -           -           1.000      1.000    1.000   
insight                   -      -       -           -           0.989      0.958    0.958   
references                -      0.375   0.966       -           -          -        -       
detection_result          -      -       -           -           0.988      0.988    0.988   
detection_method          -      -       -           -           0.975      0.969    0.969   
product_detection_result  -      -       -           -           0.923      0.667    0.667   
log_method                -      -       -           -           0.987      0.975    0.975   
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

- **description**: SSL/TLS: Collect and Report Certificate Details (0.667); SSL/TLS: Collect and Report Certificate Details (0.764); Postfix SMTP Server Detection (0.939); SMTP too long line (0.959); OpenVAS / Greenbone Vulnerability Manager Default Credentials (0.961)
- **solution**: Check if Mailserver answer to VRFY and EXPN requests (0.459); SSL/TLS: Certificate Expired (0.822); SSL/TLS: Certificate Expired (0.822); SMTP antivirus scanner DoS (0.828); OpenVAS / Greenbone Vulnerability Manager Default Credentials (0.874)
- **insight**: OpenVAS / Greenbone Vulnerability Manager Default Credentials (0.904); SSL/TLS: Certificate Expired (0.967); SSL/TLS: Certificate Expired (0.967); Check if Mailserver answer to VRFY and EXPN requests (0.97)
- **references**: SSL/TLS: HTTP Strict Transport Security (HSTS) Missing (0.364); Check if Mailserver answer to VRFY and EXPN requests (0.5); CGI Scanning Consolidation (0.5); HTTP Security Headers Detection (0.5); SSL/TLS: HTTP Public Key Pinning (HPKP) Missing (0.5)
- **detection_result**: Service Detection with '<xml/>' Request (0.93); wapiti (NASL wrapper) (0.941); SMTP Server type and version (0.948); Greenbone Security Assistant (GSA) Detection (0.949); SSL/TLS: Collect and Report Certificate Details (0.965)
- **detection_method**: SSL/TLS: Certificate Expired (0.857); OpenVAS / Greenbone Vulnerability Manager Default Credentials (0.992); SSL/TLS: Certificate Expired (0.992); SMTP too long line (0.993); Check if Mailserver answer to VRFY and EXPN requests (0.993)
- **product_detection_result**: OpenVAS / Greenbone Vulnerability Manager Default Credentials (0.752)
- **log_method**: wapiti (NASL wrapper) (0.801); Traceroute (0.821); SSL/TLS: HTTP Public Key Pinning (HPKP) Missing (0.923); SSL/TLS: Report Medium Cipher Suites (0.923); Services (0.992)
- **cvss**: Services (0.0)
- **port**: SSL/TLS: Report Non Weak Cipher Suites (0.0); SSL/TLS: Report Supported Cipher Suites (0.0)
- **protocol**: CPE Inventory (0.0)

## Notes

- baseline never fills `plugin`, `plugin_details`, `instances` — scores there only measure presence agreement: 1.0 means the extraction also left the field empty; low values mean it filled a field the ground truth does not annotate.
