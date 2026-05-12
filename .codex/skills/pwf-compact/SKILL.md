---
name: pwf-compact
description: Archive old progress.md auto records and keep recent progress small. Invoke with /pwf-compact.
user-invocable: true
allowed-tools: "Bash"
---

# /pwf-compact

Archive old objective auto records from `progress.md` into `progress.archive.md`, then keep only recent hot records in `progress.md`.

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py compact
```

If the user asks for a custom keep count, pass `--keep-records <N>`.
If the user asks to preview only, pass `--dry-run`.

After it completes, summarize archived count, kept count, and archive path.
