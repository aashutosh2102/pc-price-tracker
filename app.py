"""PC Price Tracker — minimalist visual dashboard.

Local:  streamlit run app.py
Cloud:  share.streamlit.io · Secrets: GITHUB_REPO, GITHUB_TOKEN (fine-grained, Contents: Read and write)
"""
import base64
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

import viz
from history_core import load_launch, read_history, timeline
from market_core import (best_alternatives, cheapest_per_key, load_local, load_local_history, load_market_cfg,
                         read_csv_text, recent_changes, run_scan_and_merge)
from tracker_core import fetch_part, forecast, load_config, read_rows, rows_to_csv, summarize, upsert

st.set_page_config(page_title="PC Price Tracker", page_icon="◆", layout="wide", initial_sidebar_state="collapsed")
st.markdown(viz.CSS, unsafe_allow_html=True)
ROOT = Path(__file__).parent
PC = viz.CFG


# ======================= storage (GitHub or local) =======================
def secret(k):
    try:
        return st.secrets.get(k)
    except Exception:
        return None


REPO, TOKEN = secret("GITHUB_REPO"), secret("GITHUB_TOKEN")
GH = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
if TOKEN:
    GH["Authorization"] = f"Bearer {TOKEN}"
FILES = ["data/prices.csv", "data/history.csv", "data/market_latest.csv", "data/market_seen.csv",
         "data/market_history.csv", "data/market_meta.json"]


def gh_get(path):
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/{path}",
                     headers={**GH, "Accept": "application/vnd.github.raw+json"}, timeout=25)
    return r.text if r.ok else None


def gh_put(path, text, msg):
    url = f"https://api.github.com/repos/{REPO}/contents/{path}"
    cur = requests.get(url, headers=GH, timeout=20)
    body = {"message": msg, "content": base64.b64encode(text.encode()).decode()}
    if cur.ok:
        body["sha"] = cur.json().get("sha")
    r = requests.put(url, headers=GH, json=body, timeout=30)
    if r.ok:
        return True, ""
    hint = {401: "token invalid/expired", 403: "token needs Contents: Read and write", 404: "check repo name/access"}
    return False, f"{path}: HTTP {r.status_code} ({hint.get(r.status_code, '')})"


def persist(files, msg):
    if REPO and TOKEN:
        errs = [e for ok, e in (gh_put(p, t, msg) for p, t in files.items()) if not ok]
        return (False, "GitHub save failed — " + "; ".join(errs)) if errs else (True, "Saved to GitHub")
    for p, t in files.items():
        (ROOT / p).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / p).write_text(t, encoding="utf-8")
    return True, "Saved locally"


@st.cache_data(ttl=300, show_spinner=False)
def load_all():
    raw = {}
    if REPO:
        raw = {f: gh_get(f) for f in FILES}
    if not REPO or raw.get("data/prices.csv") is None:
        raw = {f: (ROOT / f).read_text(encoding="utf-8") if (ROOT / f).exists() else "" for f in FILES}
        src = "local files"
    else:
        src = "GitHub"
    return {k: v or "" for k, v in raw.items()}, src


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_build(_cfg, day):
    res, logs = {}, []
    with requests.Session() as s:
        for p in _cfg["parts"]:
            price, src, log = fetch_part(p, s, pause=0.5)
            logs += log
            if price:
                res[p["name"]] = (price, src)
    return res, logs


# ======================= load data =======================
cfg, mcfg, launch = load_config(), load_market_cfg(), load_launch()
names = [p["name"] for p in cfg["parts"]]
raw, where = load_all()
raw.update(st.session_state.get("raw_override", {}))
rows = read_rows(raw["data/prices.csv"])
hist = read_history(raw["data/history.csv"])
market = read_csv_text(raw["data/market_latest.csv"])
seen = read_csv_text(raw["data/market_seen.csv"])
mhist = read_csv_text(raw["data/market_history.csv"])
meta = json.loads(raw["data/market_meta.json"]) if raw["data/market_meta.json"].strip() else {}

# ======================= sidebar (tucked away) =======================
with st.sidebar:
    st.markdown("### Controls")
    auto = st.toggle("Auto-fetch build prices", value=True, help="On page load, at most every 6 hours.")
    auto_mkt = st.toggle("Auto-scan market daily", value=True, help="~1,300 products, 30–60 s.")
    c1, c2 = st.columns(2)
    if c1.button("Fetch build", width="stretch"):
        fetch_build.clear()
        st.session_state.pop("auto_done", None)
    if c2.button("Scan market", width="stretch"):
        st.session_state["force_market"] = True
    cfg["half_life_days"] = st.slider("Forecast memory (half-life, days)", 10, 120, cfg.get("half_life_days", 45))
    st.divider()
    st.markdown("### Add a quote")
    with st.form("add", clear_on_submit=True, border=False):
        part = st.selectbox("Part", names)
        price = st.number_input("Price (₹)", min_value=100, step=100, value=None, placeholder="74990")
        day = st.date_input("Date", value=date.today(), max_value=date.today())
        src = st.text_input("Where", placeholder="Kryptronix, Nehru Place")
        if st.form_submit_button("Save", width="stretch", type="primary") and price:
            rows = upsert(rows, part, price, src or "manual quote", day)
            ok, msg = persist({"data/prices.csv": rows_to_csv(rows)}, f"Quote: {part} ₹{int(price):,}")
            st.session_state.setdefault("raw_override", {})["data/prices.csv"] = rows_to_csv(rows)
            (st.success if ok else st.error)(msg)
            load_all.clear()
    st.divider()
    st.caption(f"Data from **{where}** · {len(rows)} build prices · {len(hist)} history points · "
               f"{len(market):,} market listings · last scan {meta.get('last_scan', 'never')}")

# ======================= automatic updates =======================
if auto and "auto_done" not in st.session_state:
    with st.spinner("Fetching today's prices…"):
        res, logs = fetch_build(cfg, date.today().isoformat())
    st.session_state.update(auto_done=True, fetch_log=logs)
    new = {k: v for k, v in res.items()
           if not any(r["part"] == k and r["date"] == date.today() and r["price"] == v[0] for r in rows)}
    if new:
        for k, (p, s) in new.items():
            rows = upsert(rows, k, p, s)
        txt = rows_to_csv(rows)
        st.session_state.setdefault("raw_override", {})["data/prices.csv"] = txt
        st.session_state["save_msg"] = persist({"data/prices.csv": txt}, f"Auto price update {date.today()}")
        load_all.clear()

stale = not meta.get("last_scan") or date.fromisoformat(meta["last_scan"]) < date.today()
if st.session_state.pop("force_market", False) or (auto_mkt and stale and "market_tried" not in st.session_state):
    st.session_state["market_tried"] = True
    cats = [c["name"] for c in mcfg["categories"]]
    bar = st.progress(0.0, text="Scanning the market…")

    def prog(cat, page, pages):
        i = cats.index(cat) if cat in cats else 0
        bar.progress(min(1.0, (i + page / max(pages, 1)) / len(cats)), text=f"Scanning {cat} · page {page}/{pages}")

    lt, sn, meta2, ch, log, ht = run_scan_and_merge(raw["data/market_history.csv"], raw["data/market_seen.csv"], meta, prog)
    bar.empty()
    st.session_state["market_log"] = log
    if lt:
        files = {"data/market_latest.csv": lt, "data/market_seen.csv": sn, "data/market_history.csv": ht,
                 "data/market_meta.json": json.dumps(meta2, indent=2)}
        st.session_state.setdefault("raw_override", {}).update(files)
        st.session_state["save_msg"] = persist(files, f"Market scan {date.today()}")
        market, seen, mhist, meta = read_csv_text(lt), read_csv_text(sn), read_csv_text(ht), meta2
        load_all.clear()
    else:
        st.session_state["save_msg"] = (False, "Market scan got no products — the stores may be blocking this server. "
                                               "Your Windows task / GitHub Action can fill it in.")

# ======================= derived data =======================
summary = summarize(rows, cfg)
fc = {s["part"]["name"]: s["f"] for s in summary}
part_by_name = {p["name"]: p for p in cfg["parts"]}


def part_points(p):
    pts = timeline(p.get("history_item"), p["name"], rows, hist, mhist)
    return sorted({(x["date"], x["price"]) for x in pts})


mdf = pd.DataFrame(market)
if not mdf.empty:
    mdf["price"] = pd.to_numeric(mdf["price"], errors="coerce")
    mdf["in_stock"] = mdf["in_stock"].astype(str).str.lower() != "false"
    mdf = mdf[mdf["in_stock"]]
gpu_scores = {k: v for k, v in mcfg.get("gpu_scores", {}).items() if not k.startswith("_")}
gpu_scores.update({k: v["perf"] for k, v in launch.items() if isinstance(v, dict) and v.get("perf")})

# ======================= hero =======================
have = [s for s in summary if s["f"]]
tl = sum(s["f"]["latest"] for s in have)
tt = sum(s["part"]["target"] for s in have)
t30, t90, t1y = (sum(s["f"][k] for s in have) for k in ("f30", "f90", "f1y"))
buy_now = sum(1 for s in have if s["f"]["signal"].startswith("BUY"))
chips = (f'<span class="chip">● {where}</span><span class="chip">{len(market):,} listings</span>'
         f'<span class="chip">updated {max((r["date"] for r in rows), default=date.today()):%d %b}</span>')
st.markdown(f'<div class="hero"><div><h1>PC Price Tracker</h1><p>Ryzen 7 9700X · RTX 5070 · 32 GB DDR5 — '
            f'and the whole Indian PC-parts market around it</p></div><div>{chips}</div></div>', unsafe_allow_html=True)
if "save_msg" in st.session_state:
    ok, msg = st.session_state["save_msg"]
    st.toast(msg, icon="✅" if ok else "⚠️")

k = st.columns(4)
gap = tl - tt
k[0].markdown(viz.kpi("Build today", viz.inr(tl), f"{buy_now}/{len(have)} parts at target", viz.GOOD if buy_now else viz.MUTED), unsafe_allow_html=True)
k[1].markdown(viz.kpi("Gap to target", viz.inr(abs(gap)), "above target" if gap > 0 else "below target ✓",
                      viz.BAD if gap > 0 else viz.GOOD), unsafe_allow_html=True)
k[2].markdown(viz.kpi("In 90 days", viz.inr(t90), f"{t90 - tl:+,.0f} vs today", viz.BAD if t90 > tl else viz.GOOD), unsafe_allow_html=True)
k[3].markdown(viz.kpi("In 1 year", viz.inr(t1y), f"{t1y - tl:+,.0f} vs today", viz.BAD if t1y > tl else viz.GOOD), unsafe_allow_html=True)

t_over, t_time, t_mkt, t_pulse, t_data = st.tabs(["Overview", "Timeline", "Market", "Pulse", "Data"])

# ======================= OVERVIEW =======================
with t_over:
    st.markdown(viz.section("Signal board", "Each part: today's price, the signal, and its full price journey "
                                            "(dotted green = your target)."), unsafe_allow_html=True)
    for i in range(0, len(cfg["parts"]), 4):
        cols = st.columns(4)
        for col, p in zip(cols, cfg["parts"][i:i + 4]):
            f = fc.get(p["name"])
            with col:
                if not f:
                    st.markdown(f'<div class="card"><div class="t">{p["name"]}</div><div class="m">{p["model"]}</div>'
                                f'<div class="p">–</div></div>', unsafe_allow_html=True)
                    continue
                vs = (f["latest"] / p["target"] - 1) * 100
                st.markdown(f'<div class="card"><div class="t">{p["name"]}</div><div class="m">{p["model"]}</div>'
                            f'<div class="p">{viz.inr(f["latest"])} <span style="font-size:.75rem;color:'
                            f'{viz.BAD if vs > 0 else viz.GOOD}">{'on target' if abs(vs) < 0.5 else f'{vs:+.0f}% vs target'}</span></div>{viz.pill(f["signal"])}</div>',
                            unsafe_allow_html=True)
                st.plotly_chart(viz.sparkline(part_points(p), p["target"]), width="stretch", config=PC, key=f"spark_{p['name']}")

    if have:
        a, b = st.columns([3, 2])
        with a:
            deltas = [(s["part"]["name"], s["f"]["latest"] - s["part"]["target"]) for s in have]
            st.plotly_chart(viz.waterfall(deltas, tt, tl), width="stretch", config=PC)
        with b:
            st.plotly_chart(viz.donut([s["part"]["name"] for s in have], [s["f"]["latest"] for s in have]),
                            width="stretch", config=PC)
        a, b = st.columns(2)
        with a:
            bullets = []
            for s in have:
                pts = part_points(s["part"]) or [(s["f"]["last_date"], s["f"]["latest"])]
                ps = [x[1] for x in pts]
                bullets.append({"part": s["part"]["name"], "low": min(ps), "high": max(ps), "latest": s["f"]["latest"],
                                "target": s["part"]["target"], "f90": s["f"]["f90"]})
            st.plotly_chart(viz.target_bullets(bullets), width="stretch", config=PC)
        with b:
            st.plotly_chart(viz.forecast_fan(tl, t30, t90, t1y), width="stretch", config=PC)

        if not mdf.empty:
            st.markdown(viz.section("Cheaper equivalents right now",
                                    "Lowest in-stock listing in the market scan that matches each part's rules."), unsafe_allow_html=True)
            eq = []
            for s in have:
                alt = best_alternatives(market, s["part"].get("match", {}), 1)
                if alt:
                    ap = int(float(alt[0]["price"]))
                    eq.append({"Part": s["part"]["name"], "Yours": s["f"]["latest"], "Cheapest match": ap,
                               "Save": s["f"]["latest"] - ap, "Listing": alt[0]["name"], "Link": alt[0]["url"]})
            if eq:
                st.dataframe(pd.DataFrame(eq), hide_index=True, width="stretch", column_config={
                    "Yours": st.column_config.NumberColumn("Yours (₹)", format="localized"),
                    "Cheapest match": st.column_config.NumberColumn("Cheapest match (₹)", format="localized"),
                    "Save": st.column_config.NumberColumn("You'd save (₹)", format="localized",
                                                          help="Positive = the market has it cheaper; negative = yours is cheaper"),
                    "Link": st.column_config.LinkColumn(display_text="open")})

# ======================= TIMELINE =======================
with t_time:
    st.markdown(viz.section("Price journey", "Everything known about a product — from launch to today, plus where it's "
                                             "heading. Combines your tracker, long-run history and daily market scans."),
                unsafe_allow_html=True)
    opts = {f"{p['name']} · {p['model']}": ("part", p["name"]) for p in cfg["parts"]}
    for it in sorted({r["item"] for r in hist} | set(launch) - {"_source"}):
        if not any(p.get("history_item") == it for p in cfg["parts"]):
            opts[it] = ("item", it)
    if mhist:
        for kk in sorted({r["key"] for r in mhist if r.get("key")}):
            opts.setdefault(f"{kk} (market)", ("item", kk))
    choice = st.selectbox("Product", list(opts), index=list(opts).index(next(o for o in opts if o.startswith("GPU"))))
    kind, ident = opts[choice]
    p = part_by_name.get(ident) if kind == "part" else None
    item = p["history_item"] if p else ident
    pts = timeline(item, p["name"] if p else None, rows, hist, mhist)
    linfo = launch.get(item) if isinstance(launch.get(item), dict) else None
    f = fc.get(p["name"]) if p else None
    if not pts:
        st.info("No price points yet for this product.")
    else:
        prices = [x["price"] for x in pts]
        first = pts[0]
        recent = [x for x in pts if (pts[-1]["date"] - x["date"]).days <= 7]
        last = min(recent, key=lambda x: x["price"])
        peak = max(prices)
        s = st.columns(6)
        S = lambda col, l, v, sub='': col.markdown(viz.stat(l, v, sub), unsafe_allow_html=True)
        S(s[0], "Best price now", viz.inr(last["price"]), f'lowest in last 7 days · {last["date"]:%d %b}')
        S(s[1], "All-time low", viz.inr(min(prices)), f'{next(x["date"] for x in pts if x["price"] == min(prices)):%d %b %Y}')
        S(s[2], "From peak", f"{(last['price'] / peak - 1) * 100:+.0f}%", viz.inr(peak))
        if linfo:
            ld = date.fromisoformat(linfo["launch"])
            S(s[3], "Launched", f"{ld:%b %Y}", f"{(date.today() - ld).days} days ago")
            S(s[4], "vs launch MSRP", f"{(last['price'] / linfo['msrp_inr'] - 1) * 100:+.0f}%",
                        viz.inr(linfo["msrp_inr"]))
        else:
            S(s[3], "Tracked since", f"{first['date']:%b %Y}", f"{(last['date'] - first['date']).days} days")
            S(s[4], "Data points", len(pts), f"{len({x['source'] for x in pts})} sources")
        S(s[5], "Signal", f["signal"].split(" - ")[0] if f else "–", f["when"] if f else "")
        st.plotly_chart(viz.journey(pts, item, linfo, p["target"] if p else None, f), width="stretch", config=PC)
        cdl = viz.monthly_candles(pts)
        a, b = st.columns([3, 2])
        with a:
            if cdl:
                st.plotly_chart(cdl, width="stretch", config=PC)
            else:
                st.caption("Month-by-month candles appear once there are prices in at least 2 different months.")
        with b:
            src = pd.DataFrame(pts).groupby("source").size().sort_values()
            import plotly.graph_objects as go
            fig = go.Figure(go.Bar(x=src.values, y=[s_[:38] for s_ in src.index], orientation="h",
                                   marker=dict(color=viz.ACCENT), hovertemplate="%{y}: %{x} points<extra></extra>"))
            fig.update_layout(height=300, title="Where the data comes from")
            st.plotly_chart(fig, width="stretch", config=PC)

    st.markdown(viz.section("Compare journeys", "Overlay several products. Indexed view starts every line at 100, "
                                                "so you can compare how much each moved."), unsafe_allow_html=True)
    c1, c2 = st.columns([4, 1])
    defaults = [o for o in opts if o.startswith(("GPU", "RAM", "SSD"))][:3]
    picks = c1.multiselect("Products", list(opts), default=defaults)
    mode = c2.radio("Scale", ["Indexed", "Absolute"], horizontal=False)
    series = {}
    for o in picks:
        kd, idn = opts[o]
        pp = part_by_name.get(idn) if kd == "part" else None
        it = pp["history_item"] if pp else idn
        series[o.split(" · ")[0]] = sorted({(x["date"], x["price"]) for x in timeline(it, pp["name"] if pp else None, rows, hist, mhist)})
    if series:
        st.plotly_chart(viz.compare_lines(series, mode), width="stretch", config=PC)

    gl = [k_ for k_, v in launch.items() if isinstance(v, dict)]
    if gl:
        st.markdown(viz.section("Since launch", launch.get("_source", "")), unsafe_allow_html=True)
        drows = []
        for g in gl:
            tp = timeline(g, "GPU" if part_by_name.get("GPU", {}).get("history_item") == g else None, rows, hist, mhist)
            drows.append({"name": g, "msrp": launch[g].get("msrp_inr"), "low": launch[g].get("low_12m"),
                          "median": launch[g].get("median_12m"), "today": min((x["price"] for x in tp if x["date"] == tp[-1]["date"]), default=None) if tp else None})
        st.plotly_chart(viz.launch_dumbbell(drows), width="stretch", config=PC)

# ======================= MARKET =======================
with t_mkt:
    if mdf.empty:
        st.markdown(viz.section("No market scan yet", "Open the sidebar (›) and press **Scan market**, or let your "
                                                      "Windows task / GitHub Action run update_market.py."), unsafe_allow_html=True)
    else:
        st.plotly_chart(viz.market_map(mdf), width="stretch", config=PC)
        cats = [c["name"] for c in mcfg["categories"] if c["name"] in set(mdf["category"])]
        cat = st.segmented_control("Category", cats, default="GPU" if "GPU" in cats else cats[0], label_visibility="collapsed")
        cat = cat or cats[0]
        d = mdf[mdf["category"] == cat]
        m = st.columns(4)
        m[0].metric("Listings", f"{len(d):,}")
        m[1].metric("Models", d["key"].nunique())
        m[2].metric("Cheapest", viz.inr(d["price"].min()))
        m[3].metric("Median", viz.inr(d["price"].median()))
        f1, f2 = st.columns([3, 2])
        q = f1.text_input("Filter", placeholder="Search e.g. 5070, CL30, Lancool", label_visibility="collapsed")
        brands = f2.multiselect("Brands", sorted(d["brand"].dropna().unique()), placeholder="All brands",
                                label_visibility="collapsed")
        if q:
            d = d[d["name"].str.contains(q, case=False, regex=False) | d["key"].astype(str).str.contains(q, case=False, regex=False)]
        if brands:
            d = d[d["brand"].isin(brands)]
        if d.empty:
            st.info("Nothing matches.")
        else:
            a, b = st.columns([3, 2])
            with a:
                fig, note = viz.value_chart(cat, d, gpu_scores)
                if fig:
                    fig.update_layout(height=420)
                    st.plotly_chart(fig, width="stretch", config=PC)
                if note:
                    st.caption(note)
            with b:
                st.plotly_chart(viz.brand_share(d), width="stretch", config=PC)
            a, b = st.columns([3, 2])
            with a:
                st.plotly_chart(viz.price_spread(d), width="stretch", config=PC)
            with b:
                st.plotly_chart(viz.price_histogram(d), width="stretch", config=PC)
            if mhist:
                keys = d.groupby("key").size().sort_values(ascending=False).index.tolist()
                mk = st.selectbox("Model history", keys)
                dm = viz.daily_min(mhist, key=mk)
                if not dm.empty and mk in dm:
                    import plotly.graph_objects as go
                    fig = go.Figure(go.Scatter(x=dm.index, y=dm[mk], mode="lines+markers", line=dict(shape="hv", color=viz.ACCENT, width=2),
                                               fill="tozeroy", fillcolor=viz.rgba(viz.ACCENT, 0.08), hovertemplate="%{x|%d %b}<br>₹%{y:,.0f}<extra></extra>"))
                    lo_ = dm[mk].min()
                    fig.update_layout(height=300, title=f"{mk} — cheapest listing per day", xaxis=dict(tickformat="%d %b"), yaxis=dict(tickprefix="₹", tickformat=",.0f",
                                                                                                  range=[lo_ * 0.9, dm[mk].max() * 1.05]))
                    st.plotly_chart(fig, width="stretch", config=PC)
            with st.expander(f"All {len(d):,} listings"):
                st.dataframe(d.sort_values("price")[["name", "key", "brand", "price", "store", "url"]], hide_index=True,
                             width="stretch", column_config={"price": st.column_config.NumberColumn("Price (₹)", format="localized"),
                                                             "url": st.column_config.LinkColumn("Link", display_text="open")})

# ======================= PULSE =======================
with t_pulse:
    if not seen:
        st.markdown(viz.section("Waiting for scans", "The first market scan sets the baseline. From the next one on, new "
                                                     "launches, new listings and price drops appear here."), unsafe_allow_html=True)
    else:
        days = st.select_slider("Window", [1, 3, 7, 14, 30, 60, 90], value=7, format_func=lambda v: f"last {v} days")
        new, drops, new_models = recent_changes(seen, meta, days)
        m = st.columns(3)
        m[0].markdown(viz.kpi("New models / chips", len(new_models), "first time seen in the market", viz.ACCENT), unsafe_allow_html=True)
        m[1].markdown(viz.kpi("New listings", len(new), "new products from any brand", viz.INFO), unsafe_allow_html=True)
        m[2].markdown(viz.kpi("Price drops ≥5%", len(drops), "since the previous scan", viz.GOOD), unsafe_allow_html=True)
        if new_models:
            st.markdown(viz.section("🚀 New models", "A chip or model that never appeared before — e.g. a new GPU launch."),
                        unsafe_allow_html=True)
            nm = pd.DataFrame(new_models)
            nm["from"] = [int(float(cheapest_per_key(market, r.category, [r.key]).get(r.key, {}).get("price", 0) or 0)) for r in nm.itertuples()]
            st.dataframe(nm.sort_values("first_seen", ascending=False), hide_index=True, width="stretch",
                         column_config={"from": st.column_config.NumberColumn("From (₹)", format="localized")})
        if new:
            st.plotly_chart(viz.launch_radar(pd.DataFrame(new)), width="stretch", config=PC)
        if drops:
            dd = pd.DataFrame(drops)
            dd["price"] = pd.to_numeric(dd["price"])
            dd["drop %"] = dd["drop_pct"] * 100
            st.plotly_chart(viz.drops_chart(dd), width="stretch", config=PC)
        idx, heat = viz.category_index(mhist)
        if idx:
            st.markdown(viz.section("Market temperature", "Median movement of every model's cheapest listing, per category."),
                        unsafe_allow_html=True)
            st.plotly_chart(idx, width="stretch", config=PC)
            st.plotly_chart(heat, width="stretch", config=PC)
        else:
            st.caption("Market temperature charts appear after two or more daily scans.")
    if market:
        st.markdown(viz.section("Your picks vs the field", "Cheapest in-stock listing per model. ★ = your choice."),
                    unsafe_allow_html=True)
        cols = st.columns(2)
        j = 0
        for p in cfg["parts"]:
            mm = p.get("match", {})
            if not mm.get("compare"):
                continue
            keys = mm.get("key_in", []) + mm["compare"]
            best = cheapest_per_key(market, mm["category"], keys)
            rr = [{"model": k_, "price": int(float(best[k_]["price"])) if k_ in best else None, "yours": k_ in mm.get("key_in", [])}
                  for k_ in keys]
            if any(r["price"] for r in rr):
                cols[j % 2].plotly_chart(viz.picks_dotplot(rr, p["name"]), width="stretch", config=PC, key=f"pick_{p['name']}")
                j += 1

# ======================= DATA =======================
with t_data:
    st.markdown(viz.section("Raw data & downloads"), unsafe_allow_html=True)
    if st.session_state.get("fetch_log"):
        lg = pd.DataFrame(st.session_state["fetch_log"])
        st.markdown(f"**Today's build fetch** — {lg[lg['price'].notna()]['part'].nunique()}/{len(names)} parts updated")
        st.dataframe(lg, hide_index=True, width="stretch")
    if st.session_state.get("market_log"):
        st.markdown("**Last market scan**")
        st.dataframe(pd.DataFrame(st.session_state["market_log"]), hide_index=True, width="stretch")
    with st.expander("Targets & market outlook (this session)"):
        ed = st.data_editor(pd.DataFrame([{"Part": p["name"], "Target": p["target"], "Outlook % / 90d": p["outlook_90d"] * 100,
                                           "Basis": p["outlook_basis"]} for p in cfg["parts"]]),
                            disabled=["Part", "Basis"], hide_index=True, width="stretch")
        if st.button("Apply"):
            for p, (_, r) in zip(cfg["parts"], ed.iterrows()):
                p["target"], p["outlook_90d"] = int(r["Target"]), float(r["Outlook % / 90d"]) / 100
            st.caption("Applied for this session. Permanent: edit parts.json in GitHub.")
    for label, key in (("Build prices", "data/prices.csv"), ("Long-run history", "data/history.csv"),
                       ("Market listings", "data/market_latest.csv"), ("Market price history", "data/market_history.csv")):
        if raw.get(key):
            st.download_button(f"Download {label} (CSV)", raw[key], key.split("/")[-1], "text/csv")
    st.caption("Forecasts blend each part's recent trend with industry outlook (TrendForce for RAM/SSD). "
               "A guide, not a guarantee.")
