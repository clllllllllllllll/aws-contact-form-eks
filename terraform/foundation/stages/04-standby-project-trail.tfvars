# Use only after capturing live findings and destroying the disposable workload.
# Retain the issued certificate, DNS, buckets, logs, recorder configuration and
# logging project trail. Stop Config recording; disable Security Hub and FSBP.
# A reviewed plan must show only those intended changes.
enable_certificate       = true
enable_security_services = true
enable_cloudtrail        = true
pause_config_and_fsbp    = true
