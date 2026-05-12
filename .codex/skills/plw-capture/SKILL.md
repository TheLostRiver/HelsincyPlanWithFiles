---
name: plw-capture
description: Capture external or visual context into findings.md. Invoke with /plw-capture.
user-invocable: true
allowed-tools: "Bash"
---

# /plw-capture

Use any text after `/plw-capture` as the capture metadata.

If kind, source, or summary is missing, ask the user for the missing fields. Otherwise run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py capture --kind <web|browser|image|pdf|file|note> --source <source> --summary <summary>
```

Keep the summary factual and concise. Capture only context that should persist beyond the current model context window.
