"""🔎 Search any PC part: price history since launch + rating history.
Lives in pages/ so Streamlit shows it as a second page next to the main dashboard."""
import base64
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import search_core as sc  # noqa: E402

st.set_page_config(page_title="Search · PC Price Tracker", page_icon="◆", layout="wide")
try:  # reuse the main dashboard's theme if present
    import viz  # noqa: F401
    st.markdown(viz.CSS, unsafe_allow_html=True)
except Exception:
    pass

ACC, GOOD, BAD, WARN, MUTED, INFO = "#8B7CFF", "#34D399", "#FB7185", "#F59E0B", "#8A90A2", "#38BDF8"
SRC_COL = {"gpuprix": "#A3E635", "pricehistory": INFO, "pcpricetracker": WARN, "pcpaisa": "#F472B6", "tracked": ACC}
PC = {"displayModeBar": False}
st.markdown("""<style>
.sx-hero{display:flex;justify-content:space-between;align-items:flex-end;margin:.2rem 0 1rem}
.sx-hero h1{font-size:2rem;font-weight:700;margin:0;letter-spacing:-.02em;background:linear-gradient(90deg,#E6E8EE,#8B7CFF);
 -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.sx-sub{color:#8A90A2;font-size:.9rem;margin-top:.2rem}
.sx-card{background:linear-gradient(180deg,#141821,#10131A);border:1px solid #1F2430;border-radius:16px;padding:.85rem 1rem;height:100%}
.sx-l{color:#8A90A2;font-size:.72rem;text-transform:uppercase;letter-spacing:.06em}
.sx-v{color:#F2F3F7;font-size:1.45rem;font-weight:650;margin-top:.15rem;letter-spacing:-.02em}
.sx-d{color:#8A90A2;font-size:.78rem;margin-top:.1rem}
.sx-name{font-size:1.5rem;font-weight:650;color:#F2F3F7;letter-spacing:-.02em}
.sx-chip{display:inline-block;padding:.2rem .6rem;border-radius:999px;font-size:.72rem;border:1px solid #262C3A;color:#B5BAC7;
 background:#121620;margin-right:.35rem}
.sx-sec{color:#E6E8EE;font-size:1.02rem;font-weight:600;margin:1.4rem 0 .1rem}
.sx-note{color:#8A90A2;font-size:.83rem;margin-bottom:.4rem}
</style>""", unsafe_allow_html=True)


def inr(v):
    return "–" if v is None else f"₹{float(v):,.0f}"


def card(col, label, value, sub=""):
    col.markdown(f'<div class="sx-card"><div class="sx-l">{label}</div><div class="sx-v">{value}</div>'
                 f'<div class="sx-d">{sub}</div></div>', unsafe_allow_html=True)


def sec(t, n=""):
    st.markdown(f'<div class="sx-sec">{t}</div>' + (f'<div class="sx-note">{n}</div>' if n else ""), unsafe_allow_html=True)


def layout(fig, h, title=""):
    fig.update_layout(height=h, title=dict(text=title, x=0, font=dict(size=14, color="#E6E8EE")),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#C9CDD6", size=12),
                      margin=dict(l=8, r=8, t=44, b=8), hoverlabel=dict(bgcolor="#1A1F2B"),
                      legend=dict(orientation="h", yanchor="top", y=-0.15, x=0, font=dict(size=11)))
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.05)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.05)", zeroline=False)
    return fig


# ---------------- storage (GitHub if configured, else local) ----------------
def secret(k):
    try:
        return st.secrets.get(k)
    except Exception:
        return None


REPO, TOKEN = secret("GITHUB_REPO"), secret("GITHUB_TOKEN")
GH = {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {})}


@st.cache_data(ttl=300, show_spinner=False)
def load(path):
    if REPO:
        r = requests.get(f"https://api.github.com/repos/{REPO}/contents/{path}",
                         headers={**GH, "Accept": "application/vnd.github.raw+json"}, timeout=20)
        if r.ok:
            return r.text
    f = ROOT / path
    return f.read_text(encoding="utf-8") if f.exists() else ""


def save(files, msg):
    if REPO and TOKEN:
        for path, text in files.items():
            url = f"https://api.github.com/repos/{REPO}/contents/{path}"
            cur = requests.get(url, headers=GH, timeout=20)
            body = {"message": msg, "content": base64.b64encode(text.encode()).decode()}
            if cur.ok:
                body["sha"] = cur.json().get("sha")
            r = requests.put(url, headers=GH, json=body, timeout=30)
            if not r.ok:
                return False, f"GitHub save failed for {path} (HTTP {r.status_code})"
        load.clear()
        return True, "Saved to GitHub"
    for path, text in files.items():
        (ROOT / path).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / path).write_text(text, encoding="utf-8")
    load.clear()
    return True, "Saved locally"


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def cached_lookup(query, choice):
    info, res, log = sc.lookup(query, choice)
    return info, res, log


# ---------------- page ----------------
st.markdown('<div class="sx-hero"><div><h1>Search any part</h1><div class="sx-sub">Type it the way you say it — '
            '<i>5070 rtx</i>, <i>intel ultra 7 cpu</i>, <i>9800x3d</i>, <i>sn7100 2tb</i>. We find it across Indian price trackers '
            'and show its price story since launch, plus its rating.</div></div></div>', unsafe_allow_html=True)

watch = json.loads(load("data/watchlist.json") or "[]")
c1, c2 = st.columns([5, 1])
q = c1.text_input("Search", value=st.session_state.get("q", ""), placeholder="e.g. 5070 rtx · intel ultra 7 cpu · 9800x3d",
                  label_visibility="collapsed")
go_ = c2.button("Search", type="primary", width="stretch")
if watch:
    pick = st.pills("Tracked", [w["canonical"] for w in watch], label_visibility="collapsed", selection_mode="single")
    if pick and pick != st.session_state.get("choice"):
        st.session_state.update(q=pick, choice=pick)
        st.rerun()
if go_ and q:
    st.session_state.update(q=q, choice=None)

query = st.session_state.get("q", "")
if not query:
    sec("How it works")
    a, b, c = st.columns(3)
    card(a, "1 · Understand", "Your words → exact model", "“5070 rtx” → RTX 5070 · “intel 7 ultra” → pick 265K / 265KF / …")
    card(b, "2 · Search", "4 Indian trackers", "gpuprix · pricehistory.app · pcpricetracker · pcpaisa")
    card(c, "3 · Story", "Launch → today → next", "Launch MSRP, every recorded drop, all-time low/high, rating; ⭐ to track it daily")
    st.stop()

info = sc.understand(query)
choice = st.session_state.get("choice")
if not info["canonical"] and not choice:
    sec(f"Which one did you mean?", f"“{query}” matches several models.")
    pick = st.pills("Choose", info["choices"], label_visibility="collapsed", selection_mode="single")
    if pick:
        st.session_state["choice"] = pick
        st.rerun()
    st.stop()

with st.spinner(f"Searching for {choice or info['canonical']} across Indian price trackers…"):
    info, res, log = cached_lookup(query, choice)
name = info["canonical"]

# merge in our own daily snapshots for this item (grows over time once tracked)
hist_rows = [r for r in sc.read_csv_text(load("data/search_history.csv")) if r["item"] == name]
rev_rows = [r for r in sc.read_csv_text(load("data/search_reviews.csv")) if r["item"] == name]
pts = list(res["points"]) if res else []
pts += [(date.fromisoformat(r["date"]), int(float(r["price"])), r["source"]) for r in hist_rows]
pts = sorted(set(pts))

if not pts:
    st.warning(f"Couldn't find price data for **{name}** right now. The search engine or the sites may be blocking this "
               "server — add a free Google/Brave search key in Secrets (see README), or try a more exact name.")
    with st.expander("What was tried"):
        st.dataframe(pd.DataFrame(log), hide_index=True, width="stretch")
    st.stop()

# ---------------- derived facts ----------------
df = pd.DataFrame(pts, columns=["date", "price", "source"])
df["date"] = pd.to_datetime(df["date"])
df["site"] = df["source"].str.split(" · ").str[0]
recent = df[df["date"] >= df["date"].max() - pd.Timedelta(days=10)]
now = recent.loc[recent["price"].idxmin()]
lo, hi = df.loc[df["price"].idxmin()], df.loc[df["price"].idxmax()]
launch = res.get("launch", {}) if res else {}
stats = res.get("stats", {}) if res else {}
ld = launch.get("date")
since = ld or launch.get("tracked_since") or df["date"].min().date()
rating = res.get("rating") if res else None

# ---------------- header ----------------
title = (res.get("titles") or [name])[0] if res else name
chips = "".join(f'<span class="sx-chip">{x}</span>' for x in
                [info["kind"], f"{len(df)} price points", f"{df['site'].nunique()} sources",
                 f"on market since {since:%b %Y}" if ld else f"tracked since {since:%b %Y}"])
st.markdown(f'<div class="sx-name">{name}</div><div class="sx-note">{title if title != name else ""}</div>{chips}',
            unsafe_allow_html=True)
st.write("")
k = st.columns(6)
card(k[0], "Best price now", inr(now["price"]), f'{now["source"]} · {now["date"]:%d %b}')
card(k[1], "All-time low", inr(lo["price"]), f'{lo["date"]:%d %b %Y}')
card(k[2], "Peak", inr(hi["price"]), f'{hi["date"]:%d %b %Y}')
if launch.get("msrp"):
    card(k[3], "vs launch price", f'{(now["price"] / launch["msrp"] - 1) * 100:+.0f}%', f'MSRP {inr(launch["msrp"])} (est.)')
else:
    card(k[3], "vs average", f'{(now["price"] / stats["avg"] - 1) * 100:+.0f}%' if stats.get("avg") else "–",
         f'avg {inr(stats.get("avg"))}' if stats.get("avg") else "")
days = (date.today() - since).days
card(k[4], "Launched" if ld else "Tracked since", f"{since:%b %Y}", f"{days} days {'on the market' if ld else 'of history'}")
card(k[5], "Rating", f'{rating["score"]:g}/{rating["out_of"]}' if rating else "–",
     f'{rating["count"]} reviews · {rating["source"]}' if rating and rating.get("count") else (rating or {}).get("source", "no rating found"))

w_names = [w["canonical"] for w in watch]
b1, b2, _ = st.columns([1.2, 1.2, 5])
if name not in w_names:
    if b1.button("⭐ Track daily", width="stretch") and res:
        watch.append({"canonical": name, "query": query, "kind": info["kind"], "urls": res["urls"], "added": date.today().isoformat()})
        p_rows, r_rows = sc.snapshot_rows(name, res)
        H = sc.read_csv_text(load("data/search_history.csv")) + p_rows
        R = sc.read_csv_text(load("data/search_reviews.csv")) + r_rows
        ok, msg = save({"data/watchlist.json": json.dumps(watch, indent=2, default=str),
                        "data/search_history.csv": sc.to_csv(H, sc.HIST_FIELDS),
                        "data/search_reviews.csv": sc.to_csv(R, sc.REV_FIELDS)}, f"Track {name}")
        st.toast(msg + " — refreshed daily from now on", icon="⭐" if ok else "⚠️")
else:
    b1.markdown('<span class="sx-chip">⭐ tracked daily</span>', unsafe_allow_html=True)
    if b2.button("Stop tracking", width="stretch"):
        watch = [w for w in watch if w["canonical"] != name]
        ok, msg = save({"data/watchlist.json": json.dumps(watch, indent=2, default=str)}, f"Untrack {name}")
        st.toast(msg)

# ---------------- 1. the price story ----------------
sec("The price story", "Every recorded price from every source. Dashed lines are reference prices.")
fig = go.Figure()
line = df.groupby("date", as_index=False)["price"].min()
fig.add_scatter(x=line["date"], y=line["price"], mode="lines", line=dict(color="#C9CDD6", width=1.6, shape="hv"),
                name="Lowest known", hoverinfo="skip")
for site, g in df.groupby("site"):
    fig.add_scatter(x=g["date"], y=g["price"], mode="markers", name=site,
                    marker=dict(size=9, color=SRC_COL.get(site, ACC), line=dict(color="#0B0D12", width=1)),
                    customdata=g["source"], hovertemplate="%{x|%d %b %Y}<br><b>₹%{y:,.0f}</b><br>%{customdata}<extra></extra>")
for key, lab, col in (("msrp", "launch MSRP", "#A3E635"),):
    if launch.get(key):
        fig.add_hline(y=launch[key], line=dict(color=col, dash="dash", width=1), annotation_text=f"{lab} {inr(launch[key])}",
                      annotation_position="top left", annotation_font=dict(color=col, size=11))
for key, lab, col in (("median_12m", "12-mo median", "#94A3B8"), ("low_12m", "12-mo low", GOOD), ("avg", "average", "#94A3B8")):
    if stats.get(key):
        fig.add_hline(y=stats[key], line=dict(color=col, dash="dot", width=1), annotation_text=f"{lab} {inr(stats[key])}",
                      annotation_position="bottom right", annotation_font=dict(color=col, size=11))
if ld:
    fig.add_vline(x=pd.Timestamp(ld), line=dict(color=MUTED, dash="dot", width=1))
    fig.add_annotation(x=pd.Timestamp(ld), y=1, yref="paper", text="launch", showarrow=False, yanchor="bottom", font=dict(color=MUTED, size=11))
    fig.update_xaxes(range=[pd.Timestamp(ld) - pd.Timedelta(days=20), pd.Timestamp(date.today()) + pd.Timedelta(days=20)])
fig.add_annotation(x=lo["date"], y=lo["price"], text=f"low {inr(lo['price'])}", ay=30, arrowhead=0, arrowcolor=GOOD, font=dict(color=GOOD, size=11))
if hi["price"] != lo["price"]:
    fig.add_annotation(x=hi["date"], y=hi["price"], text=f"peak {inr(hi['price'])}", ay=-30, arrowhead=0, arrowcolor=BAD, font=dict(color=BAD, size=11))
fig.update_yaxes(tickprefix="₹", tickformat=",.0f")
st.plotly_chart(layout(fig, 460), width="stretch", config=PC)

# ---------------- 2. where today sits + monthly ----------------
a, b = st.columns([2, 3])
with a:
    ref_lo = min(lo["price"], stats.get("low_12m") or lo["price"])
    ref_hi = max(hi["price"], launch.get("msrp") or 0)
    g = go.Figure(go.Indicator(
        mode="gauge+number", value=float(now["price"]), number=dict(prefix="₹", valueformat=",.0f", font=dict(size=30, color="#F2F3F7")),
        gauge=dict(axis=dict(range=[ref_lo * 0.95, ref_hi * 1.02], tickvals=[ref_lo, (ref_lo + ref_hi) / 2, ref_hi],
                             ticktext=[f"₹{v / 1000:,.0f}k" for v in (ref_lo, (ref_lo + ref_hi) / 2, ref_hi)], tickcolor=MUTED),
                   bar=dict(color=ACC, thickness=0.28), bgcolor="#141821", borderwidth=0,
                   steps=[dict(range=[ref_lo * 0.95, ref_lo + (ref_hi - ref_lo) / 3], color="rgba(52,211,153,0.18)"),
                          dict(range=[ref_lo + (ref_hi - ref_lo) / 3, ref_lo + 2 * (ref_hi - ref_lo) / 3], color="rgba(245,158,11,0.14)"),
                          dict(range=[ref_lo + 2 * (ref_hi - ref_lo) / 3, ref_hi * 1.02], color="rgba(251,113,133,0.16)")],
                   threshold=dict(line=dict(color=GOOD, width=3), value=float(lo["price"])))))
    pos = (now["price"] - ref_lo) / max(1, ref_hi - ref_lo)
    verdict = "a good time to buy" if pos < 1 / 3 else "a fair price" if pos < 2 / 3 else "expensive vs its history"
    st.plotly_chart(layout(g, 300, "Where today's price sits"), width="stretch", config=PC)
    st.markdown(f'<div class="sx-note" style="text-align:center">Today is <b>{verdict}</b> — green tick = all-time low</div>',
                unsafe_allow_html=True)
with b:
    df["m"] = df["date"].dt.to_period("M").dt.to_timestamp()
    mo = df.sort_values("date").groupby("m")["price"].agg(open="first", high="max", low="min", close="last").reset_index()
    if len(mo) >= 2:
        c = go.Figure(go.Candlestick(x=mo["m"], open=mo["open"], high=mo["high"], low=mo["low"], close=mo["close"],
                                     increasing=dict(line=dict(color=BAD), fillcolor="rgba(251,113,133,0.5)"),
                                     decreasing=dict(line=dict(color=GOOD), fillcolor="rgba(52,211,153,0.5)")))
        c.update_layout(xaxis_rangeslider_visible=False)
        c.update_yaxes(tickprefix="₹", tickformat=",.0f")
        st.plotly_chart(layout(c, 330, "Month by month (open · high · low · close)"), width="stretch", config=PC)
    else:
        drops = df.sort_values("date")["price"].diff()
        st.markdown('<div class="sx-note">Month-by-month view appears once prices span 2+ months.</div>', unsafe_allow_html=True)

# ---------------- 3. ratings over time ----------------
sec("Rating history", "Captured each day this product is tracked. Shows whether buyer opinion is improving or slipping.")
rv = pd.DataFrame(rev_rows)
if rating:
    rv = pd.concat([rv, pd.DataFrame([{"date": date.today().isoformat(), "score": rating["score"], "out_of": rating["out_of"],
                                       "count": rating.get("count"), "source": rating["source"]}])], ignore_index=True)
if rv.empty:
    st.markdown('<div class="sx-note">No public rating found for this product on the tracked sites.</div>', unsafe_allow_html=True)
else:
    rv["date"] = pd.to_datetime(rv["date"])
    rv["score"] = pd.to_numeric(rv["score"], errors="coerce")
    rv["out_of"] = pd.to_numeric(rv["out_of"], errors="coerce")
    rv["count"] = pd.to_numeric(rv["count"], errors="coerce")
    rv = rv.drop_duplicates(["date", "source"], keep="last").sort_values("date")
    a, b = st.columns([1, 3])
    with a:
        r = rv.iloc[-1]
        pie = go.Figure(go.Pie(values=[r["score"], r["out_of"] - r["score"]], hole=0.78, sort=False, textinfo="none",
                               marker=dict(colors=[ACC, "#1F2430"]), hoverinfo="skip"))
        pie.update_layout(showlegend=False, annotations=[dict(text=f"<b>{r['score']:g}</b><br><span style='font-size:11px;color:#8A90A2'>out of {r['out_of']:g}</span>",
                                                              showarrow=False, font=dict(size=26, color="#F2F3F7"))])
        st.plotly_chart(layout(pie, 240, f"Rating today · {r['source']}"), width="stretch", config=PC)
    with b:
        rf = go.Figure()
        if rv["count"].notna().any():
            rf.add_bar(x=rv["date"], y=rv["count"], name="number of reviews", marker=dict(color="rgba(56,189,248,0.35)"), yaxis="y2")
        rf.add_scatter(x=rv["date"], y=rv["score"] / rv["out_of"] * 10, mode="lines+markers", name="score /10",
                       line=dict(color=ACC, width=3), marker=dict(size=9))
        rf.update_layout(yaxis=dict(range=[0, 10.5], title="score /10"), yaxis2=dict(overlaying="y", side="right", showgrid=False, title="reviews"))
        st.plotly_chart(layout(rf, 260, "Score and review count over time"), width="stretch", config=PC)
        if len(rv) < 2:
            st.markdown('<div class="sx-note">Only today\'s rating so far — press ⭐ Track daily to build this history.</div>',
                        unsafe_allow_html=True)

# ---------------- 4. extras ----------------
specs = res.get("specs", {}) if res else {}
boards = res.get("boards", []) if res else []
if specs or boards:
    sec("Specs & cheapest versions")
    a, b = st.columns([1, 2])
    with a:
        labels = {"arch": "Architecture", "vram": "VRAM (GB)", "tdp": "Power (W)", "perf": "Performance score /100", "value": "Value score"}
        st.dataframe(pd.DataFrame([{"Spec": labels.get(k_, k_), "Value": v} for k_, v in specs.items()]), hide_index=True, width="stretch")
    with b:
        if boards:
            bd = pd.DataFrame(boards).sort_values("price")
            bf = go.Figure(go.Bar(x=bd["price"], y=bd["brand"] + " " + bd["series"], orientation="h",
                                  marker=dict(color=[ACC if s else "#3A4155" for s in bd["in_stock"]]),
                                  text=[inr(p) for p in bd["price"]], textposition="outside",
                                  hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>"))
            bf.update_layout(yaxis=dict(autorange="reversed"))
            bf.update_xaxes(tickprefix="₹", tickformat=",.0f")
            st.plotly_chart(layout(bf, 60 + 34 * len(bd), "Cheapest boards today (grey = out of stock)"), width="stretch", config=PC)

with st.expander("Sources & search log"):
    if res and res.get("urls"):
        st.dataframe(pd.DataFrame([{"Site": s_, "Page": u} for s_, u in res["urls"].items()]), hide_index=True, width="stretch",
                     column_config={"Page": st.column_config.LinkColumn()})
    st.dataframe(pd.DataFrame(log), hide_index=True, width="stretch")
    st.download_button("Download prices (CSV)", df[["date", "price", "source"]].to_csv(index=False), f"{name}.csv", "text/csv")
st.caption("Prices and ratings come from public tracker pages and may lag the stores. Launch MSRP in ₹ is gpuprix's estimate.")
