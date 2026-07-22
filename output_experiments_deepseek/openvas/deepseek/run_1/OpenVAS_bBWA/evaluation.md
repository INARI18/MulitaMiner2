# Evaluation report

- results: `output_experiments_deepseek\openvas\deepseek\run_1\OpenVAS_bBWA\results.json`
- baseline: `resources\openvas\OpenVAS_bBWA.xlsx`
- source: OPENVAS — threshold 0.7 — text metrics: token_f1

## Coverage

- baseline findings: 58
- extracted records: 59
- matched: 57  (recall 0.983, precision 0.966)

## Field scores (measured mean — vacuous empty×empty pairs excluded)

```
field                     exact  set_f1_ids  structural  token_f1
-----                     -----  ----------  ----------  --------
name                      -      -           -           1.000   
description               -      -           -           0.969   
solution                  -      -           -           0.915   
impact                    -      -           -           0.910   
insight                   -      -           -           0.883   
references                -      0.939       -           -       
detection_result          -      -           -           0.889   
detection_method          -      -           -           0.934   
product_detection_result  -      -           -           0.778   
log_method                -      -           -           n/a     
plugin                    n/a    -           -           -       
plugin_details            -      -           n/a         -       
instances                 -      -           -           n/a     
cvss                      1.000  -           -           -       
severity                  1.000  -           -           -       
port                      1.000  -           -           -       
protocol                  1.000  -           -           -       
```

`n/a` = every matched pair was empty on both sides for that field (nothing to measure). Inclusive means and per-pair detail live in `evaluation.json`.

## Worst pairs per field

- **description**: SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.75); rsh Unencrypted Cleartext Login (0.762); rexec Passwordless / Unencrypted Cleartext Login (0.762); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.857); TWiki XSS and Command Execution Vulnerabilities (0.872)
- **solution**: Tiki Wiki CMS Groupware < 4.2 Multiple Unspecified Vulnerabilities (0.0); SSL/TLS: OpenSSL CCS Man in the Middle Security Bypass Vulnerability (0.435); Samba MS-RPC Remote Shell Command Execution Vulnerability (Active Check) (0.632); SSH Brute Force Logins With Default Credentials Reporting (0.636); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.693)
- **impact**: Tiki Wiki CMS Groupware < 4.2 Multiple Unspecified Vulnerabilities (0.0); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.0); VNC Server Unencrypted Data Transmission (0.846); FTP Unencrypted Cleartext Login (0.867); Telnet Unencrypted Cleartext Login (0.867)
- **insight**: SSL/TLS: Certificate Expired (0.0); SSL/TLS: Certificate Expired (0.0); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.0); SSL/TLS: 'DHE_EXPORT' Man in the Middle Security Bypass Vulnerability (LogJam) (0.875); TCP timestamps (0.9)
- **references**: OS End Of Life Detection (0.0); Test HTTP dangerous methods (0.5); vsftpd Compromised Source Packages Backdoor Vulnerability (0.667); Tiki Wiki CMS Groupware < 4.2 Multiple Unspecified Vulnerabilities (0.696); HTTP Debugging Methods (TRACE/TRACK) Enabled (0.75)
- **detection_result**: PostgreSQL weak password (0.0); MySQL / MariaDB weak password (0.0); SSL/TLS: Diffie-Hellman Key Exchange Insufficient DH Group Strength Vulnerability (0.0); OS End Of Life Detection (0.212); Tiki Wiki CMS Groupware < 4.2 Multiple Unspecified Vulnerabilities (0.27)
- **detection_method**: SSL/TLS: Certificate Expired (0.14); SSL/TLS: SSLv3 Protocol CBC Cipher Suites Information Disclosure Vulnerability (POODLE) (0.35); Telnet Unencrypted Cleartext Login (0.4); SSL/TLS: Deprecated SSLv2 and SSLv3 Protocol Detection (0.478); SSL/TLS: Report Weak Cipher Suites (0.483)
- **product_detection_result**: Distributed Ruby (dRuby/DRb) Multiple Remote Code Execution Vulnerabilities (0.0); vsftpd Compromised Source Packages Backdoor Vulnerability (0.0); vsftpd Compromised Source Packages Backdoor Vulnerability (0.0); MySQL / MariaDB weak password (0.667); TWiki Cross-Site Request Forgery Vulnerability - Sep10 (0.667)

## False negatives (in baseline, not extracted)

- phpinfo() output Reporting

## False positives (extracted, not in baseline)

- phpinfo() output Reporting 2 RESULTS PER HOST 7
- SSL/TLS: Certificate Signed Using A Weak Signature Algorithm

## Notes

- baseline never fills `log_method`, `plugin`, `plugin_details`, `instances` — scores there only measure presence agreement: 1.0 means the extraction also left the field empty; low values mean it filled a field the ground truth does not annotate.
