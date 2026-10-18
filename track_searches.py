"""Daily: refresh every product you starred (⭐ Track daily) on the Search page.
Appends prices to data/search_history.csv and ratings to data/search_reviews.csv, so their history keeps growing."""
import json
from datetime import date

import requests

import search_core as sc


def main():
    watch = json.loads(sc.WATCH.read_text(encoding="utf-8")) if sc.WATCH.exists() else []
    if not watch:
        print("Watchlist is empty - star products on the Search page first.")
        return
    H = sc.read_csv_text(sc.SHIST.read_text(encoding="utf-8") if sc.SHIST.exists() else "")
    R = sc.read_csv_text(sc.SREV.read_text(encoding="utf-8") if sc.SREV.exists() else "")
    with requests.Session() as s:
        for w in watch:
            res, log = sc.refresh_watch_item(w, s)
            p, r = sc.snapshot_rows(w["canonical"], res)
            H += p
            R += r
            ok = sum(1 for l in log if "point" in l["result"])
            print(f"  {w['canonical']:<28} {len(res['points']):>3} price points from {ok}/{len(log)} sources"
                  + (f", rating {res['rating']['score']}" if res.get("rating") else ""))
    sc.SHIST.parent.mkdir(parents=True, exist_ok=True)
    sc.SHIST.write_text(sc.to_csv(H, sc.HIST_FIELDS), encoding="utf-8")
    sc.SREV.write_text(sc.to_csv(R, sc.REV_FIELDS), encoding="utf-8")
    print(f"Saved. {date.today()}")


if __name__ == "__main__":
    main()
