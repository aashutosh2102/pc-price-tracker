"""
Scan the whole market (every CPU, GPU, motherboard, RAM, SSD, PSU, cooler, case listed by the stores
in market.json), save it to data/market_*.csv and report what's new.

  python update_market.py                 full scan and save
  python update_market.py --only GPU RAM  scan some categories only (not saved)
"""
import sys

from market_core import (best_alternatives, load_local, read_csv_text, run_scan_and_merge,
                         save_local, scan_market)
from tracker_core import load_config


def progress(cat, page, pages):
    print(f"  {cat:<13} page {page}/{pages}")


def main():
    args = sys.argv[1:]
    if "--only" in args:
        cats = args[args.index("--only") + 1:]
        items, log = scan_market(categories=cats, progress=progress)
        for i in sorted(items, key=lambda x: (x["category"], x["price"]))[:60]:
            print(f"  {i['category']:<12} {i.get('key',''):<20} Rs {i['price']:>9,}  {i['name'][:60]}")
        print(f"\n{len(items)} products (test scan, not saved).")
        return
    latest, seen, meta = load_local()
    print("Scanning the whole market...")
    lt, st, meta, ch, log = run_scan_and_merge(latest, seen, meta, progress)
    blocked = [l for l in log if l["status"] != "ok"]
    for b in blocked:
        print(f"  ! {b['category']}: {b['status']}  {b['url']}")
    if lt is None:
        print("\nNo products fetched (sites blocked?). Nothing saved.")
        return
    save_local(lt, st, meta)
    items = read_csv_text(lt)
    print(f"\nSaved {len(items)} products. Baseline scan: {meta['baseline']}\n")
    print(f"New products: {len(ch['new_products'])}  |  New models/chips: {len(ch['new_models'])}  |  "
          f"Price drops >=5%: {len(ch['drops'])}  |  New all-time lows: {len(ch['new_lows'])}")
    for i in ch["new_models"]:
        print(f"  NEW MODEL  {i['category']:<12} {i['key']:<22} Rs {int(i['price']):,}  {i['name'][:50]}")
    for i in sorted(ch["drops"], key=lambda x: -x["drop_pct"])[:15]:
        print(f"  DROP {i['drop_pct']:>4.0%}  {i['category']:<12} Rs {i['old_price']:,} -> {int(i['price']):,}  {i['name'][:50]}")
    print("\nCheapest equivalents for your build:")
    for p in load_config()["parts"]:
        alts = best_alternatives(items, p.get("match", {}), 1)
        if alts:
            a = alts[0]
            print(f"  {p['name']:<13} Rs {int(float(a['price'])):>9,}  {a['name'][:60]}")


if __name__ == "__main__":
    main()
