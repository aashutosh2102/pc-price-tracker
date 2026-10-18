"""Product search: understand a free-text query ("5070 rtx", "intel ultra 7 cpu"), find the product on
Indian price-history sites, and return its price history since launch plus ratings.

Self-contained (no imports from the rest of the project) so it can be dropped into the repo as-is.

Sources (no API key needed):
  gpuprix.com        GPUs: launch date, launch MSRP, 12-month low/median, 3-month median, current low, perf score, boards
  pricehistory.app   any product: price-drop log, lowest/highest/average, tracking span, current price, rating
  pcpricetracker.in  any product: lowest now, 30-day median, 90-day low/high, all-time low with dates
  pcpaisa.in         any product: lowest live in-stock price, store count
Web search to find pages: Google Programmable Search or Brave (optional keys) -> DuckDuckGo fallback.
"""
import csv
import difflib
import io
import json
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests

ROOT = Path(__file__).parent
WATCH = ROOT / "data" / "watchlist.json"
SHIST = ROOT / "data" / "search_history.csv"
SREV = ROOT / "data" / "search_reviews.csv"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept-Language": "en-IN,en;q=0.9"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug",
                                       "sep", "oct", "nov", "dec"], 1)}
SITES = ["gpuprix.com", "pricehistory.app", "pcpricetracker.in", "pcpaisa.in"]


# =============================== helpers ===============================
def page_text(html):
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    t = re.sub(r"<[^>]+>", " ", html)
    for a, b in (("&#8377;", "₹"), ("&#x20B9;", "₹"), ("&nbsp;", " "), ("&amp;", "&"), ("&rarr;", "→"), ("&#8594;", "→")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t)


def _p(s):
    return int(str(s).replace(",", "").split(".")[0])


def parse_date(s):
    """'7th Aug 2025', 'Aug 7, 2025', '07 Aug 2026', '2025-08-07' -> date."""
    s = s.strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3})[a-z]*,?\s+(\d{4})", s)
    if m:
        return date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
    m = re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", s)
    if m:
        return date(int(m[3]), MONTHS[m[1].lower()], int(m[2]))
    raise ValueError(s)


D1 = r"\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]{2}[a-z]*,?\s+\d{4}"
D2 = r"[A-Z][a-z]{2}[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
P = r"₹\s*([\d,]+)"

_fixtures = None


def http_get(url, session=None, timeout=20):
    """Returns (status_code, text). PCT_FIXTURES=path.json lets tests replay saved pages."""
    global _fixtures
    if os.environ.get("PCT_FIXTURES"):
        if _fixtures is None:
            _fixtures = json.loads(Path(os.environ["PCT_FIXTURES"]).read_text(encoding="utf-8"))
        for k, v in _fixtures.items():
            if k in url:
                return 200, v
        return 404, ""
    try:
        r = (session or requests).get(url, headers=HEADERS, timeout=timeout)
        return r.status_code, r.text
    except requests.RequestException as e:
        return 0, type(e).__name__


# =============================== 1. understand the query ===============================
GPU_FAM = {"rtx": "RTX", "gtx": "GTX", "rx": "RX", "arc": "Arc"}
VRAM_VARIANTS = {"RTX 5060 Ti", "RX 9060 XT", "RTX 4060 Ti", "RTX 3060", "RTX 3050"}
KNOWN = {  # used to offer choices when a query is incomplete
    "Core Ultra 9": ["Core Ultra 9 285K", "Core Ultra 9 285"],
    "Core Ultra 7": ["Core Ultra 7 265K", "Core Ultra 7 265KF", "Core Ultra 7 265F", "Core Ultra 7 265"],
    "Core Ultra 5": ["Core Ultra 5 245K", "Core Ultra 5 245KF", "Core Ultra 5 235", "Core Ultra 5 225F", "Core Ultra 5 225"],
    "Ryzen 9": ["Ryzen 9 9950X3D", "Ryzen 9 9950X", "Ryzen 9 9900X", "Ryzen 9 7950X3D"],
    "Ryzen 7": ["Ryzen 7 9800X3D", "Ryzen 7 9700X", "Ryzen 7 7800X3D", "Ryzen 7 7700X", "Ryzen 7 7700"],
    "Ryzen 5": ["Ryzen 5 9600X", "Ryzen 5 7600X", "Ryzen 5 7600", "Ryzen 5 7500F"],
    "RTX 50": ["RTX 5090", "RTX 5080", "RTX 5070 Ti", "RTX 5070", "RTX 5060 Ti 16GB", "RTX 5060 Ti 8GB", "RTX 5060", "RTX 5050"],
    "RX 90": ["RX 9070 XT", "RX 9070", "RX 9060 XT 16GB", "RX 9060 XT 8GB"],
}


def understand(q):
    """Return {'kind', 'canonical' (or None), 'choices', 'terms', 'query'}."""
    raw = q.strip()
    s = " " + re.sub(r"[^a-z0-9.]+", " ", raw.lower()) + " "
    s = re.sub(r"\b(rtx|gtx|rx|arc)(\d)", r"\1 \2", s)
    s = re.sub(r"(\d{4})(ti|super|xtx|xt|gre)\b", r"\1 \2", s)
    out = {"query": raw, "kind": "Other", "canonical": None, "choices": [], "terms": raw}

    # ---- GPU ----
    fam = next((GPU_FAM[f] for f in GPU_FAM if re.search(rf"\b{f}\b", s)), None)
    num = re.search(r"\b(\d{4})\b", s) or (re.search(r"\b(\d{3})\b", s) if fam else None)
    gpu_hint = fam or re.search(r"\b(gpu|graphics|geforce|radeon|nvidia|video card)\b", s)
    if num and (gpu_hint or not re.search(r"\b(ryzen|core|intel|cpu|processor|ultra|i[3579])\b", s)):
        n = int(num.group(1))
        if not fam:
            if 2000 <= n <= 5099 and n % 10 == 0:
                fam = "RTX"
            elif 5000 < n < 10000 and n % 10 == 0 and str(n)[0] in "6789":
                fam = "RX"
        if fam and (fam != "RTX" or 2000 <= n <= 5099) and (fam != "RX" or n >= 400):
            name = f"{fam} {n}"
            if fam in ("RTX", "GTX"):
                name += " Ti" if re.search(r"\bti\b", s) else ""
                name += " Super" if re.search(r"\bsuper\b", s) else ""
            if fam == "RX":
                m = re.search(r"\b(xtx|xt|gre)\b", s)
                name += f" {m.group(1).upper()}" if m else ""
            vram = re.search(r"\b(\d{1,2})\s?gb\b", s)
            if name in VRAM_VARIANTS:
                if vram:
                    name += f" {vram.group(1)}GB"
                else:
                    out["choices"] = [f"{name} 16GB", f"{name} 8GB"]
            out.update(kind="GPU", canonical=None if out["choices"] else name, terms=name)
            return out

    # ---- CPU ----
    m = re.search(r"\bryzen\s?([3579])\s?(\d{4}\s?x3d|\d{4}[a-z]{0,2})?\b", s)
    if m:
        fam_ = f"Ryzen {m.group(1)}"
        if m.group(2):
            name = f"{fam_} {m.group(2).replace(' ', '').upper()}"
            out.update(kind="CPU", canonical=name, terms=name)
        else:
            out.update(kind="CPU", choices=KNOWN.get(fam_, []), terms=fam_)
        return out
    m = re.search(r"\b(\d{4}x3d|\d{4}x)\b", s)
    if m and not re.search(r"\b(intel|core)\b", s):
        d = m.group(1)
        name = f"Ryzen {'9' if d[1] == '9' else '7' if d[1] in '78' else '5'} {d.upper()}"
        out.update(kind="CPU", canonical=name, terms=name)
        return out
    if re.search(r"\bultra\b", s) or re.search(r"\bcore\s?u[3579]\b", s):
        tier = re.search(r"\bultra\s?([3579])\b|\b([3579])\s?ultra\b|\bu([3579])\b|\bcore\s?([3579])\b", s)
        t = next((g for g in (tier.groups() if tier else []) if g), None)
        model = re.search(r"\b(2\d{2}[a-z]{0,2})\b", s)
        if model:
            mm = model.group(1).upper()
            t = t or {"28": "9", "26": "7", "25": "7", "24": "5", "23": "5", "22": "5"}.get(mm[:2], "7")
            name = f"Core Ultra {t} {mm}"
            out.update(kind="CPU", canonical=name, terms=name)
        else:
            fam_ = f"Core Ultra {t or 7}"
            out.update(kind="CPU", choices=KNOWN[fam_], terms=fam_)
        return out
    m = re.search(r"\bi([3579])\s?-?\s?(\d{4,5}[a-z]{0,2})\b", s)
    if not m and re.search(r"\bi[3579]\b", s) and re.search(r"\b(1\d{4}[a-z]{0,2})\b", s):
        m = re.match(r"(\d)(.*)", re.search(r"\bi([3579])\b", s).group(1) + re.search(r"\b(1\d{4}[a-z]{0,2})\b", s).group(1))
    if m:
        name = f"Core i{m.group(1)}-{m.group(2).upper()}"
        out.update(kind="CPU", canonical=name, terms=name)
        return out

    # ---- generic: clean filler words, keep the rest ----
    words = [w for w in raw.split() if w.lower() not in {"price", "history", "india", "buy", "best", "cpu", "gpu"}]
    kind = ("RAM" if re.search(r"\bddr\d|ram\b", s) else "SSD" if re.search(r"\bssd|nvme|sn\d{3,4}\b", s)
            else "Power Supply" if re.search(r"\bpsu|smps|\d{3,4}w\b|rm\d{3,4}", s)
            else "Case" if re.search(r"\bcase|cabinet|lancool|tower\b", s)
            else "CPU Cooler" if re.search(r"\bcooler|aio|assassin\b", s) else "Other")
    out.update(kind=kind, canonical=" ".join(words) or raw, terms=" ".join(words) or raw)
    return out


def similarity(a, b):
    a, b = a.lower(), b.lower()
    ta, tb = set(re.findall(r"[a-z0-9]+", a)), set(re.findall(r"[a-z0-9]+", b))
    tok = len(ta & tb) / max(1, len(ta))
    return 0.6 * tok + 0.4 * difflib.SequenceMatcher(None, a, b).ratio()


def must_tokens(canon):
    """Tokens a result title must contain, e.g. RTX 5070 Ti -> {'5070','ti'}; avoids 5070 vs 5070 Ti mixups."""
    t = set(re.findall(r"[a-z0-9]+", canon.lower()))
    return {x for x in t if re.search(r"\d", x) or x in {"ti", "super", "xt", "xtx", "gre"}}


def title_matches(canon, title):
    tl = " " + re.sub(r"[^a-z0-9]+", " ", title.lower()) + " "
    req = must_tokens(canon)
    if not all(f" {x} " in tl or x in tl.replace(" ", "") for x in req):
        return False
    for bad in {"ti", "super", "xt", "xtx", "gre"} - {x for x in req}:
        if re.search(rf"\b{re.escape(canon.split()[-1].lower())}\s{bad}\b", tl):
            return False   # searched "RTX 5070" but page is "RTX 5070 Ti"
    return True


# =============================== 2. web search ===============================
def _secret(k):
    v = os.environ.get(k)
    if v:
        return v
    try:
        import streamlit as st
        return st.secrets.get(k)
    except Exception:
        return None


def web_search(query, n=8):
    """Returns ([{title,url,snippet}], provider)."""
    key, cx = _secret("GOOGLE_CSE_KEY"), _secret("GOOGLE_CSE_ID")
    if key and cx:
        try:
            r = requests.get("https://www.googleapis.com/customsearch/v1",
                             params={"key": key, "cx": cx, "q": query, "num": min(n, 10), "gl": "in"}, timeout=20)
            if r.ok:
                return [{"title": i.get("title", ""), "url": i.get("link", ""), "snippet": i.get("snippet", "")}
                        for i in r.json().get("items", [])], "Google"
        except requests.RequestException:
            pass
    bkey = _secret("BRAVE_API_KEY")
    if bkey:
        try:
            r = requests.get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": n, "country": "IN"},
                             headers={"X-Subscription-Token": bkey, "Accept": "application/json"}, timeout=20)
            if r.ok:
                return [{"title": i.get("title", ""), "url": i.get("url", ""), "snippet": i.get("description", "")}
                        for i in r.json().get("web", {}).get("results", [])], "Brave"
        except requests.RequestException:
            pass
    code, html = http_get(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&kl=in-en")
    if code != 200:
        return [], f"DuckDuckGo (HTTP {code})"
    out = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>', html, re.S):
        href = m.group(1)
        if "uddg=" in href:
            href = unquote(parse_qs(urlparse(href).query).get("uddg", [href])[0])
        out.append({"title": page_text(m.group(2)).strip(), "url": href, "snippet": page_text(m.group(3)).strip()})
    return out[:n], "DuckDuckGo"


def gpuprix_url(canon):
    c = canon.lower().replace(" ", "-")
    brand = "geforce-" if c.startswith(("rtx", "gtx")) else "radeon-" if c.startswith("rx") else ""
    return f"https://gpuprix.com/india/gpus/{brand}{c}" if brand else None


def discover(info, log):
    """Find one page per site for the product. Returns {site: {url,title,snippet}}."""
    canon = info["canonical"]
    found = {}
    if info["kind"] == "GPU":
        found["gpuprix.com"] = {"url": gpuprix_url(canon), "title": canon, "snippet": ""}
    for site in ["pricehistory.app", "pcpricetracker.in", "pcpaisa.in"] + ([] if "gpuprix.com" in found else ["gpuprix.com"]):
        if site == "gpuprix.com" and info["kind"] != "GPU":
            continue
        results, provider = web_search(f"{canon} price india site:{site}")
        hits = [r for r in results if site in r["url"] and title_matches(canon, r["title"] + " " + r["url"])]
        hits.sort(key=lambda r: -similarity(canon, r["title"]))
        log.append({"step": f"search {site}", "via": provider, "result": f"{len(hits)} match(es)" if hits else "no match"})
        if hits:
            found[site] = hits[0]
        time.sleep(0.6)
    return found


# =============================== 3. read each source ===============================
def parse_gpuprix(t):
    o = {"points": [], "stats": {}, "launch": {}, "specs": {}, "boards": []}
    g = lambda pat: re.search(pat, t)
    m = g(r"current low\s*" + P)
    upd = g(r"Last updated\s+(" + D2 + ")")
    day = parse_date(upd.group(1)) if upd else date.today()
    if m:
        o["points"].append((day, _p(m.group(1)), "gpuprix · India lowest"))
    for k, pat in (("low_12m", r"12-month low\s*" + P), ("median_12m", r"12-month median\s*" + P),
                   ("median_3m", r"3-month median\s*" + P)):
        m = g(pat)
        if m:
            o["stats"][k] = _p(m.group(1))
    m = g(r"MSRP:?\s*" + P)
    if m:
        o["launch"]["msrp"] = _p(m.group(1))
    m = g(r"Released\s+(" + D2 + ")") or g(r"Release(?:d| date)\s+(" + D2 + ")")
    if m:
        o["launch"]["date"] = parse_date(m.group(1))
    for k, pat in (("perf", r"Performance\s+(\d+)\s*/\s*100"), ("value", r"Value Score\s+([\d.]+)"),
                   ("vram", r"VRAM(?: Capacity)?\s+(\d+)\s*GB"), ("tdp", r"TDP\s+(\d+)\s*W"),
                   ("arch", r"Architecture\s+([A-Za-z0-9 ]+?)\s+(?:Process|CUDA|Stream|Base)")):
        m = g(pat)
        if m:
            o["specs"][k] = m.group(1)
    for m in re.finditer(r"([A-Z]{3,}[A-Z0-9 ]*?)\s+([A-Za-z0-9 +]+?)\s+(?:GeForce|Radeon)\s[^₹]{3,60}?(\d{3})\s?mm\s+" + P + r"\s+(In stock|Out of stock)", t):
        o["boards"].append({"brand": m.group(1).strip().title(), "series": m.group(2).strip(), "length_mm": int(m.group(3)),
                            "price": _p(m.group(4)), "in_stock": m.group(5) == "In stock"})
    return o


def parse_pricehistory(t):
    o = {"points": [], "stats": {}, "launch": {}, "rating": None, "title": ""}
    m = re.search(r"Price History\s+(" + D1 + ")", t)
    day = parse_date(m.group(1)) if m else date.today()
    m = re.search(r"(?:Price History\s+" + D1 + r",?\s*[\d:]+\s*[AP]M\s+)(.{10,160}?)\s+Price may vary", t)
    if m:
        o["title"] = m.group(1).strip()
    for m in re.finditer(r"Price Drop\s+(" + D1 + r")\s+" + P + r"\s*→\s*" + P, t):
        d = parse_date(m.group(1))
        o["points"] += [(d - timedelta(days=1), _p(m.group(2)), "pricehistory · before drop"), (d, _p(m.group(3)), "pricehistory · drop")]
    for lab, key in (("lowest ever", "Lowest Ever Price"), ("highest", "Highest Price")):
        m = re.search(key + r"\s+" + P + r"\s+(" + D1 + ")", t)
        if m:
            o["points"].append((parse_date(m.group(2)), _p(m.group(1)), f"pricehistory · {lab}"))
            o["stats"]["low_all" if "low" in lab else "high_all"] = _p(m.group(1))
    m = re.search(r"current Price in India is\s+" + P, t)
    if m:
        o["points"].append((day, _p(m.group(1)), "pricehistory · current"))
    m = re.search(r"Average Price\s+" + P, t)
    if m:
        o["stats"]["avg"] = _p(m.group(1))
    m = re.search(r"Based on\s+(\d+)\s+days price tracking", t)
    if m:
        o["launch"]["tracked_since"] = day - timedelta(days=int(m.group(1)))
    m = re.search(r"Rating\s+([\d.]+)\s*/\s*10", t)
    if m:
        c = re.search(r"(?:consist of|Based on)\s+(\d+)\s+(?:individual ratings|reviews)", t)
        o["rating"] = {"score": float(m.group(1)), "out_of": 10, "count": int(c.group(1)) if c else None, "source": "pricehistory.app"}
    o["points"] = sorted(set(o["points"]))
    return o


def parse_pcpricetracker(t):
    o = {"points": [], "stats": {}}
    m = re.search(r"Prices checked\s+(\d{1,2} [A-Z][a-z]{2} \d{4})", t)
    day = parse_date(m.group(1)) if m else date.today()
    m = re.search(r"Lowest available price\s+" + P, t)
    if m:
        o["points"].append((day, _p(m.group(1)), "pcpricetracker · lowest now"))
    for lab, pat in (("90-day low", r"90-day low\s+" + P + r"\s+Recorded\s+(\d{1,2} [A-Z][a-z]{2} \d{4})"),
                     ("90-day high", r"90-day high\s+" + P + r"\s+Recorded\s+(\d{1,2} [A-Z][a-z]{2} \d{4})"),
                     ("all-time low", r"All-time low\s+" + P + r"\s+[^·]*·\s*(\d{1,2} [A-Z][a-z]{2} \d{4})")):
        m = re.search(pat, t)
        if m:
            o["points"].append((parse_date(m.group(2)), _p(m.group(1)), f"pcpricetracker · {lab}"))
    m = re.search(r"30-day median of\s+" + P, t)
    if m:
        o["stats"]["median_30d"] = _p(m.group(1))
    return o


def parse_pcpaisa(t):
    o = {"points": [], "stats": {}}
    m = re.search(r"lowest live in-stock price at\s+" + P + r"\s+from\s+([A-Za-z0-9 .]+?)(?:,|\.|\s+ranging)", t)
    if m:
        o["points"].append((date.today(), _p(m.group(1)), f"pcpaisa · {m.group(2).strip()}"))
    m = re.search(r"tracked across\s+(\d+)\s+stores", t)
    if m:
        o["stats"]["stores"] = int(m.group(1))
    return o


PARSERS = {"gpuprix.com": parse_gpuprix, "pricehistory.app": parse_pricehistory,
           "pcpricetracker.in": parse_pcpricetracker, "pcpaisa.in": parse_pcpaisa}


def read_sources(pages, log, session=None):
    """pages: {site: {url, snippet}} -> merged result."""
    res = {"points": [], "stats": {}, "launch": {}, "specs": {}, "boards": [], "rating": None, "titles": [], "urls": {}}
    for site, pg in pages.items():
        if not pg or not pg.get("url"):
            continue
        code, html = http_get(pg["url"], session)
        text = page_text(html) if code == 200 else ""
        used = "page"
        if not text and pg.get("snippet"):
            text, used = pg["snippet"], "search snippet"
        o = PARSERS[site](text) if text else {}
        n = len(o.get("points", []))
        log.append({"step": f"read {site}", "via": used if text else "-",
                    "result": f"{n} price point(s)" if text else f"blocked (HTTP {code})"})
        res["urls"][site] = pg["url"]
        res["points"] += o.get("points", [])
        for k in ("stats", "launch", "specs"):
            for kk, vv in o.get(k, {}).items():
                res[k].setdefault(kk, vv)
        res["boards"] += o.get("boards", [])
        if o.get("rating") and not res["rating"]:
            res["rating"] = o["rating"]
        if o.get("title"):
            res["titles"].append(o["title"])
        time.sleep(0.5)
    res["points"] = sorted(set(res["points"]))
    return res


def lookup(query, choice=None):
    """Full pipeline. Returns (info, result, log)."""
    info = understand(query)
    if choice:
        info.update(canonical=choice, terms=choice, choices=[])
    log = []
    if not info["canonical"]:
        return info, None, log
    with requests.Session() as s:
        pages = discover(info, log)
        res = read_sources(pages, log, s)
    return info, res, log


# =============================== 4. watchlist & tracked history ===============================
def read_csv_text(text):
    return list(csv.DictReader(io.StringIO(text or "")))


def to_csv(rows, fields):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    seen = set()
    for r in sorted(rows, key=lambda r: (r.get("item", ""), str(r.get("date", "")))):
        k = tuple(str(r.get(f, "")) for f in fields)
        if k not in seen:
            seen.add(k)
            w.writerow(r)
    return buf.getvalue()


HIST_FIELDS = ["date", "item", "price", "source"]
REV_FIELDS = ["date", "item", "score", "out_of", "count", "source"]


def snapshot_rows(item, res, day=None):
    day = (day or date.today()).isoformat()
    prices = [{"date": d.isoformat(), "item": item, "price": p, "source": s} for d, p, s in res["points"]]
    reviews = []
    if res.get("rating"):
        r = res["rating"]
        reviews.append({"date": day, "item": item, "score": r["score"], "out_of": r["out_of"],
                        "count": r.get("count") or "", "source": r["source"]})
    return prices, reviews


def refresh_watch_item(w, session=None):
    """Re-read stored pages (no web search needed). Used by the daily job."""
    log = []
    pages = {site: {"url": u, "snippet": ""} for site, u in w.get("urls", {}).items()}
    res = read_sources(pages, log, session)
    return res, log
