---
description: "Lock, show, or clear plan hash attestation. /plw-attest"
argument-hint: "[--show|--clear]"
---

Use `$ARGUMENTS` as optional attestation flags.

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py attest $ARGUMENTS
```

When creating an attestation, remind the user that future hook injection will block tampered plan content until the plan is reviewed and re-attested or the attestation is cleared.
