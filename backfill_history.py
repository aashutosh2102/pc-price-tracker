"""
Backfill long-run price history (as far back as pricehistory.app tracks each product)
into data/history.csv.

  python backfill_history.py          fetch and merge
  python backfill_history.py --test   show what would be added, without saving
"""
import sys
import time

import requests

from history_core import HISTORY, fetch_history, history_to_csv, merge_points, read_history
from tracker_core import load_config


def main():
    cfg = load_config()
    jobs = [(p["history_item"], u) for p in cfg["parts"] for u in p.get("history_urls", []) if u]
    jobs += [(x["item"], x["url"]) for x in cfg.get("extra_history", [])]
    rows = read_history()
    before = len(rows)
    with requests.Session() as s:
        for item, url in jobs:
            pts, status = fetch_history(url, s)
            span = f"{pts[0][0]} → {pts[-1][0]}" if pts else ""
            print(f"  {item:<40} {status:<28} {span}")
            rows = merge_points(rows, item, pts)
            time.sleep(1)
    if "--test" in sys.argv:
        print("\nTest only - nothing saved.")
        return
    text = history_to_csv(rows)
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(text, encoding="utf-8")
    print(f"\nHistory now has {len(text.splitlines()) - 1} points (was {before}).")


if __name__ == "__main__":
    main()
