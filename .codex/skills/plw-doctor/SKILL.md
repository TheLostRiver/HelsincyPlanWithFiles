---
name: plw-doctor
description: Run Helsincy Plan With Files diagnostics. Invoke with /plw-doctor.
user-invocable: true
allowed-tools: "Bash"
---

# /plw-doctor

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py doctor
```

Report the diagnostic output clearly. If any check is not healthy, explain the next safe fix before editing files.
