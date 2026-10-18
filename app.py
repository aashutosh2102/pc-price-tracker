"""PC Price Tracker - Streamlit dashboard (your build + whole market).

Local:  streamlit run app.py
Cloud:  share.streamlit.io. Secrets (App settings > Secrets):
        GITHUB_REPO = "aashutosh2102/pc-price-tracker"
        GITHUB_TOKEN = "github_pat_..."   (fine-grained, this repo only, Contents: Read and write)
"""
import base64
import json
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

from market_core import (best_alternatives, cheapest_per_key, load_local, load_market_cfg, read_csv_text,
                         recent_changes, run_scan_and_merge, save_local)
from tracker_core import fetch_part, load_config, read_rows, rows_to_csv, save_rows, summarize, upsert

st.set_page_config(page_title="PC Price Tracker", page_icon="🖥️", layout="wide")


# ======================= GitHub / local storage =======================
def secret(key):
    try:
        return st.secrets.get(key)
    except Exception:
        return None


REPO, TOKEN = secret("GITHUB_REPO"), secret("GITHUB_TOKEN")
GH = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
if TOKEN:
    GH["Authorization"] = f"Bearer {TOKEN}"


def gh_url(path):
    return f"https://api.github.com/repos/{REPO}/contents/{path}"


def gh_get(path):
    if not REPO:
        return None
    r = requests.get(gh_url(path), headers={**GH, "Accept": "application/vnd.github.raw+json"}, timeout=20)
    return r.text if r.ok else None


def gh_put(path, text, message):
    cur = requests.get(gh_url(path), headers=GH, timeout=20)
    body = {"message": message, "content": base64.b64encode(text.encode()).decode()}
    if cur.ok:
        body["sha"] = cur.json().get("sha")
    r = requests.put(gh_url(path), headers=GH, json=body, timeout=30)
    if r.ok:
        return True, ""
    detail = r.json().get("message", "") if "json" in r.headers.get("content-type", "") else ""
    hint = {401: "Token invalid or expired.", 403: "Token needs 'Contents: Read and write' on this repo.",
            404: "Check GITHUB_REPO and token repo access."}.get(r.status_code, "")
    return False, f"{path}: HTTP {r.status_code} {detail} {hint}"


def persist(files, message):
    """files: {repo_path: text}. Saves to GitHub if configured, else locally."""
    if REPO and TOKEN:
        errs = [e for ok, e in (gh_put(p, t, message) for p, t in files.items()) if not ok]
        return (False, "GitHub save failed: " + " | ".join(errs)) if errs else (True, "Saved to GitHub ✅")
    try:
        for p, t in files.items():
            from pathlib import Path
            fp = Path(__file__).parent / p
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(t, encoding="utf-8")
        return True, "Saved locally (add GITHUB_TOKEN in Secrets to keep data on Streamlit Cloud)"
    except OSError as e:
        return False, f"Could not save: {e}"


def show(ok, msg):
    (st.success if ok else st.error)(msg)


@st.cache_data(ttl=300, show_spinner=False)
def load_all():
    if REPO:
        p, lt, sn, mt = (gh_get("data/prices.csv"), gh_get("data/market_latest.csv"),
                         gh_get("data/market_seen.csv"), gh_get("data/market_meta.json"))
        if p is not None:
            return read_rows(p), lt or "", sn or "", json.loads(mt) if mt else {}, "GitHub repo"
    lt, sn, mt = load_local()
    return read_rows(), lt, sn, mt, "local files"


def github_check():
    if not REPO:
        return [("❌", "GITHUB_REPO secret is missing")]
    if not TOKEN:
        return [("❌", "GITHUB_TOKEN secret is missing")]
    r = requests.get(f"https://api.github.com/repos/{REPO}", headers=GH, timeout=20)
    if r.status_code == 401:
        return [("❌", "Token invalid or expired")]
    if r.status_code == 404:
        return [("❌", f"Repo '{REPO}' not found or token has no access")]
    push = r.json().get("permissions", {}).get("push")
    return [("✅", f"Repo found: {REPO}"),
            ("✅" if push else "❌", "Write access" if push else "No write access - set Contents: Read and write"),
            ("✅" if gh_get("data/prices.csv") else "⚠️", "data/prices.csv readable")]


# ======================= fetch helpers =======================
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_build(_cfg, day):
    results, logs = {}, []
    with requests.Session() as s:
        for p in _cfg["parts"]:
            price, src, log = fetch_part(p, s, pause=0.5)
            logs += log
            if price:
                results[p["name"]] = (price, src)
    return results, logs


def do_market_scan(seen_text, meta):
    bar = st.progress(0.0, text="Scanning the whole market…")
    cats = [c["name"] for c in load_market_cfg()["categories"]]

    def prog(cat, page, pages):
        i = cats.index(cat) if cat in cats else 0
        bar.progress(min(1.0, (i + page / max(pages, 1)) / len(cats)), text=f"Scanning {cat}: page {page}/{pages}")

    lt, sn, meta2, ch, log = run_scan_and_merge(None, seen_text, meta, prog)
    bar.empty()
    st.session_state["market_log"] = log
    if lt is None:
        st.warning("Market scan got no products (stores may be blocking this server). "
                   "Your Windows task or GitHub Action can fill this in instead.")
        return None
    ok, msg = persist({"data/market_latest.csv": lt, "data/market_seen.csv": sn,
                       "data/market_meta.json": json.dumps(meta2, indent=2)}, f"Market scan {date.today()}")
    st.session_state["save_msg"] = (ok, f"Market: {msg}")
    load_all.clear()
    return lt, sn, meta2


# ======================= load =======================
cfg = load_config()
mcfg = load_market_cfg()
names = [p["name"] for p in cfg["parts"]]
rows, latest_text, seen_text, meta, where = load_all()
rows = st.session_state.get("rows", rows)
if "market" in st.session_state:
    latest_text, seen_text, meta = st.session_state["market"]

# ======================= sidebar =======================
with st.sidebar:
    st.header("⚙️ Controls")
    auto = st.toggle("Auto-fetch build prices on load", value=True, help="Once per 6 hours.")
    auto_mkt = st.toggle("Auto-scan whole market if older than 1 day", value=True,
                         help="Scans ~1,300 products from store category pages (~30-60 s).")
    if st.button("🔄 Fetch build prices now", width="stretch"):
        fetch_build.clear()
        st.session_state.pop("auto_done", None)
    if st.button("🛒 Scan whole market now", width="stretch"):
        st.session_state["force_market"] = True
    cfg["half_life_days"] = st.slider("Recency half-life (days)", 10, 120, cfg.get("half_life_days", 45))

    st.divider()
    st.subheader("➕ Add a quote")
    with st.form("add", clear_on_submit=True):
        part = st.selectbox("Part", names)
        price = st.number_input("Price (₹)", min_value=100, step=100, value=None, placeholder="e.g. 74990")
        day = st.date_input("Date", value=date.today(), max_value=date.today())
        src = st.text_input("Source", placeholder="e.g. Kryptronix, Nehru Place")
        if st.form_submit_button("Save quote", width="stretch") and price:
            rows = upsert(rows, part, price, src or "manual quote", day)
            st.session_state["rows"] = rows
            show(*persist({"data/prices.csv": rows_to_csv(rows)}, f"Quote: {part} ₹{int(price):,}"))
            load_all.clear()
    with st.expander("🔧 Check GitHub connection"):
        if st.button("Run check", width="stretch"):
            for icon, msg in github_check():
                st.write(f"{icon} {msg}")
    st.caption(f"Data: **{where}** · {len(rows)} build prices · market scan: {meta.get('last_scan', 'never')}")

# ======================= automatic fetches =======================
if auto and "auto_done" not in st.session_state:
    with st.spinner("Fetching today's build prices…"):
        results, logs = fetch_build(cfg, date.today().isoformat())
    st.session_state.update(auto_done=True, fetch_log=logs)
    changed = {k: v for k, v in results.items()
               if not any(r["part"] == k and r["date"] == date.today() and r["price"] == v[0] for r in rows)}
    if changed:
        for k, (p, s) in changed.items():
            rows = upsert(rows, k, p, s)
        st.session_state["rows"] = rows
        st.session_state["save_msg"] = persist({"data/prices.csv": rows_to_csv(rows)}, f"Auto price update {date.today()}")
        load_all.clear()

stale = meta.get("last_scan") != date.today().isoformat() and (
    not meta.get("last_scan") or date.today() - date.fromisoformat(meta["last_scan"]) >= timedelta(days=1))
if st.session_state.pop("force_market", False) or (auto_mkt and stale and "market_tried" not in st.session_state):
    st.session_state["market_tried"] = True
    res = do_market_scan(seen_text, meta)
    if res:
        latest_text, seen_text, meta = res
        st.session_state["market"] = res

market = read_csv_text(latest_text)
seen = read_csv_text(seen_text)
mdf = pd.DataFrame(market)
if not mdf.empty:
    mdf["price"] = pd.to_numeric(mdf["price"], errors="coerce")
    mdf["mrp"] = pd.to_numeric(mdf.get("mrp"), errors="coerce")
    mdf["in_stock"] = mdf["in_stock"].astype(str).str.lower() != "false"

# ======================= header =======================
st.title("🖥️ PC Price Tracker")
st.caption("Your Ryzen 7 9700X + RTX 5070 build, plus every CPU, GPU, motherboard, RAM, SSD, PSU, cooler and case in the market.")
if "save_msg" in st.session_state:
    show(*st.session_state["save_msg"])

tab_build, tab_market, tab_new = st.tabs(["🎯 My Build", "🛒 Whole Market", "🆕 What's New & Deals"])

# ======================= TAB 1: my build =======================
with tab_build:
    if st.session_state.get("fetch_log"):
        lg = pd.DataFrame(st.session_state["fetch_log"])
        ok_parts = lg[lg["price"].notna()]["part"].nunique()
        with st.expander(f"📡 Today's build fetch: {ok_parts}/{len(names)} parts updated automatically — details"):
            lg["price"] = lg["price"].map(lambda v: f"₹{int(v):,}" if pd.notna(v) else "-")
            st.dataframe(lg, hide_index=True, width="stretch")

    with st.expander("🎯 Targets & market outlook (edit for this session)"):
        ed = st.data_editor(pd.DataFrame([{"Part": p["name"], "Target (₹)": p["target"],
                                           "Outlook % / 90 days": p["outlook_90d"] * 100, "Basis": p["outlook_basis"]}
                                          for p in cfg["parts"]]),
                            disabled=["Part", "Basis"], hide_index=True, width="stretch")
        for p, (_, r) in zip(cfg["parts"], ed.iterrows()):
            p["target"], p["outlook_90d"] = int(r["Target (₹)"]), float(r["Outlook % / 90 days"]) / 100
        st.caption("Permanent changes: edit parts.json in GitHub.")

    summary = summarize(rows, cfg)
    have = [s for s in summary if s["f"]]
    tl, tt = sum(s["f"]["latest"] for s in have), sum(s["part"]["target"] for s in have)
    t90, t1y = sum(s["f"]["f90"] for s in have), sum(s["f"]["f1y"] for s in have)
    alt_total = 0
    alts = {}
    for p in cfg["parts"]:
        a = best_alternatives(market, p.get("match", {}), 1) if market else []
        alts[p["name"]] = a[0] if a else None
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Build cost today", f"₹{tl:,}", f"₹{tl - tt:,} vs target", delta_color="inverse")
    c2.metric("Your target", f"₹{tt:,}")
    c3.metric("Forecast in 90 days", f"₹{t90:,}", f"{t90 - tl:+,}", delta_color="inverse")
    c4.metric("Forecast in 1 year", f"₹{t1y:,}", f"{t1y - tl:+,}", delta_color="inverse")

    ICON = {"BUY": "🟢", "Rising": "🟠", "Falling -": "🔵", "Falling slowly": "⚪", "Flat": "⚪"}
    table = []
    for s in summary:
        p, f, a = s["part"], s["f"], alts.get(s["part"]["name"])
        row = {"Part": p["name"], "Model": p["model"]}
        if f:
            row.update({"Signal": f"{next((v for k, v in ICON.items() if f['signal'].startswith(k)), '⚪')} {f['signal']}",
                        "Latest (₹)": f["latest"], "Target (₹)": p["target"], "Updated": f["last_date"],
                        "90-day change": f["change_90d"] * 100, "In 90 days (₹)": f["f90"], "In 1 year (₹)": f["f1y"],
                        "Target likely": f["when"]})
        if a:
            ap = int(float(a["price"]))
            row.update({"Cheapest equivalent (₹)": ap, "Equivalent": a["name"], "Link": a["url"],
                        "Cheaper than yours by (₹)": (f["latest"] - ap) if f else None})
        table.append(row)
    cols = ["Signal", "Part", "Model", "Latest (₹)", "Target (₹)", "Cheapest equivalent (₹)", "Cheaper than yours by (₹)",
            "Equivalent", "Link", "90-day change", "In 90 days (₹)", "In 1 year (₹)", "Target likely", "Updated"]
    money = st.column_config.NumberColumn(format="₹%d")
    st.dataframe(pd.DataFrame(table).reindex(columns=cols), hide_index=True, width="stretch", column_config={
        **{c: money for c in cols if "(₹)" in c},
        "90-day change": st.column_config.NumberColumn(format="%+.1f%%"),
        "Link": st.column_config.LinkColumn(display_text="open"),
        "Updated": st.column_config.DateColumn(format="DD MMM YYYY")})
    st.caption("**Cheapest equivalent** = lowest in-stock product in the market scan matching your part's rules "
               "(e.g. any RTX 5070, any DDR5 32GB 2-stick 6000+ kit). Rules live in parts.json → match.")

    st.subheader("📈 Price history & forecast")
    sel = st.selectbox("Part", names, index=names.index("GPU") if "GPU" in names else 0)
    s = next(x for x in summary if x["part"]["name"] == sel)
    pts = sorted((r["date"], r["price"]) for r in rows if r["part"] == sel)
    if pts:
        f, p = s["f"], s["part"]
        last = f["last_date"]
        fig = go.Figure()
        fig.add_scatter(x=[d for d, _ in pts], y=[v for _, v in pts], mode="lines+markers", name="Recorded")
        fig.add_scatter(x=[last, last + timedelta(days=30), last + timedelta(days=90), last + timedelta(days=365)],
                        y=[f["latest"], f["f30"], f["f90"], f["f1y"]], mode="lines+markers", name="Forecast",
                        line=dict(dash="dash"))
        fig.add_hline(y=p["target"], line_color="green", annotation_text=f"Target ₹{p['target']:,}")
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10), yaxis_tickprefix="₹",
                          legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, width="stretch")
        st.caption(f"Market outlook basis: {p['outlook_basis']}")

# ======================= TAB 2: whole market =======================
with tab_market:
    if mdf.empty:
        st.info("No market scan yet. Click **🛒 Scan whole market now** in the sidebar, "
                "or let the Windows task / GitHub Action run `update_market.py`.")
    else:
        st.caption(f"{len(mdf):,} products · scanned {meta.get('last_scan', '?')} · source: "
                   f"{', '.join(sorted(mdf['store'].dropna().unique()))}")
        counts = mdf.groupby("category").size()
        st.write(" · ".join(f"**{c}** {n}" for c, n in counts.items()))
        cats = [c["name"] for c in mcfg["categories"] if c["name"] in counts.index]
        cat = st.radio("Category", cats, horizontal=True)
        d = mdf[mdf["category"] == cat].copy()
        f1, f2, f3, f4 = st.columns([2, 2, 3, 1])
        q = f1.text_input("Search", placeholder="e.g. 5070, Lancool, CL30")
        brands = f2.multiselect("Brand", sorted(d["brand"].dropna().unique()))
        lo, hi = int(d["price"].min()), int(d["price"].max())
        pr = f3.slider("Price (₹)", lo, max(hi, lo + 1), (lo, max(hi, lo + 1)), step=500)
        instock = f4.checkbox("In stock", value=True)
        if q:
            d = d[d["name"].str.contains(q, case=False, regex=False) | d["key"].astype(str).str.contains(q, case=False, regex=False)]
        if brands:
            d = d[d["brand"].isin(brands)]
        d = d[d["price"].between(*pr)]
        if instock:
            d = d[d["in_stock"]]
        view = st.radio("View", ["Cheapest per model", "All products"], horizontal=True)

        extra = {"GPU": ["vram_gb", "maker"], "CPU": ["socket", "maker", "x3d"], "Motherboard": ["chipset", "socket", "form", "wifi"],
                 "RAM": ["ddr", "total_gb", "kit", "speed", "cl"], "SSD": ["capacity_gb", "gen", "nvme"],
                 "Power Supply": ["watt", "rating", "modular", "atx3"], "CPU Cooler": ["type", "radiator_mm"],
                 "Case": ["size", "form"]}.get(cat, [])
        extra = [c for c in extra if c in d.columns]
        if cat == "RAM" and "total_gb" in d:
            d["₹ per GB"] = d["price"] / pd.to_numeric(d["total_gb"], errors="coerce")
        if cat == "SSD" and "capacity_gb" in d:
            d["₹ per TB"] = d["price"] / (pd.to_numeric(d["capacity_gb"], errors="coerce") / 1000)
        if cat == "GPU":
            sc = {k: v for k, v in mcfg.get("gpu_scores", {}).items() if not k.startswith("_")}
            d["Perf score"] = d["key"].map(sc)
            d["₹ per perf point"] = d["price"] / d["Perf score"]
        value_cols = [c for c in ["₹ per GB", "₹ per TB", "Perf score", "₹ per perf point"] if c in d.columns]

        if view == "Cheapest per model":
            g = d.sort_values("price").groupby("key", as_index=False).agg(
                price=("price", "first"), name=("name", "first"), url=("url", "first"), listings=("name", "size"),
                **{c: (c, "first") for c in extra + value_cols})
            g = g.sort_values("price")
            show_cols = ["key", "price", "listings"] + value_cols + extra + ["name", "url"]
            st.dataframe(g[show_cols], hide_index=True, width="stretch", height=480, column_config={
                "key": "Model", "price": st.column_config.NumberColumn("Cheapest (₹)", format="₹%d"),
                "name": "Cheapest listing", "url": st.column_config.LinkColumn("Link", display_text="open"),
                **{c: st.column_config.NumberColumn(c, format="₹%d") for c in value_cols if c.startswith("₹")}})
            top = g.head(30)
            fig = px.bar(top, x="price", y="key", orientation="h", height=max(300, 22 * len(top)),
                         labels={"price": "Cheapest (₹)", "key": ""})
            fig.update_layout(yaxis=dict(autorange="reversed"), margin=dict(l=10, r=10, t=10, b=10), xaxis_tickprefix="₹")
            st.plotly_chart(fig, width="stretch")
        else:
            show_cols = ["name", "key", "price", "mrp", "in_stock"] + value_cols + extra + ["store", "url"]
            st.dataframe(d.sort_values("price")[[c for c in show_cols if c in d.columns]], hide_index=True,
                         width="stretch", height=560, column_config={
                    "name": "Product", "key": "Model", "price": st.column_config.NumberColumn("Price (₹)", format="₹%d"),
                    "mrp": st.column_config.NumberColumn("MRP (₹)", format="₹%d"),
                    "url": st.column_config.LinkColumn("Link", display_text="open"),
                    **{c: st.column_config.NumberColumn(c, format="₹%d") for c in value_cols if c.startswith("₹")}})
        if cat == "GPU":
            st.caption(f"Perf score: {mcfg.get('gpu_scores', {}).get('_source', '')} Add more in market.json → gpu_scores.")
        st.download_button("Download this view (CSV)", d.to_csv(index=False), f"market_{cat}.csv", "text/csv")

    if st.session_state.get("market_log"):
        with st.expander("📡 Last market scan log"):
            st.dataframe(pd.DataFrame(st.session_state["market_log"]), hide_index=True, width="stretch")

# ======================= TAB 3: what's new =======================
with tab_new:
    if not seen:
        st.info("Needs at least one market scan. The first scan sets the baseline; "
                "from the next scan on, new products, new chips and price drops show here.")
    else:
        days = st.slider("Look back (days)", 1, 60, 7)
        new, drops, new_models = recent_changes(seen, meta, days)
        a, b, c = st.columns(3)
        a.metric("New models / chips", len(new_models))
        b.metric("New products", len(new))
        c.metric("Price drops ≥5%", len(drops))
        st.caption(f"Baseline scan: {meta.get('baseline', '?')} (products already listed then are not counted as new).")

        st.subheader("🚀 New models / chips (e.g. a new GPU or CPU launch)")
        if new_models:
            nm = pd.DataFrame(new_models)
            best = {(i["category"], i["key"]): i for i in market}
            nm["cheapest (₹)"] = [int(float(cheapest_per_key(market, r.category, [r.key]).get(r.key, {}).get("price", 0) or 0))
                                  for r in nm.itertuples()]
            st.dataframe(nm.sort_values("first_seen", ascending=False), hide_index=True, width="stretch",
                         column_config={"cheapest (₹)": st.column_config.NumberColumn(format="₹%d")})
        else:
            st.write("Nothing new in this period.")

        st.subheader("📉 Price drops")
        if drops:
            dd = pd.DataFrame(drops)
            dd["price"] = pd.to_numeric(dd["price"]); dd["prev_price"] = pd.to_numeric(dd["prev_price"])
            dd["drop %"] = dd["drop_pct"] * 100
            st.dataframe(dd.sort_values("drop %", ascending=False)[["category", "name", "prev_price", "price", "drop %", "low_price", "url"]],
                         hide_index=True, width="stretch", column_config={
                    "prev_price": st.column_config.NumberColumn("Was (₹)", format="₹%d"),
                    "price": st.column_config.NumberColumn("Now (₹)", format="₹%d"),
                    "low_price": st.column_config.NumberColumn("All-time low (₹)", format="₹%d"),
                    "drop %": st.column_config.NumberColumn(format="%.0f%%"),
                    "url": st.column_config.LinkColumn("Link", display_text="open")})
        else:
            st.write("No drops of 5% or more in this period.")

        st.subheader("🆕 New products")
        if new:
            st.dataframe(pd.DataFrame(new)[["first_seen", "category", "key", "name", "price", "url"]].sort_values("first_seen", ascending=False),
                         hide_index=True, width="stretch", column_config={
                    "price": st.column_config.NumberColumn("Price (₹)", format="₹%d"),
                    "url": st.column_config.LinkColumn("Link", display_text="open")})
        else:
            st.write("No new listings in this period.")

    if market:
        st.subheader("⚖️ Your picks vs the alternatives")
        sc = {k: v for k, v in mcfg.get("gpu_scores", {}).items() if not k.startswith("_")}
        for p in cfg["parts"]:
            m = p.get("match", {})
            if not m.get("compare"):
                continue
            keys = m.get("key_in", []) + m["compare"]
            best = cheapest_per_key(market, m["category"], keys)
            rows_ = [{"Model": k, "Cheapest (₹)": int(float(best[k]["price"])) if k in best else None,
                      "Listing": best[k]["name"] if k in best else "not in stock",
                      "Link": best[k]["url"] if k in best else None, "Yours": "⭐" if k in m.get("key_in", []) else "",
                      **({"Perf score": sc.get(k), "₹ per perf point": (int(float(best[k]["price"])) / sc[k]) if k in best and k in sc else None}
                         if m["category"] == "GPU" else {})} for k in keys]
            st.markdown(f"**{p['name']}**")
            st.dataframe(pd.DataFrame(rows_), hide_index=True, width="stretch", column_config={
                "Cheapest (₹)": st.column_config.NumberColumn(format="₹%d"),
                "₹ per perf point": st.column_config.NumberColumn(format="₹%d"),
                "Link": st.column_config.LinkColumn(display_text="open")})
