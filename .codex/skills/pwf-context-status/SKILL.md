---
name: pwf-context-status
description: Show the current session PWF context profile and notice settings. Invoke with /pwf-context-status.
user-invocable: true
allowed-tools: "Bash"
---

# /pwf-context-status

Run:

```powershell
python .codex\skills\planning-with-files\scripts\plan.py context status
```

中文模式：如果用户希望中文输出，先设置 `PWF_LANG=zh-CN`，再运行相同命令。

Show the effective profile, source, notice mode, progress mode, findings state, and context budget for the current session.
