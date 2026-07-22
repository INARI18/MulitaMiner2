# Evaluation report

- results: `output_experiments\openvas\deepseek\run_3\OpenVAS_bBWA\results.json`
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
description               -      -       -           -           0.986      0.965    0.965   
solution                  -      -       -           -           0.956      0.909    0.909   
impact                    -      -       -           -           0.930      0.912    0.912   
insight                   -      -       -           -           0.895      0.884    0.884   
references                -      0.879   0.943       -           -          -        -       
detection_result          -      -       -           -           0.956      0.892    0.892   
detection_method          -      -       -           -           0.973      0.935    0.935   
product_detection_result  -      -       -           -           0.821      0.783    0.783   
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

- **description**: SSL/TLS: Certificate Expired (0.785); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.803); rsh Unencrypted Cleartext Login (0.822); rexec Passwordless / Unencrypted Cleartext Login (0.822); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.886)
- **solution**: Tiki Wiki CMS Groupware < 4.2 Multiple Unspecified Vulnerabilities (0.0); SSL/TLS: OpenSSL CCS Man in the Middle Security Bypass Vulnerability (0.582); TWiki XSS and Command Execution Vulnerabilities (0.659); SSL/TLS: 'DHE_EXPORT' Man in the Middle Security Bypass Vulnerability (LogJam) (0.727); SSL/TLS: Deprecated SSLv2 and SSLv3 Protocol Detection (0.76)
- **impact**: Tiki Wiki CMS Groupware < 4.2 Multiple Unspecified Vulnerabilities (0.0); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.0); VNC Server Unencrypted Data Transmission (0.883); FTP Unencrypted Cleartext Login (0.896); Telnet Unencrypted Cleartext Login (0.896)
- **insight**: SSL/TLS: Certificate Expired (0.0); SSL/TLS: Certificate Expired (0.0); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.0); SSL/TLS: 'DHE_EXPORT' Man in the Middle Security Bypass Vulnerability (LogJam) (0.897); TCP timestamps (0.922)
- **references**: OS End Of Life Detection (0.0); Test HTTP dangerous methods (0.5); Anonymous FTP Login Reporting (0.5); awiki Multiple Local File Include Vulnerabilities (0.625); Tiki Wiki CMS Groupware < 4.2 Multiple Unspecified Vulnerabilities (0.696)
- **detection_result**: SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.0); MySQL / MariaDB weak password (0.274); PostgreSQL weak password (0.275); OS End Of Life Detection (0.424); Tiki Wiki CMS Groupware < 4.2 Multiple Unspecified Vulnerabilities (0.466)
- **detection_method**: SSL/TLS: Certificate Expired (0.367); SSL/TLS: SSLv3 Protocol CBC Cipher Suites Information Disclosure Vulnerability (POODLE) (0.525); Telnet Unencrypted Cleartext Login (0.563); SSL/TLS: Deprecated SSLv2 and SSLv3 Protocol Detection (0.612); SSL/TLS: Report Weak Cipher Suites (0.618)
- **product_detection_result**: Distributed Ruby (dRuby/DRb) Multiple Remote Code Execution Vulnerabilities (0.0); vsftpd Compromised Source Packages Backdoor Vulnerability (0.0); vsftpd Compromised Source Packages Backdoor Vulnerability (0.0); MySQL / MariaDB weak password (0.754); TWiki < 6.1.0 XSS Vulnerability (0.754)

## Spurious (extracted, not in baseline)

- SSL/TLS: Certificate Signed Using A Weak Signature Algorithm

## Notes

- baseline never fills `log_method`, `plugin`, `plugin_details`, `instances` — scores there only measure presence agreement: 1.0 means the extraction also left the field empty; low values mean it filled a field the ground truth does not annotate.
