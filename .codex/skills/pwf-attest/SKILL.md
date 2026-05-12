---
name: pwf-attest
description: Lock, show, or clear plan hash attestation. Invoke with /pwf-attest.
user-invocable: true
allowed-tools: "Bash"
---

# /pwf-attest

Use any text after `/pwf-attest` as optional attestation flags.

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py attest <optional --show or --clear>
```

When creating an attestation, remind the user that future hook injection will block tampered plan content until the plan is reviewed and re-attested or the attestation is cleared.
