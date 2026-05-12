---
name: pwf-switch
description: Show or switch the active Helsincy Plan With Files task. Invoke with /pwf-switch.
user-invocable: true
allowed-tools: "Bash"
---

# /pwf-switch

Use any text after `/pwf-switch` as the optional plan id.

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py switch <optional plan-id>
```

If no plan id was provided, report the current active plan. If a plan id was provided, confirm the newly active plan.
