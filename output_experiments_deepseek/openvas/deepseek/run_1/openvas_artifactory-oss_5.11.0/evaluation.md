# Evaluation report

- results: `output_experiments\openvas\deepseek\run_1\openvas_artifactory-oss_5.11.0\results.json`
- baseline: `resources\openvas\openvas_artifactory-oss_5.11.0.xlsx`
- source: OPENVAS — threshold 0.7 — text metrics: token_f1, rouge_l, bertscore

## Coverage

- baseline findings: 116
- extracted records: 115
- matched: 115  (recall 0.991, precision 1.000)

## Field scores (measured mean — vacuous empty×empty pairs excluded)

```
field                     exact  set_f1  set_f1_ids  structural  bertscore  rouge_l  token_f1
-----                     -----  ------  ----------  ----------  ---------  -------  --------
name                      -      -       -           -           0.999      1.000    1.000   
description               -      -       -           -           0.953      0.826    0.826   
solution                  -      -       -           -           0.888      0.715    0.715   
impact                    -      -       -           -           0.648      0.645    0.645   
insight                   -      -       -           -           0.864      0.809    0.810   
references                -      0.070   0.303       -           -          -        -       
detection_result          -      -       -           -           0.932      0.887    0.887   
detection_method          -      -       -           -           0.896      0.847    0.847   
product_detection_result  -      -       -           -           0.952      0.905    0.905   
log_method                -      -       -           -           0.862      0.722    0.725   
plugin                    n/a    -       -           -           -          -        -       
plugin_details            -      -       -           n/a         -          -        -       
instances                 -      -       -           -           n/a        n/a      n/a     
cvss                      0.922  -       -           -           -          -        -       
severity                  0.965  -       -           -           -          -        -       
port                      0.887  -       -           -           -          -        -       
protocol                  0.965  -       -           -           -          -        -       
```

`n/a` = every matched pair was empty on both sides for that field (nothing to measure). Inclusive means and per-pair detail live in `evaluation.json`.

## Worst pairs per field

- **name**: Apache Tomcat CORS Filter Setting Security Bypass Vulnerability (0.992); Apache Tomcat CORS Filter Setting Security Bypass Vulnerability (0.992); Apache Tomcat Hostname Verification Security Bypass Vulnerability - Linux (0.994); Apache Tomcat UTF-8 Decoder Denial of Service Vulnerability - Linux (0.994); Apache Tomcat Hostname Verification Security Bypass Vulnerability - Linux (0.994)
- **description**: Apache Tomcat Rewrite Rule Bypass Vulnerability (Apr 2025) - Linux (0.542); Apache Tomcat CORS Filter Setting Security Bypass Vulnerability (0.606); OS Detection Consolidation and Reporting (0.717); Services (0.752); Apache Tomcat Detection Consolidation (0.755)
- **solution**: Apache Tomcat Request Smuggling Vulnerability (Oct 2022) - Linux (0.0); Apache Tomcat DoS Vulnerability (Feb 2023) - Linux (0.0); Apache Tomcat DoS Vulnerability (Feb 2023) - Linux (0.0); Apache Tomcat Multiple Vulnerabilities (Dec 2024) - Linux (0.0); Apache Tomcat HTTP Request Smuggling Vulnerability (Jul 2021) - Linux (0.0)
- **impact**: Apache Tomcat Privilege Escalation Vulnerability (Dec 2019) - Linux (0.0); Apache Tomcat RCE Vulnerability (May 2020) - Linux (0.0); Apache Tomcat DoS Vulnerability (Jul 2024) - Linux (0.0); Apache Tomcat Privilege Escalation Vulnerability (Dec 2019) - Linux (0.0); Apache Tomcat Security Constraint Incorrect Handling Access Bypass Vulnerabilities - Linux (0.0)
- **insight**: Apache Tomcat Information Disclosure Vulnerability (Mar 2021) - Linux (0.0); Apache Tomcat DoS Vulnerability (Jun 2020) - Linux (0.0); Apache Tomcat Request Smuggling Vulnerability (Oct 2022) - Linux (0.0); Apache Tomcat DoS Vulnerability (Feb 2023) - Linux (0.0); Apache Tomcat Open Redirect Vulnerability (Aug 2023) - Linux (0.0)
- **references**: Apache Tomcat Session Fixation Vulnerability (Aug 2025) - Linux (0.0); Apache Tomcat Request Smuggling Vulnerability (Oct 2022) - Linux (0.0); Apache Tomcat RCE Vulnerability (Mar 2021) - Linux (0.0); Apache Tomcat Request Smuggling Vulnerability (Oct 2022) - Linux (0.0); Apache Tomcat Multiple Vulnerabilities (Dec 2024) - Linux (0.0)
- **detection_result**: Apache Tomcat Request Mix-up Vulnerability (May 2022) - Linux (0.0); Apache Tomcat Multiple DoS Vulnerabilities (Jul 2020) - Linux (0.0); Apache Tomcat Hostname Verification Security Bypass Vulnerability - Linux (0.0); Apache Tomcat Clustering DoS Vulnerability (May 2022) (0.0); Services (0.0)
- **detection_method**: Apache Tomcat Multiple Vulnerabilities (Feb 2020) - Linux (0.0); Apache Tomcat Request Smuggling Vulnerability (Oct 2022) - Linux (0.0); Apache Tomcat DoS Vulnerability (Jun 2020) - Linux (0.0); Apache Tomcat Request Smuggling Vulnerability (Oct 2022) - Linux (0.0); Apache Tomcat Open Redirect Vulnerability (Aug 2023) - Linux (0.0)
- **product_detection_result**: Apache Tomcat AJP RCE Vulnerability (Ghostcat) - Active Check (0.0); Apache JServ Protocol (AJP) v1.3 Detection (TCP) (0.0); Apache Tomcat Detection Consolidation (0.0); Apache Tomcat NIO/NIO2 Connectors Information Disclosure Vulnerability - Linux (0.745); Apache Tomcat Multiple Vulnerabilities (Dec 2024) - Linux (0.746)
- **log_method**: Apache Tomcat Multiple Vulnerabilities (Dec 2024) - Linux (0.0); TCP Timestamps Information Disclosure (0.0); HTTP Security Headers Detection (0.258); Allowed HTTP Methods Enumeration (0.447); Hostname Determination Reporting (0.571)
- **cvss**: Apache Tomcat Multiple Vulnerabilities (Feb 2020) - Linux (0.0); Apache Tomcat RCE Vulnerability (May 2020) - Linux (0.0); Apache Tomcat Multiple DoS Vulnerabilities (Jul 2025) - Linux (0.0); Apache Tomcat Information Disclosure Vulnerability (Jan 2021) - Linux (0.0); Apache Tomcat CGI Security Constraint Bypass Vulnerability (May 2025) - Linux (0.0)
- **severity**: Apache Tomcat Multiple Vulnerabilities (Feb 2020) - Linux (0.0); Apache Tomcat RCE Vulnerability (Mar 2025) - Linux (0.0); Apache Tomcat Multiple Vulnerabilities (Dec 2024) - Linux (0.0); Apache Tomcat Information Disclosure Vulnerability (Sep 2022) - Linux (0.0)
- **port**: Apache Tomcat DoS Vulnerability (Jun 2020) - Linux (0.0); TCP Timestamps Information Disclosure (0.0); Apache JServ Protocol (AJP) v1.3 Detection (TCP) (0.0); CPE Inventory (0.0); HTTP Security Headers Detection (0.0)
- **protocol**: Apache Tomcat DoS Vulnerability (Jun 2020) - Linux (0.0); Apache JServ Protocol (AJP) v1.3 Detection (TCP) (0.0); CPE Inventory (0.0); JFrog Artifactory Detection (HTTP) (0.0)

## Missed (in baseline, not extracted)

- ICMP Timestamp Reply Information Disclosure

## Notes

- baseline never fills `plugin`, `plugin_details`, `instances` — scores there only measure presence agreement: 1.0 means the extraction also left the field empty; low values mean it filled a field the ground truth does not annotate.
