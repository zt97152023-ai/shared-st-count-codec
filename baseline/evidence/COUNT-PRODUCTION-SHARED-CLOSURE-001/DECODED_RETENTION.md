# Decoded-output retention

Decoded `decoded.npz` and `metadata.json` directories were removed only when the sibling `verify.json` reported `all=true`. Archives, archive SHA-256 values, physical ledgers, decode reports, verify reports, failure directories, and retry artifacts were retained. Decoded outputs remain reproducible from the retained archives in fresh processes.
