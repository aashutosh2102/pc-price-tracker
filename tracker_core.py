"""Shared logic: config, price fetching, history storage and the forecast model."""
import csv
import json
import re
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).parent
CONFIG = ROOT / "parts.json"
DATA = ROOT / "data" / "prices.csv"
FIELDS = ["date", "part", "price", "source"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}


# ---------- config & data ----------
def load_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def read_rows(text=None):
    """Read history rows from CSV text (or the local file)."""
    if text is None:
        if not DATA.exists():
            return []
        text = DATA.read_text(encoding="utf-8")
    rows = []
    for r in csv.DictReader(text.splitlines()):
        try:
            rows.append({"date": date.fromisoformat(r["date"]), "part": r["part"],
                         "price": int(float(r["price"])), "source": r.get("source", "")})
        except (KeyError, ValueError):
            continue
    return rows


def rows_to_csv(rows):
    out = [",".join(FIELDS)]
    for r in sorted(rows, key=lambda r: (r["date"], r["part"])):
        src = str(r.get("source", "")).replace(",", ";").replace("\n", " ")
        out.append(f'{r["date"].isoformat()},{r["part"]},{r["price"]},{src}')
    return "\n".join(out) + "\n"


def upsert(rows, part, price, source, day=None):
    """Add a price; replaces an existing entry for the same part and day."""
    day = day or date.today()
    rows = [r for r in rows if not (r["date"] == day and r["part"] == part)]
    rows.append({"date": day, "part": part, "price": int(price), "source": source})
    return rows


def save_rows(rows):
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(rows_to_csv(rows), encoding="utf-8")


# ---------- fetching ----------
def _text(html):
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    t = re.sub(r"<[^>]+>", " ", html).replace("&#8377;", "₹").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", t)


def fetch_price(part):
    """Returns (price or None, status message)."""
    if not part.get("url"):
        return None, "manual part (no tracker page)"
    try:
        r = requests.get(part["url"], headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None, f"site returned HTTP {r.status_code}"
        text = _text(r.text)
        for pat in part["patterns"]:
            m = re.search(pat, text)
            if m:
                price = int(m.group(1).replace(",", ""))
                if 0.3 * part["target"] <= price <= 3 * part["target"]:
                    return price, "ok"
                return None, f"ignored odd value Rs {price:,}"
        return None, "price not found (page layout may have changed)"
    except requests.RequestException as e:
        return None, f"network error: {type(e).__name__}"


# ---------- forecast model ----------
def forecast(points, target, outlook, half_life=45):
    """
    points: [(date, price)] for one part.
    1) recency-weighted linear trend of your data (half-life in days)
    2) blended with market outlook: trust = n/(n+8)
    3) 1-year path: momentum halves each quarter
    """
    points = sorted(points)
    latest = points[-1][1]
    n = len(points)
    newest = points[-1][0]
    data_trend = None
    if n >= 3:
        xs = [(d - newest).days for d, _ in points]
        ws = [0.5 ** (-x / half_life) for x in xs]
        ys = [p for _, p in points]
        sw = sum(ws)
        swx = sum(w * x for w, x in zip(ws, xs))
        swy = sum(w * y for w, y in zip(ws, ys))
        swxx = sum(w * x * x for w, x in zip(ws, xs))
        swxy = sum(w * x * y for w, x, y in zip(ws, xs, ys))
        den = sw * swxx - swx ** 2
        if den:
            slope = (sw * swxy - swx * swy) / den
            data_trend = max(-0.3, min(0.3, slope * 90 / latest))
    trust = n / (n + 8) if data_trend is not None else 0.0
    L = trust * data_trend + (1 - trust) * outlook if data_trend is not None else outlook

    q = [latest * (1 + L)]
    for k in (2, 4, 8):
        q.append(q[-1] * (1 + L / k))

    if latest <= target:
        when, sig = "Now", "BUY - at/below target"
    else:
        labels = ["Within 3 months", "In 3-6 months", "In 6-9 months", "In 9-12 months"]
        when = next((lab for lab, v in zip(labels, q) if v <= target), "Not within 1 year")
        if L > 0.02:
            sig = "Rising - buy soon"
        elif L < -0.02:
            sig = "Falling - wait" if when != "Not within 1 year" else "Falling slowly - buy when ready"
        else:
            sig = "Flat - buy when ready"
    return {
        "latest": latest, "last_date": newest, "n": n, "low": min(p for _, p in points),
        "high": max(p for _, p in points), "data_trend": data_trend, "trust": trust,
        "change_90d": L, "f30": round(latest * (1 + L) ** (1 / 3)), "f90": round(q[0]),
        "f1y": round(q[3]), "when": when, "signal": sig,
    }


def summarize(rows, cfg):
    hl = cfg.get("half_life_days", 45)
    out = []
    for p in cfg["parts"]:
        pts = [(r["date"], r["price"]) for r in rows if r["part"] == p["name"]]
        f = forecast(pts, p["target"], p["outlook_90d"], hl) if pts else None
        out.append({"part": p, "f": f})
    return out
