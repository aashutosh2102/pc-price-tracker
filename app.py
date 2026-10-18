"""PC Build Price Tracker - Streamlit dashboard.

Local:  streamlit run app.py
Cloud:  share.streamlit.io. Secrets (App settings > Secrets):
        GITHUB_REPO = "aashutosh2102/pc-price-tracker"
        GITHUB_TOKEN = "github_pat_..."   (fine-grained, this repo only, Contents: Read and write)
"""
import base64
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from tracker_core import (fetch_part, load_config, read_rows, rows_to_csv,
                          save_rows, summarize, upsert)

st.set_page_config(page_title="PC Price Tracker", page_icon="🖥️", layout="wide")


def secret(key):
    try:
        return st.secrets.get(key)
    except Exception:
        return None


REPO, TOKEN = secret("GITHUB_REPO"), secret("GITHUB_TOKEN")
API = f"https://api.github.com/repos/{REPO}/contents/data/prices.csv" if REPO else None
GH = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
if TOKEN:
    GH["Authorization"] = f"Bearer {TOKEN}"


# ---------- storage ----------
@st.cache_data(ttl=300, show_spinner=False)
def load_rows_cached():
    if API:
        r = requests.get(API, headers={**GH, "Accept": "application/vnd.github.raw+json"}, timeout=20)
        if r.ok:
            return read_rows(r.text), "GitHub repo"
    return read_rows(), "local file"


def persist(rows, message):
    """Returns (ok: bool, message)."""
    if API and TOKEN:
        cur = requests.get(API, headers=GH, timeout=20)
        body = {"message": message, "content": base64.b64encode(rows_to_csv(rows).encode()).decode()}
        if cur.ok:
            body["sha"] = cur.json().get("sha")
        r = requests.put(API, headers=GH, json=body, timeout=20)
        if r.ok:
            return True, "Saved to GitHub ✅"
        detail = r.json().get("message", "") if r.headers.get("content-type", "").startswith("application/json") else ""
        hint = {401: "Token is invalid or expired - create a new one.",
                403: "Token can't write to this repo. Give it 'Contents: Read and write' for this repo (see 'Check GitHub connection').",
                404: "Repo not found - check GITHUB_REPO spelling and that the token can access it."}.get(r.status_code, "")
        return False, f"GitHub save failed ({r.status_code}: {detail}). {hint}"
    try:
        save_rows(rows)
        return True, "Saved locally (add GITHUB_TOKEN in Secrets to keep data on Streamlit Cloud)"
    except OSError as e:
        return False, f"Could not save: {e}"


def show(ok, msg):
    (st.success if ok else st.error)(msg)


def github_check():
    if not REPO:
        return [("❌", "GITHUB_REPO secret is missing")]
    out = []
    if not TOKEN:
        out.append(("❌", "GITHUB_TOKEN secret is missing"))
        return out
    r = requests.get(f"https://api.github.com/repos/{REPO}", headers=GH, timeout=20)
    if r.status_code == 401:
        return [("❌", "Token invalid or expired")]
    if r.status_code == 404:
        return [("❌", f"Repo '{REPO}' not found or token has no access to it")]
    perms = r.json().get("permissions", {})
    out.append(("✅", f"Repo found: {REPO}"))
    out.append(("✅" if perms.get("push") else "❌",
                "Write access" if perms.get("push") else "No write access - set Contents: Read and write"))
    f = requests.get(API, headers=GH, timeout=20)
    out.append(("✅" if f.ok else "⚠️", "data/prices.csv found" if f.ok else f"data/prices.csv: HTTP {f.status_code}"))
    return out


# ---------- fetching ----------
@st.cache_data(ttl=6 * 3600, show_spinner=False)
def fetch_all(_cfg, day):  # cached ~6h per day, so refreshing the page doesn't hammer sites
    results, logs = {}, []
    with requests.Session() as s:
        for p in _cfg["parts"]:
            price, src, log = fetch_part(p, s, pause=0.5)
            logs += log
            if price:
                results[p["name"]] = (price, src)
    return results, logs


def apply_fetch(rows, results):
    for name, (price, src) in results.items():
        rows = upsert(rows, name, price, src)
    return rows


cfg = load_config()
names = [p["name"] for p in cfg["parts"]]
rows, where = load_rows_cached()
if "rows" in st.session_state:
    rows = st.session_state["rows"]

# ---------- sidebar ----------
with st.sidebar:
    st.header("⚙️ Controls")
    auto = st.toggle("Auto-fetch prices on page load", value=True,
                     help="Fetches today's prices once (cached for 6 hours) when you open or refresh the app.")
    cfg["half_life_days"] = st.slider("Recency half-life (days)", 10, 120, cfg.get("half_life_days", 45))

    if st.button("🔄 Fetch live prices now", width="stretch"):
        fetch_all.clear()
        st.session_state.pop("auto_done", None)

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
            show(*persist(rows, f"Quote: {part} ₹{int(price):,}"))
            load_rows_cached.clear()

    st.divider()
    with st.expander("🔧 Check GitHub connection"):
        if st.button("Run check", width="stretch"):
            for icon, msg in github_check():
                st.write(f"{icon} {msg}")
    st.caption(f"Data: **{where}** · {len(rows)} prices recorded")

# ---------- auto / manual fetch ----------
if auto and "auto_done" not in st.session_state:
    with st.spinner("Fetching today's prices from MDComputers, pricehistory.app, gpuprix…"):
        results, logs = fetch_all(cfg, date.today().isoformat())
    st.session_state["auto_done"] = True
    st.session_state["fetch_log"] = logs
    changed = {k: v for k, v in results.items()
               if not any(r["part"] == k and r["date"] == date.today() and r["price"] == v[0] for r in rows)}
    if changed:
        rows = apply_fetch(rows, changed)
        st.session_state["rows"] = rows
        st.session_state["save_msg"] = persist(rows, f"Auto price update {date.today()}")
        load_rows_cached.clear()

# ---------- header ----------
st.title("🖥️ PC Build Price Tracker")
st.caption("Ryzen 7 9700X + RTX 5070 · lowest in-stock price across several Indian sites · "
           "forecast blends your history with industry outlook (a guide, not a guarantee)")
if "save_msg" in st.session_state:
    show(*st.session_state["save_msg"])

if st.session_state.get("fetch_log"):
    lg = pd.DataFrame(st.session_state["fetch_log"])
    ok_parts = lg[lg["price"].notna()]["part"].nunique()
    with st.expander(f"📡 Today's fetch: {ok_parts}/{len(names)} parts updated automatically — details"):
        lg["price"] = lg["price"].map(lambda v: f"₹{int(v):,}" if pd.notna(v) else "-")
        st.dataframe(lg, hide_index=True, width="stretch")

with st.expander("🎯 Targets & market outlook (edit for this session)"):
    ed = st.data_editor(
        pd.DataFrame([{"Part": p["name"], "Target (₹)": p["target"], "Outlook % / 90 days": p["outlook_90d"] * 100,
                       "Basis": p["outlook_basis"]} for p in cfg["parts"]]),
        disabled=["Part", "Basis"], hide_index=True, width="stretch")
    for p, (_, r) in zip(cfg["parts"], ed.iterrows()):
        p["target"], p["outlook_90d"] = int(r["Target (₹)"]), float(r["Outlook % / 90 days"]) / 100
    st.caption("To change defaults permanently, edit parts.json in GitHub.")

summary = summarize(rows, cfg)
have = [s for s in summary if s["f"]]
tl, tt = sum(s["f"]["latest"] for s in have), sum(s["part"]["target"] for s in have)
t90, t1y = sum(s["f"]["f90"] for s in have), sum(s["f"]["f1y"] for s in have)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Build cost today", f"₹{tl:,}", f"₹{tl - tt:,} vs target", delta_color="inverse")
c2.metric("Your target", f"₹{tt:,}")
c3.metric("Forecast in 90 days", f"₹{t90:,}", f"{t90 - tl:+,}", delta_color="inverse")
c4.metric("Forecast in 1 year", f"₹{t1y:,}", f"{t1y - tl:+,}", delta_color="inverse")

ICON = {"BUY": "🟢", "Rising": "🟠", "Falling -": "🔵", "Falling slowly": "⚪", "Flat": "⚪"}
table = []
for s in summary:
    p, f = s["part"], s["f"]
    if not f:
        table.append({"Signal": "⚪ No data", "Part": p["name"], "Model": p["model"]})
        continue
    last_src = next((r["source"] for r in sorted(rows, key=lambda r: r["date"], reverse=True)
                     if r["part"] == p["name"]), "")
    table.append({
        "Signal": f"{next((v for k, v in ICON.items() if f['signal'].startswith(k)), '⚪')} {f['signal']}",
        "Part": p["name"], "Model": p["model"], "Latest (₹)": f["latest"], "Target (₹)": p["target"],
        "Updated": f["last_date"], "From": last_src, "Lowest (₹)": f["low"], "90-day change": f["change_90d"] * 100,
        "In 90 days (₹)": f["f90"], "In 1 year (₹)": f["f1y"], "Target likely": f["when"],
        "Prices": f["n"], "Trust in your data": f["trust"] * 100})
money = st.column_config.NumberColumn(format="₹%d")
st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch", column_config={
    "Latest (₹)": money, "Target (₹)": money, "Lowest (₹)": money, "In 90 days (₹)": money, "In 1 year (₹)": money,
    "90-day change": st.column_config.NumberColumn(format="%+.1f%%"),
    "Trust in your data": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
    "Updated": st.column_config.DateColumn(format="DD MMM YYYY")})

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
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), yaxis_tickprefix="₹",
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width="stretch")
    st.caption(f"Market outlook basis: {p['outlook_basis']}")

with st.expander("🗂️ All recorded prices"):
    st.dataframe(pd.DataFrame(sorted(rows, key=lambda r: r["date"], reverse=True)), hide_index=True, width="stretch")
    st.download_button("Download CSV", rows_to_csv(rows), "prices.csv", "text/csv")
