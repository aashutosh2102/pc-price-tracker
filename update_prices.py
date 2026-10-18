"""
Fetch today's prices (lowest in-stock across several sites) into data/prices.csv.

  python update_prices.py                  automatic (used by Task Scheduler / GitHub Actions)
  python update_prices.py --ask            also ask you to type prices it couldn't fetch
  python update_prices.py --add GPU 74990  record a quote, e.g. from Nehru Place
  python update_prices.py --test           show what every source returns, without saving
"""
import sys

import requests

from tracker_core import fetch_part, load_config, read_rows, save_rows, summarize, upsert


def main():
    args = sys.argv[1:]
    cfg = load_config()
    names = [p["name"] for p in cfg["parts"]]
    rows = read_rows()
    added = 0

    if "--add" in args:
        i = args.index("--add")
        try:
            part, price = args[i + 1], int(args[i + 2].replace(",", ""))
        except (IndexError, ValueError):
            sys.exit('Usage: python update_prices.py --add GPU 74990   (quote names with spaces: "CPU Cooler")')
        match = [n for n in names if n.lower() == part.lower()]
        if not match:
            sys.exit(f"Unknown part '{part}'. Use one of: {', '.join(names)}")
        rows = upsert(rows, match[0], price, "manual quote")
        added = 1
    else:
        with requests.Session() as s:
            for p in cfg["parts"]:
                price, src, log = fetch_part(p, s)
                for l in log:
                    shown = f"Rs {l['price']:,}" if l["price"] else "-"
                    print(f"  {l['part']:<13} {l['site']:<22} {shown:>11}  {l['status']}")
                if price:
                    print(f"  {'':<13} -> using Rs {price:,} from {src}")
                elif "--ask" in args:
                    v = input(f"    Type today's {p['name']} price (Enter to skip): ").strip().replace(",", "")
                    if v.isdigit():
                        price, src = int(v), "manual"
                if price and "--test" not in args:
                    rows = upsert(rows, p["name"], price, src)
                    added += 1

    if added:
        save_rows(rows)
    print(f"\nSaved {added} price(s).\n")
    print(f"{'Part':<13}{'Latest':>10}{'Target':>10}{'90d':>8}{'In 1 yr':>10}  Signal")
    for s in summarize(rows, cfg):
        f, p = s["f"], s["part"]
        if f:
            print(f"{p['name']:<13}{f['latest']:>10,}{p['target']:>10,}{f['change_90d']:>+8.1%}{f['f1y']:>10,}  {f['signal']}")
    # Always exit 0 so scheduled jobs don't fail when a site blocks requests.


if __name__ == "__main__":
    main()
