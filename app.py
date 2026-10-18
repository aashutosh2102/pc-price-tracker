"""PC Build Price Tracker - Streamlit dashboard.

Local:  streamlit run app.py
Cloud:  deploy on share.streamlit.io (see README). Optional secrets:
        GITHUB_REPO = "your-username/pc-price-tracker"
        GITHUB_TOKEN = "github_pat_..."   (fine-grained, Contents: Read and write)
"""
import base64
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from tracker_core import (fetch_price, load_config, read_rows, rows_to_csv,
                          save_rows, summarize, upsert)

st.set_page_config(page_title="PC Price Tracker", page_icon="🖥️", layout="wide")


def secret(key):
    try:
        return st.secrets.get(key)
    except Exception:
        return None


REPO, TOKEN = secret("GITHUB_REPO"), secret("GITHUB_TOKEN")
API = f"https://api.github.com/repos/{REPO}/contents/data/prices.csv" if REPO else None


# ---------- storage: GitHub repo if configured, else local file ----------
@st.cache_data(ttl=300, show_spinner=False)
def load_rows_cached():
    if API:
        h = {"Accept": "application/vnd.github.raw+json"}
        if TOKEN:
            h["Authorization"] = f"Bearer {TOKEN}"
        r = requests.get(API, headers=h, timeout=20)
        if r.ok:
            return read_rows(r.text), "GitHub repo"
    return read_rows(), "local file"


def persist(rows, message):
    """Save rows to GitHub (if token) or local file. Returns a status string."""
    if API and TOKEN:
        h = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}
        cur = requests.get(API, headers=h, timeout=20)
        sha = cur.json().get("sha") if cur.ok else None
        body = {"message": message, "content": base64.b64encode(rows_to_csv(rows).encode()).decode()}
        if sha:
            body["sha"] = sha
        r = requests.put(API, headers=h, json=body, timeout=20)
        return "Saved to GitHub ✅" if r.ok else f"GitHub save failed ({r.status_code})"
    try:
        save_rows(rows)
        return "Saved to local file ✅ (on Streamlit Cloud this resets on restart - add GITHUB_TOKEN to keep it)"
    except OSError as e:
        return f"Could not save: {e}"


cfg = load_config()
names = [p["name"] for p in cfg["parts"]]
rows, where = load_rows_cached()
if "rows" in st.session_state:
    rows = st.session_state["rows"]

# ---------- sidebar ----------
with st.sidebar:
    st.header("⚙️ Controls")
    cfg["half_life_days"] = st.slider("Recency half-life (days)", 10, 120, cfg.get("half_life_days", 45),
                                      help="A price this many days old counts half as much as today's.")

    if st.button("🔄 Fetch live prices now", width="stretch"):
        log = []
        with st.spinner("Checking price sites..."):
            for p in cfg["parts"]:
                price, status = fetch_price(p)
                log.append({"Part": p["name"], "Price": f"₹{price:,}" if price else "-", "Status": status})
                if price:
                    rows = upsert(rows, p["name"], price, p["url"])
        st.dataframe(pd.DataFrame(log), hide_index=True, width="stretch")
        if any(x["Price"] != "-" for x in log):
            st.session_state["rows"] = rows
            st.success(persist(rows, f"Live price update {date.today()}"))
            load_rows_cached.clear()
        else:
            st.warning("No prices fetched. Sites may block this server - use 'Add a quote' below "
                       "or let your Windows PC / GitHub Action update the data.")

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
            st.success(persist(rows, f"Quote: {part} ₹{int(price):,}"))
            load_rows_cached.clear()

    st.divider()
    st.caption(f"Data source: **{where}** · {len(rows)} prices recorded")

# ---------- edit targets / outlook ----------
st.title("🖥️ PC Build Price Tracker")
st.caption("Ryzen 7 9700X + RTX 5070 build · Forecasts blend your price history with industry outlook. A guide, not a guarantee.")

with st.expander("🎯 Targets & market outlook (edit for this session)"):
    ed = st.data_editor(
        pd.DataFrame([{"Part": p["name"], "Target (₹)": p["target"], "Outlook % / 90 days": p["outlook_90d"] * 100,
                       "Basis": p["outlook_basis"]} for p in cfg["parts"]]),
        disabled=["Part", "Basis"], hide_index=True, width="stretch")
    for p, (_, r) in zip(cfg["parts"], ed.iterrows()):
        p["target"], p["outlook_90d"] = int(r["Target (₹)"]), float(r["Outlook % / 90 days"]) / 100
    st.caption("To change defaults permanently, edit parts.json in your GitHub repo.")

summary = summarize(rows, cfg)

# ---------- headline metrics ----------
have = [s for s in summary if s["f"]]
tot_latest = sum(s["f"]["latest"] for s in have)
tot_target = sum(s["part"]["target"] for s in have)
tot_90 = sum(s["f"]["f90"] for s in have)
tot_1y = sum(s["f"]["f1y"] for s in have)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Build cost today", f"₹{tot_latest:,}", f"₹{tot_latest - tot_target:,} vs target", delta_color="inverse")
c2.metric("Your target", f"₹{tot_target:,}")
c3.metric("Forecast in 90 days", f"₹{tot_90:,}", f"{tot_90 - tot_latest:+,}", delta_color="inverse")
c4.metric("Forecast in 1 year", f"₹{tot_1y:,}", f"{tot_1y - tot_latest:+,}", delta_color="inverse")

# ---------- table ----------
ICON = {"BUY": "🟢", "Rising": "🟠", "Falling -": "🔵", "Falling slowly": "⚪", "Flat": "⚪"}
table = []
for s in summary:
    p, f = s["part"], s["f"]
    if not f:
        table.append({"Signal": "⚪ No data", "Part": p["name"], "Model": p["model"]})
        continue
    icon = next((v for k, v in ICON.items() if f["signal"].startswith(k)), "⚪")
    table.append({
        "Signal": f"{icon} {f['signal']}", "Part": p["name"], "Model": p["model"],
        "Latest (₹)": f["latest"], "Target (₹)": p["target"], "Updated": f["last_date"],
        "Lowest (₹)": f["low"], "90-day change": f["change_90d"] * 100,
        "In 90 days (₹)": f["f90"], "In 1 year (₹)": f["f1y"], "Target likely": f["when"],
        "Prices": f["n"], "Trust in your data": f["trust"] * 100,
    })
st.dataframe(
    pd.DataFrame(table), hide_index=True, width="stretch",
    column_config={
        "Latest (₹)": st.column_config.NumberColumn(format="₹%d"),
        "Target (₹)": st.column_config.NumberColumn(format="₹%d"),
        "Lowest (₹)": st.column_config.NumberColumn(format="₹%d"),
        "In 90 days (₹)": st.column_config.NumberColumn(format="₹%d"),
        "In 1 year (₹)": st.column_config.NumberColumn(format="₹%d"),
        "90-day change": st.column_config.NumberColumn(format="%+.1f%%"),
        "Trust in your data": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f%%"),
        "Updated": st.column_config.DateColumn(format="DD MMM YYYY"),
    })

# ---------- charts ----------
st.subheader("📈 Price history & forecast")
sel = st.selectbox("Part", names, index=names.index("GPU") if "GPU" in names else 0)
s = next(x for x in summary if x["part"]["name"] == sel)
pts = sorted((r["date"], r["price"]) for r in rows if r["part"] == sel)
if pts:
    f, p = s["f"], s["part"]
    last = f["last_date"]
    fx = [last, last + timedelta(days=30), last + timedelta(days=90), last + timedelta(days=365)]
    fy = [f["latest"], f["f30"], f["f90"], f["f1y"]]
    fig = go.Figure()
    fig.add_scatter(x=[d for d, _ in pts], y=[v for _, v in pts], mode="lines+markers", name="Recorded")
    fig.add_scatter(x=fx, y=fy, mode="lines+markers", name="Forecast", line=dict(dash="dash"))
    fig.add_hline(y=p["target"], line_color="green", annotation_text=f"Target ₹{p['target']:,}")
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=30, b=10), yaxis_tickprefix="₹",
                      legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, width="stretch")
    st.caption(f"Market outlook basis: {p['outlook_basis']}")
else:
    st.info("No prices recorded for this part yet - add a quote in the sidebar.")

with st.expander("🗂️ All recorded prices"):
    st.dataframe(pd.DataFrame(sorted(rows, key=lambda r: r["date"], reverse=True)),
                 hide_index=True, width="stretch")
    st.download_button("Download CSV", rows_to_csv(rows), "prices.csv", "text/csv")
