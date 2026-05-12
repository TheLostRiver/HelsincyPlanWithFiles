---
description: "Capture external or visual context into findings.md. /plw-capture"
argument-hint: "--kind web|browser|image|pdf|file|note --source <source> --summary <summary> [--trust <note>]"
---

Use `$ARGUMENTS` as the capture metadata.

If kind, source, or summary is missing, ask the user for the missing fields. Otherwise run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py capture $ARGUMENTS
```

Keep the summary factual and concise. Capture only context that should persist beyond the current model context window.
