"""Long-run price history: backfill from pricehistory.app (drop log, lowest/highest, current)
and combine all sources into one tidy timeline per item."""
import json
import re
from datetime import date, datetime, timedelta

import requests

from tracker_core import HEADERS, ROOT, page_text

HISTORY = ROOT / "data" / "history.csv"
LAUNCH = ROOT / "data" / "launch.json"
MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
D = r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Z][a-z]{2})[a-z]*,?\s+(\d{4})"
P = r"₹\s*([\d,]+)"


def _d(day, mon, year):
    return date(int(year), MONTHS[mon[:3]], int(day))


def _p(s):
    return int(s.replace(",", ""))


def parse_pricehistory(text, store_hint="pricehistory.app"):
    """Parse a pricehistory.app product page (as plain text). Returns [(date, price, label)]."""
    pts = []
    m = re.search(r"Price History\s+" + D, text)
    page_day = _d(*m.groups()) if m else date.today()
    for m in re.finditer(r"Price Drop\s+" + D + r"\s+" + P + r"\s*(?:→|->|&rarr;)\s*" + P, text):
        d, a, b = _d(*m.groups()[:3]), _p(m.group(4)), _p(m.group(5))
        pts += [(d - timedelta(days=1), a, "drop log (before)"), (d, b, "drop log")]
    for label, key in (("lowest ever", r"Lowest Ever Price"), ("highest", r"Highest Price")):
        m = re.search(key + r"\s+" + P + r"\s+" + D, text)
        if m:
            pts.append((_d(*m.groups()[1:4]), _p(m.group(1)), label))
    m = re.search(r"current Price in India is\s+" + P, text)
    if m:
        pts.append((page_day, _p(m.group(1)), "current"))
    return [(d, p, f"{store_hint} {lab}") for d, p, lab in sorted(set(pts))]


def fetch_history(url, session=None):
    try:
        r = (session or requests).get(url, headers=HEADERS, timeout=25)
        if r.status_code != 200:
            return [], f"blocked (HTTP {r.status_code})"
        pts = parse_pricehistory(page_text(r.text))
        return pts, f"ok ({len(pts)} points)" if pts else "no history found"
    except requests.RequestException as e:
        return [], f"network error ({type(e).__name__})"


# ---------- storage ----------
def read_history(text=None):
    import csv
    if text is None:
        text = HISTORY.read_text(encoding="utf-8") if HISTORY.exists() else ""
    out = []
    for r in csv.DictReader(text.splitlines()):
        try:
            out.append({"date": date.fromisoformat(r["date"]), "item": r["item"],
                        "price": int(float(r["price"])), "source": r.get("source", "")})
        except (KeyError, ValueError, TypeError):
            pass
    return out


def history_to_csv(rows):
    seen, lines = set(), ["date,item,price,source"]
    for r in sorted(rows, key=lambda r: (r["item"], r["date"], r["price"])):
        k = (r["date"], r["item"], r["price"])
        if k in seen:
            continue
        seen.add(k)
        lines.append(f'{r["date"].isoformat()},{r["item"]},{r["price"]},{str(r["source"]).replace(",", ";")}')
    return "\n".join(lines) + "\n"


def merge_points(rows, item, pts):
    return rows + [{"date": d, "item": item, "price": p, "source": s} for d, p, s in pts]


def load_launch():
    return json.loads(LAUNCH.read_text(encoding="utf-8")) if LAUNCH.exists() else {}


# ---------- combine everything into one timeline ----------
def timeline(item, build_part, build_rows, hist_rows, market_hist_rows):
    """All known points for an item: build tracker + long-run history + daily market minimum.
    Returns list of dicts {date, price, source, series}."""
    out = []
    for r in build_rows:
        if build_part and r["part"] == build_part:
            out.append({"date": r["date"], "price": r["price"], "source": r["source"] or "tracker", "series": "Your tracker"})
    for r in hist_rows:
        if r["item"] == item:
            out.append({"date": r["date"], "price": r["price"], "source": r["source"], "series": "Long-run history"})
    by_day = {}
    for r in market_hist_rows:
        if r.get("key") == item:
            try:
                d, p = date.fromisoformat(r["date"]), int(float(r["price"]))
            except (ValueError, TypeError):
                continue
            by_day[d] = min(p, by_day.get(d, p))
    out += [{"date": d, "price": p, "source": "market scan (cheapest listing)", "series": "Market scan"}
            for d, p in by_day.items()]
    return sorted(out, key=lambda r: r["date"])
