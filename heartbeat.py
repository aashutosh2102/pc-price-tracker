"""Writes data/last_run.json so you can see every automatic run - even when stores block the server and no prices change."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

log = Path(sys.argv[1]).read_text(encoding="utf-8", errors="ignore") if len(sys.argv) > 1 and Path(sys.argv[1]).exists() else ""
info = {
    "ran_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
    "runner": "GitHub Actions" if os.environ.get("GITHUB_ACTIONS") else "Windows PC",
    "trigger": os.environ.get("GITHUB_EVENT_NAME", "task"),
    "blocked_requests": log.count("blocked (HTTP"),
    "prices_saved_lines": [l.strip() for l in log.splitlines() if l.strip().startswith("Saved")],
}
Path("data").mkdir(exist_ok=True)
Path("data/last_run.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
print(json.dumps(info, indent=2))
summary = os.environ.get("GITHUB_STEP_SUMMARY")
if summary:
    with open(summary, "a", encoding="utf-8") as f:
        f.write(f"### Price update — {info['ran_at_utc']} UTC ({info['trigger']})\n\n"
                f"- Blocked requests: **{info['blocked_requests']}**\n" +
                "".join(f"- {l}\n" for l in info["prices_saved_lines"]) +
                ("\n> Many blocked requests = the stores are refusing GitHub's servers. "
                 "Your Windows task (home internet) will still collect prices.\n" if info["blocked_requests"] > 5 else ""))
