# Evaluation report

- results: `output_experiments\openvas\deepseek\run_2\OpenVAS_bBWA\results.json`
- baseline: `resources\openvas\OpenVAS_bBWA.xlsx`
- source: OPENVAS — threshold 0.7 — text metrics: token_f1, rouge_l, bertscore

## Coverage

- baseline findings: 58
- extracted records: 59
- matched: 58  (recall 1.000, precision 0.983)

## Field scores (measured mean — vacuous empty×empty pairs excluded)

```
field                     exact  set_f1  set_f1_ids  structural  bertscore  rouge_l  token_f1
-----                     -----  ------  ----------  ----------  ---------  -------  --------
name                      -      -       -           -           1.000      1.000    1.000   
description               -      -       -           -           0.988      0.974    0.974   
solution                  -      -       -           -           0.953      0.905    0.905   
impact                    -      -       -           -           0.931      0.916    0.916   
insight                   -      -       -           -           0.893      0.883    0.883   
references                -      0.882   0.946       -           -          -        -       
detection_result          -      -       -           -           0.955      0.889    0.889   
detection_method          -      -       -           -           0.973      0.934    0.934   
product_detection_result  -      -       -           -           0.820      0.778    0.778   
log_method                -      -       -           -           n/a        n/a      n/a     
plugin                    n/a    -       -           -           -          -        -       
plugin_details            -      -       -           n/a         -          -        -       
instances                 -      -       -           -           n/a        n/a      n/a     
cvss                      1.000  -       -           -           -          -        -       
severity                  1.000  -       -           -           -          -        -       
port                      1.000  -       -           -           -          -        -       
protocol                  1.000  -       -           -           -          -        -       
```

`n/a` = every matched pair was empty on both sides for that field (nothing to measure). Inclusive means and per-pair detail live in `evaluation.json`.

## Worst pairs per field

- **description**: SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.803); rexec Passwordless / Unencrypted Cleartext Login (0.822); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.886); SSL/TLS: Certificate Expired (0.917); SSL/TLS: Certificate Expired (0.917)
- **solution**: Tiki Wiki CMS Groupware < 4.2 Multiple Unspecified Vulnerabilities (0.0); SSH Brute Force Logins With Default Credentials Reporting (0.727); Samba MS-RPC Remote Shell Command Execution Vulnerability (Active Check) (0.729); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.769); phpinfo() output Reporting (0.814)
- **impact**: Tiki Wiki CMS Groupware < 4.2 Multiple Unspecified Vulnerabilities (0.0); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.0); VNC Server Unencrypted Data Transmission (0.883); FTP Unencrypted Cleartext Login (0.896); Telnet Unencrypted Cleartext Login (0.896)
- **insight**: SSL/TLS: Certificate Expired (0.0); SSL/TLS: Certificate Expired (0.0); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.0); SSL/TLS: 'DHE_EXPORT' Man in the Middle Security Bypass Vulnerability (LogJam) (0.897); TCP timestamps (0.922)
- **references**: OS End Of Life Detection (0.0); Test HTTP dangerous methods (0.5); Anonymous FTP Login Reporting (0.5); awiki Multiple Local File Include Vulnerabilities (0.625); Tiki Wiki CMS Groupware < 4.2 Multiple Unspecified Vulnerabilities (0.696)
- **detection_result**: SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.0); MySQL / MariaDB weak password (0.274); PostgreSQL weak password (0.275); OS End Of Life Detection (0.424); Tiki Wiki CMS Groupware < 4.2 Multiple Unspecified Vulnerabilities (0.466)
- **detection_method**: SSL/TLS: Certificate Expired (0.368); SSL/TLS: SSLv3 Protocol CBC Cipher Suites Information Disclosure Vulnerability (POODLE) (0.525); Telnet Unencrypted Cleartext Login (0.563); SSL/TLS: Deprecated SSLv2 and SSLv3 Protocol Detection (0.612); SSL/TLS: Report Weak Cipher Suites (0.618)
- **product_detection_result**: Distributed Ruby (dRuby/DRb) Multiple Remote Code Execution Vulnerabilities (0.0); vsftpd Compromised Source Packages Backdoor Vulnerability (0.0); vsftpd Compromised Source Packages Backdoor Vulnerability (0.0); TWiki Cross-Site Request Forgery Vulnerability - Sep10 (0.753); PostgreSQL weak password (0.754)

## Spurious (extracted, not in baseline)

- SSL/TLS: Certificate Signed Using A Weak Signature Algorithm

## Notes

- baseline never fills `log_method`, `plugin`, `plugin_details`, `instances` — scores there only measure presence agreement: 1.0 means the extraction also left the field empty; low values mean it filled a field the ground truth does not annotate.
