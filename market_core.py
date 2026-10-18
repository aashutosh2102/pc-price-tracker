"""Whole-market scanner: crawls store category pages, parses specs from product names,
tracks first-seen / price changes, and finds alternatives for the tracked build."""
import csv
import io
import json
import re
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlencode, parse_qsl, urlunparse

import requests
from bs4 import BeautifulSoup

from tracker_core import HEADERS, ROOT, page_text

MARKET_CFG = ROOT / "market.json"
LATEST = ROOT / "data" / "market_latest.csv"
SEEN = ROOT / "data" / "market_seen.csv"
META = ROOT / "data" / "market_meta.json"
MHIST = ROOT / "data" / "market_history.csv"
MHIST_FIELDS = ["date", "category", "key", "brand", "name", "url", "price"]

PRICE_RE = re.compile(r"₹\s*([\d,]{3,})")
EMI_RE = re.compile(r"₹\s*[\d,]+\s*(?:/\s*mo\w*|per month|x\s*\d+\s*m|Starting EMI|EMI)", re.I)
OOS_RE = re.compile(r"Out\s*Of\s*Stock|Sold\s*out|Notify\s*Me|Coming\s*Soon", re.I)
NOISE_RE = re.compile(r"Add to Cart|Quick view|Product Compare \(%s\)|Add to wishlist|\bCompare\b|"
                      r"\d+\s*days?\s*\d+\s*hr\s*\d+\s*min\s*\d+\s*sc|Read more|Buy Now", re.I)
RATING = {"": 0, "Bronze": 1, "Silver": 2, "Gold": 3, "Platinum": 4, "Titanium": 5}


def load_market_cfg():
    return json.loads(MARKET_CFG.read_text(encoding="utf-8"))


# ======================= parsing listing pages =======================
def _with_params(url, **params):
    p = urlparse(url)
    q = dict(parse_qsl(p.query))
    q.update({k: str(v) for k, v in params.items()})
    return urlunparse(p._replace(query=urlencode(q)))


def parse_listing(html, base_url):
    """Return [{name, price, mrp, url, in_stock}] from a category page."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    links = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"]).split("?")[0].split("#")[0]
        text = " ".join(a.get_text(" ", strip=True).split())
        if "/product/" in href and len(text) >= 8:
            if href not in links or len(text) > len(links[href][0]):
                links[href] = (text, a)
    items = []
    for href, (name, a) in links.items():
        card, node = None, a
        for _ in range(8):  # climb to the smallest ancestor holding this product's price
            node = node.parent
            if node is None:
                break
            hrefs = {urljoin(base_url, x["href"]).split("?")[0].split("#")[0]
                     for x in node.find_all("a", href=True) if "/product/" in x["href"]}
            if len(hrefs) > 1:
                break
            if PRICE_RE.search(node.get_text(" ")):
                card = node
                break
        if card is None:
            continue
        txt = EMI_RE.sub(" ", " ".join(card.get_text(" ").split()).replace("\u20b9", "₹"))
        prices = [int(p.replace(",", "")) for p in PRICE_RE.findall(txt)]
        prices = [p for p in prices if p >= 100]
        if not prices:
            continue
        top = max(prices)
        prices = [p for p in prices if p >= 0.3 * top]
        items.append({"name": name, "price": min(prices), "mrp": top if len(prices) > 1 else None,
                      "url": href, "in_stock": not OOS_RE.search(txt)})
    return items or parse_listing_text(html, base_url)


def parse_listing_text(html, base_url):
    """Fallback when product links aren't found: parse 'Name ₹MRP ₹Offer' runs from page text."""
    t = NOISE_RE.sub(" ", page_text(html))
    t = re.sub(r"\s+", " ", t)
    m1 = re.search(r"Sort By.*?(?:Show(?:\s+\d+){2,5})?", t)
    start = m1.end() if m1 else 0
    m2 = re.search(r"Showing \d+ to \d+ of \d+", t[start:])
    body = t[start:start + m2.start()] if m2 else t[start:]
    items = []
    for m in re.finditer(r"(?:-\d+%\s+)?([A-Za-z0-9][^₹]{6,180}?)\s+₹\s?([\d,]+)(?:\s+₹\s?([\d,]+))?", body):
        a, b = int(m.group(2).replace(",", "")), m.group(3)
        b = int(b.replace(",", "")) if b else None
        name = m.group(1).strip(" -|")
        items.append({"name": name, "price": min(a, b) if b else a, "mrp": max(a, b) if b else None,
                      "url": f"{base_url}#{re.sub('[^a-z0-9]+', '-', name.lower())[:80]}", "in_stock": True})
    return items


def total_pages(html):
    m = re.search(r"Showing\s+\d+\s+to\s+\d+\s+of\s+(\d+)\s*\((\d+)\s*Pages?\)", page_text(html))
    return int(m.group(2)) if m else 1


def crawl_category(cat, cfg, session=None, progress=None):
    """Crawl every listing page of one category. Returns (items, log)."""
    s = session or requests.Session()
    items, log, seen_urls = [], [], set()
    must = re.compile(cat.get("must", "."), re.I)
    excl = re.compile(cat["exclude"], re.I) if cat.get("exclude") else None
    for base in cat["urls"]:
        page, pages = 1, 1
        while page <= min(pages, cfg.get("pages_limit", 15)):
            url = _with_params(base, limit=cfg.get("per_page", 100), page=page)
            try:
                r = s.get(url, headers=HEADERS, timeout=25)
            except requests.RequestException as e:
                log.append({"category": cat["name"], "url": url, "status": f"network error ({type(e).__name__})", "found": 0})
                break
            if r.status_code != 200:
                log.append({"category": cat["name"], "url": url, "status": f"blocked (HTTP {r.status_code})", "found": 0})
                break
            if page == 1:
                pages = total_pages(r.text)
            found = 0
            for it in parse_listing(r.text, url):
                if it["url"] in seen_urls or not must.search(it["name"]) or (excl and excl.search(it["name"])):
                    continue
                seen_urls.add(it["url"])
                it.update({"category": cat["name"], "store": urlparse(url).netloc.replace("www.", "")})
                it.update(parse_specs(cat["name"], it["name"]))
                items.append(it)
                found += 1
            log.append({"category": cat["name"], "url": url, "status": "ok", "found": found})
            if progress:
                progress(cat["name"], page, pages)
            page += 1
            time.sleep(cfg.get("pause_sec", 1.0))
    return items, log


def scan_market(cfg=None, categories=None, progress=None):
    cfg = cfg or load_market_cfg()
    items, log = [], []
    with requests.Session() as s:
        for cat in cfg["categories"]:
            if categories and cat["name"] not in categories:
                continue
            i, l = crawl_category(cat, cfg, s, progress)
            items += i
            log += l
    return items, log


# ======================= spec parsing from names =======================
def _num(pat, s, flags=re.I, cast=int):
    m = re.search(pat, s, flags)
    return cast(m.group(1)) if m else None


GPU_VRAM_VARIANTS = {"RTX 5060 Ti", "RX 9060 XT", "RTX 4060 Ti", "RTX 3050", "RTX 3060", "RX 7600 XT"}
AM5 = {"A620", "B650", "B650E", "X670", "X670E", "B840", "B850", "X870", "X870E"}
AM4 = {"A320", "B350", "X370", "B450", "X470", "A520", "B550", "X570"}
L1851 = {"H810", "B860", "Z890"}
L1700 = {"H610", "B660", "H670", "Z690", "B760", "H770", "Z790"}
L1200 = {"H410", "B460", "H470", "Z490", "H510", "B560", "H570", "Z590"}


def parse_specs(category, name):
    n = " ".join(name.split())
    brand = n.split()[0].title() if n else ""
    d = {"brand": brand, "key": ""}
    if category == "GPU":
        vram = _num(r"(\d{1,2})\s?GB?\b", n)
        key = ""
        m = re.search(r"\bRTX\s?-?(A\d{3,4})\b", n, re.I)
        if m:
            key = f"RTX {m.group(1).upper()}"
        m = m or re.search(r"\b(RTX|GTX)\s?-?(\d{3,4})\s?(Ti)?\s?(Super)?", n, re.I)
        if m and not key:
            key = f"{m.group(1).upper()} {m.group(2)}" + (" Ti" if m.group(3) else "") + (" Super" if m.group(4) else "")
        if not key:
            m = re.search(r"\bRX\s?-?(\d{3,4})\s?(XTX|XT|GRE)?\b", n, re.I)
            if m:
                key = f"RX {m.group(1)}" + (f" {m.group(2).upper()}" if m.group(2) else "")
        if not key:
            m = re.search(r"\bArc\s?([AB]\d{3})", n, re.I) or re.search(r"\bGT\s?(\d{3,4})\b", n)
            if m:
                key = ("Arc " if "arc" in m.group(0).lower() else "GT ") + m.group(1).upper()
        if key in GPU_VRAM_VARIANTS and vram:
            key = f"{key} {vram}GB"
        d.update(key=key or n, vram_gb=vram, maker="NVIDIA" if re.search(r"RTX|GTX|GT\s?\d|Quadro", n, re.I)
                 else "AMD" if re.search(r"\bRX\b|Radeon", n, re.I) else "Intel" if "Arc" in n else "")
    elif category == "CPU":
        key, socket = "", ""
        m = re.search(r"Threadripper\s?(?:PRO\s?)?(\d{4,5}[A-Z0-9]*)", n, re.I)
        if m:
            key, socket = f"Threadripper {m.group(1).upper()}", "sTR5"
        m = None if key else re.search(r"Ryzen\s?([3579])\s?(?:PRO\s?)?(\d{4}[A-Z0-9]*)", n, re.I)
        if m:
            key = f"Ryzen {m.group(1)} {m.group(2).upper()}"
            gen = int(m.group(2)[0])
            socket = "AM5" if gen >= 7 else "AM4"
        m = None if key else re.search(r"Core\s?Ultra\s?([3579])\s?-?(\d{3}[A-Z]*)", n, re.I)
        if m:
            key, socket = f"Core Ultra {m.group(1)} {m.group(2).upper()}", "LGA1851"
        m = None if key else re.search(r"Core\s?i([3579])[\s-]?(\d{4,5}[A-Z]*)", n, re.I)
        if m:
            key = f"Core i{m.group(1)}-{m.group(2).upper()}"
            g = int(m.group(2)[:2]) if len(m.group(2)) >= 5 else int(m.group(2)[0])
            socket = "LGA1700" if g >= 12 else "LGA1200" if g >= 10 else ""
        d.update(key=key or n, maker="AMD" if "ryzen" in n.lower() or "threadripper" in n.lower()
                 else "Intel" if re.search(r"intel|core", n, re.I) else "", socket=socket,
                 x3d="X3D" in n.upper(), igpu=not re.search(r"\d+F\b|\d+KF\b", n.upper()))
    elif category == "Motherboard":
        m = re.search(r"\b([ABHXZ])(\d{3})(E?)(?=M\b|M-|\b|-|\s|I\b)", n)
        chip = f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else ""
        socket = ("AM5" if chip in AM5 else "AM4" if chip in AM4 else "LGA1851" if chip in L1851
                  else "LGA1700" if chip in L1700 else "LGA1200" if chip in L1200 else "")
        form = ("ITX" if re.search(r"\bITX\b|-I\b|\bI\b", n) else
                "mATX" if re.search(r"M-?ATX|Micro|\b[ABHXZ]\d{3}E?M\b|[ABHXZ]\d{3}E?M-", n, re.I) else "ATX")
        d.update(key=f"{chip} {form}".strip(), chipset=chip, socket=socket, form=form,
                 wifi=bool(re.search(r"wi-?fi|\bAX\b", n, re.I)), ddr=_num(r"DDR(\d)", n))
    elif category == "RAM":
        ddr = _num(r"DDR(\d)", n)
        m = re.search(r"(\d+)\s?GB\s*\(\s*(\d+)\s?GB?\s*[xX×*]\s*(\d)\s*\)", n) or \
            re.search(r"(\d+)\s?GB\s*\(\s*(\d)\s*[xX×*]\s*(\d+)\s?GB\s*\)", n)
        if m:
            total, kit = int(m.group(1)), True
        else:
            total = _num(r"(\d+)\s?GB", n)
            kit = bool(re.search(r"\bkit\b|dual channel|[x×]\s?2\b", n, re.I))
        speed = _num(r"(\d{4})\s?(?:MHz|MT)", n) or _num(r"DDR\d-(\d{4})", n)
        cl = _num(r"CL\s?(\d{2})", n)
        d.update(key=f"DDR{ddr or '?'} {total}GB{' kit' if kit else ''} {speed or ''}".strip(),
                 ddr=ddr, total_gb=total, kit=kit, speed=speed, cl=cl)
    elif category == "SSD":
        caps = [(float(a) * (1000 if u.upper() == "TB" else 1)) for a, u in re.findall(r"(\d+(?:\.\d+)?)\s?(TB|GB)\b", n, re.I)]
        cap = int(max([c for c in caps if c >= 120], default=0)) or None
        gen = _num(r"Gen\s?(\d)", n)
        nvme = bool(re.search(r"NVMe|M\.2", n, re.I)) and not re.search(r"\bSATA\b", n, re.I)
        d.update(key=f"{cap}GB {'Gen' + str(gen) if gen else ('NVMe' if nvme else 'SATA')}" if cap else n,
                 capacity_gb=cap, gen=gen, nvme=nvme)
    elif category == "Power Supply":
        watt = _num(r"(\d{3,4})\s?W(?:att)?\b", n) or _num(r"\b[A-Z]{1,6}-?(\d{3,4})[A-Za-z]{0,3}\b", n, 0)
        watt = watt if watt and 300 <= watt <= 2500 else None
        rating = (re.search(r"Titanium|Platinum|Gold|Silver|Bronze", n, re.I) or [""])[0].title()
        mod = "Full" if re.search(r"Fully Modular", n, re.I) else "Semi" if re.search(r"Semi", n, re.I) \
            else "Non" if re.search(r"Non Modular", n, re.I) else ""
        d.update(key=f"{watt or '?'}W {rating or 'Unrated'}", watt=watt, rating=rating,
                 rating_rank=RATING.get(rating, 0), modular=mod, atx3=bool(re.search(r"ATX\s?3|PCIE?\s?5", n, re.I)))
    elif category == "CPU Cooler":
        liquid = bool(re.search(r"Liquid|AIO", n, re.I))
        rad = max([int(x) for x in re.findall(r"\b(120|140|240|280|360|420)\b(?:\s?mm)?", n)], default=None) if liquid else None
        d.update(key=f"Liquid {rad or ''}mm".replace(" mm", "") if liquid else
                 ("Air dual-tower" if re.search(r"Dual Tower|AK620|AG620|Peerless|620|Phantom", n, re.I) else "Air"),
                 type="Liquid" if liquid else "Air", radiator_mm=rad)
    elif category == "Case":
        size = ("Full Tower" if re.search(r"Full Tower|Super Tower", n, re.I) else "Mid Tower" if re.search(r"Mid Tower", n, re.I)
                else "Mini Tower" if re.search(r"Mini Tower", n, re.I) else "SFF" if re.search(r"SFF|Small Form|ITX", n, re.I) else "")
        form = (re.search(r"E-ATX|M-ATX|mATX|ATX|ITX", n, re.I) or [""])[0].upper()
        d.update(key=f"{size or 'Case'} {form}".strip(), size=size, form=form)
    return d


# ======================= history (first seen, price changes) =======================
SEEN_FIELDS = ["url", "category", "name", "key", "first_seen", "last_seen", "price", "prev_price", "low_price", "low_date"]


def read_csv_text(text):
    return list(csv.DictReader(io.StringIO(text))) if text else []


def to_csv_text(rows, fields=None):
    if not rows:
        return ""
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def update_seen(seen_rows, items, meta, today=None):
    """Merge a new scan into the seen-history. Returns (seen_rows, meta, changes)."""
    today = (today or date.today()).isoformat()
    first_scan = not seen_rows
    meta = dict(meta or {})
    meta.setdefault("baseline", today)
    seen = {r["url"]: r for r in seen_rows}
    old_keys = {(r["category"], r["key"]) for r in seen_rows}
    changes = {"new_products": [], "new_models": [], "drops": [], "new_lows": [], "history": []}
    for it in items:
        if not it.get("in_stock", True):
            continue
        p = int(it["price"])
        r = seen.get(it["url"])
        hrow = {"date": today, "category": it["category"], "key": it.get("key", ""), "brand": it.get("brand", ""),
                "name": it["name"], "url": it["url"], "price": p}
        if r is None or int(float(r["price"])) != p:
            changes["history"].append(hrow)
        if r is None:
            seen[it["url"]] = {"url": it["url"], "category": it["category"], "name": it["name"], "key": it.get("key", ""),
                               "first_seen": today, "last_seen": today, "price": p, "prev_price": "",
                               "low_price": p, "low_date": today}
            if not first_scan:
                changes["new_products"].append(it)
                if (it["category"], it.get("key", "")) not in old_keys:
                    changes["new_models"].append(it)
                    old_keys.add((it["category"], it.get("key", "")))
            continue
        old = int(float(r["price"]))
        if p != old:
            r["prev_price"] = old
            if p <= old * 0.95:
                changes["drops"].append({**it, "old_price": old, "drop_pct": (old - p) / old})
        if p < int(float(r["low_price"] or p)):
            r["low_price"], r["low_date"] = p, today
            changes["new_lows"].append(it)
        r.update(price=p, last_seen=today, name=it["name"], key=it.get("key", r.get("key", "")))
    meta["last_scan"] = today
    meta["items"] = len(items)
    return list(seen.values()), meta, changes


def recent_changes(seen_rows, meta, days=7, today=None):
    """Rebuild 'what's new' from stored history (for the dashboard)."""
    today = today or date.today()
    base = meta.get("baseline", "")
    new = [r for r in seen_rows if r["first_seen"] != base and
           (today - date.fromisoformat(r["first_seen"])).days <= days]
    drops = []
    for r in seen_rows:
        try:
            pp, p = float(r["prev_price"]), float(r["price"])
        except (ValueError, TypeError):
            continue
        if p <= pp * 0.95 and (today - date.fromisoformat(r["last_seen"])).days <= days:
            drops.append({**r, "drop_pct": (pp - p) / pp})
    first_by_key = {}
    for r in seen_rows:
        k = (r["category"], r["key"])
        first_by_key[k] = min(first_by_key.get(k, r["first_seen"]), r["first_seen"])
    new_models = [{"category": c, "key": k, "first_seen": f} for (c, k), f in first_by_key.items()
                  if f != base and (today - date.fromisoformat(f)).days <= days * 4]
    return new, drops, new_models


# ======================= matching against the tracked build =======================
def _truthy(v):
    return str(v).strip().lower() in ("true", "1", "yes")


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def matches(item, rule):
    if item.get("category") != rule.get("category"):
        return False
    if str(item.get("in_stock", True)).lower() == "false":
        return False
    k, n = str(item.get("key", "")), str(item.get("name", ""))
    if "key_in" in rule and k not in rule["key_in"]:
        return False
    if "name_any" in rule and not any(x.lower() in n.lower() for x in rule["name_any"]):
        return False
    if "socket" in rule and item.get("socket") != rule["socket"]:
        return False
    if rule.get("wifi") and not _truthy(item.get("wifi")):
        return False
    if "chipset_in" in rule and item.get("chipset") not in rule["chipset_in"]:
        return False
    if "ddr" in rule and _f(item.get("ddr")) != rule["ddr"]:
        return False
    if "total_gb" in rule and _f(item.get("total_gb")) != rule["total_gb"]:
        return False
    if rule.get("kit") and not _truthy(item.get("kit")):
        return False
    if "min_speed" in rule and (_f(item.get("speed")) or 0) < rule["min_speed"]:
        return False
    if "capacity_gb" in rule and (_f(item.get("capacity_gb")) or 0) < rule["capacity_gb"] * 0.95:
        return False
    if "min_gen" in rule and (_f(item.get("gen")) or 0) < rule["min_gen"]:
        return False
    if "min_watt" in rule and (_f(item.get("watt")) or 0) < rule["min_watt"]:
        return False
    if "max_watt" in rule and (_f(item.get("watt")) or 99999) > rule["max_watt"]:
        return False
    if "min_rating" in rule and (_f(item.get("rating_rank")) or 0) < RATING[rule["min_rating"]]:
        return False
    return True


def best_alternatives(items, rule, n=5):
    return sorted([i for i in items if matches(i, rule)], key=lambda i: float(i["price"]))[:n]


def cheapest_per_key(items, category, keys=None):
    best = {}
    for i in items:
        if i.get("category") != category or str(i.get("in_stock", True)).lower() == "false":
            continue
        if keys and i.get("key") not in keys:
            continue
        k = i.get("key")
        if k not in best or float(i["price"]) < float(best[k]["price"]):
            best[k] = i
    return best


# ======================= local storage helpers =======================
def save_local(latest_text, seen_text, meta, hist_text=None):
    LATEST.parent.mkdir(parents=True, exist_ok=True)
    if hist_text is not None:
        MHIST.write_text(hist_text, encoding="utf-8")
    LATEST.write_text(latest_text, encoding="utf-8")
    SEEN.write_text(seen_text, encoding="utf-8")
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def load_local():
    lt = LATEST.read_text(encoding="utf-8") if LATEST.exists() else ""
    st = SEEN.read_text(encoding="utf-8") if SEEN.exists() else ""
    mt = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
    return lt, st, mt


def load_local_history():
    return MHIST.read_text(encoding="utf-8") if MHIST.exists() else ""


def run_scan_and_merge(hist_text, seen_text, meta, progress=None, cfg=None):
    """Returns (latest_csv, seen_csv, meta, changes, log, history_csv)."""
    items, log = scan_market(cfg, progress=progress)
    if not items:
        return None, None, meta, {"new_products": [], "new_models": [], "drops": [], "new_lows": [], "history": []}, log, hist_text
    today = date.today().isoformat()
    for i in items:
        i["scanned"] = today
    seen_rows, meta, changes = update_seen(read_csv_text(seen_text), items, meta)
    hist = read_csv_text(hist_text or "") + changes["history"]
    return (to_csv_text(items), to_csv_text(seen_rows, SEEN_FIELDS), meta, changes, log,
            to_csv_text(hist, MHIST_FIELDS))
