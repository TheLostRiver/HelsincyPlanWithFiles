---
name: plw-init
description: Create a new Helsincy Plan With Files task. Invoke with /plw-init.
user-invocable: true
allowed-tools: "Bash"
---

# /plw-init

Use any text after `/plw-init` as the task name and options.

If no task name was provided, ask the user for the task name. Otherwise run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py init <task name and options>
```

After it completes, summarize the active plan path and the created planning files.
