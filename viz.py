"""Design system: CSS, Plotly theme and reusable chart builders for the dashboard."""
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

ACCENT = "#8B7CFF"
PALETTE = ["#8B7CFF", "#38BDF8", "#34D399", "#F59E0B", "#F472B6", "#A3E635", "#FB7185", "#94A3B8", "#22D3EE", "#FACC15"]
MUTED = "#8A90A2"
GOOD, WARN, BAD, INFO = "#34D399", "#F59E0B", "#FB7185", "#38BDF8"
def rgba(hex_, a):
    h = hex_.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


SERIES_COLORS = {"Your tracker": ACCENT, "Long-run history": "#38BDF8", "Market scan": "#34D399"}

pio.templates["minimal"] = go.layout.Template(layout=go.Layout(
    font=dict(family="Inter, system-ui, sans-serif", color="#C9CDD6", size=12),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", colorway=PALETTE,
    xaxis=dict(gridcolor="rgba(255,255,255,0.05)", zeroline=False, linecolor="rgba(255,255,255,0.1)"),
    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", zeroline=False, linecolor="rgba(255,255,255,0.1)"),
    hoverlabel=dict(bgcolor="#1A1F2B", bordercolor="#2A3040", font=dict(color="#E6E8EE")),
    legend=dict(orientation="h", yanchor="top", y=-0.16, x=0, bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
    margin=dict(l=8, r=8, t=44, b=8), title=dict(font=dict(size=14, color="#E6E8EE"), x=0, xanchor="left"),
))
pio.templates.default = "minimal"
CFG = {"displayModeBar": False}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input { font-family: 'Inter', system-ui, sans-serif !important; }
#MainMenu, footer, [data-testid="stDecoration"] { visibility: hidden; height: 0; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1400px; }
h1, h2, h3 { letter-spacing: -0.02em; }
.hero { display:flex; justify-content:space-between; align-items:flex-end; margin-bottom: 1.2rem; }
.hero h1 { font-size: 2.1rem; font-weight: 700; margin: 0; background: linear-gradient(90deg,#E6E8EE,#8B7CFF);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.hero p { color: #8A90A2; margin: .25rem 0 0 0; font-size: .92rem; }
.chip { display:inline-block; padding: .22rem .65rem; border-radius: 999px; font-size: .75rem; font-weight: 500;
  border: 1px solid #262C3A; color: #B5BAC7; background: #121620; margin-left: .35rem; }
.kpi { background: linear-gradient(180deg,#141821,#10131A); border: 1px solid #1F2430; border-radius: 16px;
  padding: 1rem 1.1rem; height: 100%; }
.kpi .l { color: #8A90A2; font-size: .78rem; text-transform: uppercase; letter-spacing: .06em; }
.kpi .v { color: #F2F3F7; font-size: 1.65rem; font-weight: 650; margin-top: .2rem; letter-spacing: -0.02em; }
.kpi .d { font-size: .8rem; margin-top: .15rem; }
.card { background: #10131A; border: 1px solid #1F2430; border-radius: 14px; padding: .8rem .9rem .3rem .9rem; }
.card .t { color:#8A90A2; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; }
.card .m { color:#C9CDD6; font-size:.8rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.card .p { color:#F2F3F7; font-size:1.25rem; font-weight:650; margin-top:.15rem; }
.pill { display:inline-block; padding:.12rem .55rem; border-radius:999px; font-size:.7rem; font-weight:600; margin-top:.3rem; }
.sec { color:#E6E8EE; font-size:1.05rem; font-weight:600; margin: 1.6rem 0 .1rem 0; }
.sub { color:#8A90A2; font-size:.85rem; margin-bottom:.5rem; }
.stTabs [data-baseweb="tab-list"] { gap: .25rem; border-bottom: 1px solid #1F2430; }
.stTabs [data-baseweb="tab"] { padding: .55rem 1rem; border-radius: 10px 10px 0 0; color: #8A90A2; }
.stTabs [aria-selected="true"] { color: #F2F3F7 !important; }
[data-testid="stMetric"] { background:#10131A; border:1px solid #1F2430; border-radius:14px; padding:.7rem .9rem; }
</style>
"""

SIGNAL_STYLE = {"BUY": (GOOD, "BUY"), "Rising": (WARN, "RISING"), "Falling -": (INFO, "FALLING"),
                "Falling slowly": (MUTED, "SLOW FALL"), "Flat": (MUTED, "FLAT")}


def inr(v, short=False):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    v = float(v)
    if short and abs(v) >= 100000:
        return f"₹{v / 100000:.2f}L"
    if short and abs(v) >= 1000:
        return f"₹{v / 1000:.1f}k"
    return f"₹{v:,.0f}"


def stat(label, value, sub=""):
    return (f'<div class="kpi" style="padding:.75rem .9rem"><div class="l">{label}</div>'
            f'<div class="v" style="font-size:1.3rem">{value}</div><div class="d" style="color:{MUTED}">{sub}</div></div>')


def kpi(label, value, delta="", color=MUTED):
    return f'<div class="kpi"><div class="l">{label}</div><div class="v">{value}</div><div class="d" style="color:{color}">{delta}</div></div>'


def pill(signal):
    col, txt = next((v for k, v in SIGNAL_STYLE.items() if signal.startswith(k)), (MUTED, signal.upper()[:10]))
    return f'<span class="pill" style="background:{col}22;color:{col};border:1px solid {col}55">{txt}</span>'


def section(title, sub=""):
    return f'<div class="sec">{title}</div>' + (f'<div class="sub">{sub}</div>' if sub else "")


# ---------------- chart builders ----------------
def sparkline(pts, target=None, color=ACCENT):
    fig = go.Figure()
    if pts:
        x, y = [p[0] for p in pts], [p[1] for p in pts]
        if len(pts) == 1:
            x, y = [x[0] - timedelta(days=1), x[0]], [y[0], y[0]]
        fig.add_scatter(x=x, y=y, mode="lines", line=dict(color=color, width=2, shape="hv"),
                        fill="tozeroy", fillcolor=rgba(color, 0.09), hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.0f}<extra></extra>")
        if target:
            fig.add_hline(y=target, line=dict(color=GOOD, width=1, dash="dot"))
        lo, hi = min(y + ([target] if target else [])), max(y + ([target] if target else []))
        pad = (hi - lo) * 0.25 or hi * 0.05
        fig.update_yaxes(range=[lo - pad, hi + pad])
    fig.update_layout(height=70, margin=dict(l=0, r=0, t=4, b=0), showlegend=False,
                      xaxis=dict(visible=False), yaxis=dict(visible=False))
    return fig


def waterfall(parts, target_total, latest_total):
    fig = go.Figure(go.Waterfall(
        orientation="v", measure=["absolute"] + ["relative"] * len(parts) + ["total"],
        x=["Target"] + [p for p, _ in parts] + ["Today"],
        y=[target_total] + [d for _, d in parts] + [latest_total],
        text=[inr(target_total, True)] + [("+" if d >= 0 else "−") + inr(abs(d), True) for _, d in parts] + [inr(latest_total, True)],
        textposition="outside", connector=dict(line=dict(color="#2A3040", width=1)),
        increasing=dict(marker=dict(color=BAD)), decreasing=dict(marker=dict(color=GOOD)),
        totals=dict(marker=dict(color=ACCENT)), hovertemplate="%{x}<br>%{text}<extra></extra>"))
    lo = min(target_total, latest_total) * 0.85
    fig.update_layout(height=340, title="From target to today — which parts push the cost up",
                      yaxis=dict(range=[lo, max(target_total, latest_total) * 1.08], tickprefix="₹", tickformat=",.0f"),
                      showlegend=False)
    return fig


def donut(labels, values):
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.68, sort=True, textinfo="none",
                           marker=dict(colors=PALETTE, line=dict(color="#0B0D12", width=2)),
                           hovertemplate="%{label}<br>₹%{value:,.0f} · %{percent}<extra></extra>"))
    fig.update_layout(height=340, title="Where the money goes", showlegend=True,
                      legend=dict(orientation="v", x=1, y=0.5, font=dict(size=11)),
                      annotations=[dict(text=f"<b>{inr(sum(values), True)}</b><br><span style='font-size:11px;color:#8A90A2'>today</span>",
                                        showarrow=False, font=dict(size=20, color="#F2F3F7"))])
    return fig


def target_bullets(rows):
    """rows: [{part, low, high, latest, target, f90}] -> one axis in % of target."""
    fig = go.Figure()
    y = [r["part"] for r in rows][::-1]
    rs = rows[::-1]
    pct = lambda v, t: v / t * 100 if v and t else None
    fig.add_bar(y=y, x=[pct(r["high"], r["target"]) - pct(r["low"], r["target"]) for r in rs],
                base=[pct(r["low"], r["target"]) for r in rs], orientation="h", marker=dict(color="#2A3040"),
                width=0.42, name="Seen range", hovertemplate="%{y}: seen range<extra></extra>")
    fig.add_scatter(y=y, x=[pct(r["f90"], r["target"]) for r in rs], mode="markers", name="In 90 days",
                    marker=dict(symbol="line-ns", size=16, line=dict(width=3, color=WARN)),
                    customdata=[inr(r["f90"]) for r in rs], hovertemplate="%{y}: in 90 days %{customdata}<extra></extra>")
    fig.add_scatter(y=y, x=[pct(r["latest"], r["target"]) for r in rs], mode="markers", name="Today",
                    marker=dict(size=13, color=[GOOD if r["latest"] <= r["target"] else ACCENT for r in rs],
                                line=dict(color="#0B0D12", width=2)),
                    customdata=[inr(r["latest"]) for r in rs], hovertemplate="%{y}: today %{customdata} · %{x:.0f}% of target<extra></extra>")
    fig.add_vline(x=100, line=dict(color=GOOD, width=1.5, dash="dot"))
    fig.add_annotation(x=100, y=1.02, yref="paper", text="target", showarrow=False, font=dict(color=GOOD, size=11))
    fig.update_layout(height=330, title="Distance to target (100% = your target price)", barmode="overlay",
                      xaxis=dict(ticksuffix="%"))
    return fig


def forecast_fan(today_total, f30, f90, f1y, lo_mult=0.5, hi_mult=1.5):
    d0 = date.today()
    xs = [d0, d0 + timedelta(days=30), d0 + timedelta(days=90), d0 + timedelta(days=365)]
    mid = [today_total, f30, f90, f1y]
    lo = [today_total + (m - today_total) * lo_mult for m in mid]
    hi = [today_total + (m - today_total) * hi_mult for m in mid]
    fig = go.Figure()
    fig.add_scatter(x=xs + xs[::-1], y=hi + lo[::-1], mode="lines", fill="toself", fillcolor=rgba(ACCENT, 0.13), line=dict(width=0),
                    hoverinfo="skip", name="Sensitivity band")
    fig.add_scatter(x=xs, y=mid, mode="lines+markers+text", line=dict(color=ACCENT, width=3), name="Forecast",
                    text=[inr(v, True) for v in mid], textposition="top center", textfont=dict(color="#C9CDD6"),
                    hovertemplate="%{x|%d %b %Y}<br>₹%{y:,.0f}<extra></extra>")
    fig.update_layout(height=330, title="Whole build: where the price is heading", yaxis=dict(tickprefix="₹", tickformat=",.0f"))
    return fig


def journey(points, title, launch=None, target=None, fc=None):
    """Main price timeline: step line + markers by series, launch/MSRP/medians, low/high, forecast cone."""
    fig = go.Figure()
    if not points:
        return fig
    df = pd.DataFrame(points)
    df["date"] = pd.to_datetime(df["date"])
    line = df.groupby("date", as_index=False)["price"].min()
    fig.add_scatter(x=line["date"], y=line["price"], mode="lines", line=dict(color="#C9CDD6", width=1.6, shape="hv"),
                    name="Lowest known", hoverinfo="skip")
    for s, g in df.groupby("series"):
        fig.add_scatter(x=g["date"], y=g["price"], mode="markers", name=s,
                        marker=dict(size=8, color=SERIES_COLORS.get(s, ACCENT), line=dict(color="#0B0D12", width=1)),
                        customdata=g["source"], hovertemplate="%{x|%d %b %Y}<br><b>₹%{y:,.0f}</b><br>%{customdata}<extra></extra>")
    lo, hi = df.loc[df["price"].idxmin()], df.loc[df["price"].idxmax()]
    fig.add_annotation(x=lo["date"], y=lo["price"], text=f"low {inr(lo['price'], True)}", showarrow=True, arrowhead=0,
                       ay=30, font=dict(color=GOOD, size=11), arrowcolor=GOOD)
    if hi["price"] != lo["price"]:
        fig.add_annotation(x=hi["date"], y=hi["price"], text=f"high {inr(hi['price'], True)}", showarrow=True, arrowhead=0,
                           ay=-30, font=dict(color=BAD, size=11), arrowcolor=BAD)
    if launch:
        if launch.get("launch"):
            ld = pd.to_datetime(launch["launch"])
            fig.add_vline(x=ld, line=dict(color=MUTED, width=1, dash="dot"))
            fig.add_annotation(x=ld, y=1, yref="paper", text="launch", showarrow=False, yanchor="bottom",
                               font=dict(color=MUTED, size=11))
        for key, lab, col in (("msrp_inr", "launch MSRP", "#A3E635"), ("median_12m", "12-mo median", "#94A3B8")):
            if launch.get(key):
                fig.add_hline(y=launch[key], line=dict(color=col, width=1, dash="dash"),
                              annotation_text=f"{lab} {inr(launch[key], True)}", annotation_position="top left",
                              annotation_font=dict(color=col, size=11))
    if target:
        fig.add_hline(y=target, line=dict(color=GOOD, width=1.5, dash="dot"), annotation_text=f"your target {inr(target, True)}",
                      annotation_position="bottom right", annotation_font=dict(color=GOOD, size=11))
    if fc:
        last = pd.to_datetime(fc["last_date"])
        xs = [last, last + pd.Timedelta(days=30), last + pd.Timedelta(days=90), last + pd.Timedelta(days=365)]
        mid = [fc["latest"], fc["f30"], fc["f90"], fc["f1y"]]
        band = [abs(m - fc["latest"]) * 0.5 + fc["latest"] * 0.03 * i for i, m in enumerate(mid)]
        fig.add_scatter(x=xs + xs[::-1], y=[m + b for m, b in zip(mid, band)] + [m - b for m, b in zip(mid, band)][::-1],
                        mode="lines", fill="toself", fillcolor=rgba(ACCENT, 0.12), line=dict(width=0), name="Forecast range", hoverinfo="skip")
        fig.add_scatter(x=xs, y=mid, mode="lines+markers", line=dict(color=ACCENT, dash="dash", width=2), name="Forecast",
                        hovertemplate="%{x|%d %b %Y}<br>forecast ₹%{y:,.0f}<extra></extra>")
    fig.update_xaxes(rangeselector=dict(
        buttons=[dict(count=3, label="3M", step="month", stepmode="backward"),
                 dict(count=6, label="6M", step="month", stepmode="backward"),
                 dict(count=1, label="1Y", step="year", stepmode="backward"), dict(step="all", label="All")],
        bgcolor="#141821", activecolor="#2A3040", font=dict(color="#C9CDD6"), x=1, xanchor="right", y=1.02, yanchor="bottom"))
    fig.update_layout(height=470, title=title, yaxis=dict(tickprefix="₹", tickformat=",.0f"))
    return fig


def monthly_candles(points):
    df = pd.DataFrame(points)
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df["m"] = df["date"].dt.to_period("M").dt.to_timestamp()
    g = df.groupby("m")["price"].agg(open="first", high="max", low="min", close="last").reset_index()
    if len(g) < 2:
        return None
    fig = go.Figure(go.Candlestick(x=g["m"], open=g["open"], high=g["high"], low=g["low"], close=g["close"],
                                   increasing=dict(line=dict(color=BAD), fillcolor=rgba(BAD, 0.53)),
                                   decreasing=dict(line=dict(color=GOOD), fillcolor=rgba(GOOD, 0.53))))
    fig.update_layout(height=300, title="Month by month (open · high · low · close)", xaxis_rangeslider_visible=False,
                      yaxis=dict(tickprefix="₹", tickformat=",.0f"))
    return fig


def compare_lines(series, mode):
    """series: {name: [(date, price)]}; mode 'Indexed' or 'Absolute'."""
    fig = go.Figure()
    for i, (name, pts) in enumerate(series.items()):
        if not pts:
            continue
        pts = sorted(pts)
        base = pts[0][1]
        y = [p / base * 100 for _, p in pts] if mode == "Indexed" else [p for _, p in pts]
        fig.add_scatter(x=[d for d, _ in pts], y=y, mode="lines+markers", name=name,
                        line=dict(shape="hv", width=2, color=PALETTE[i % len(PALETTE)]), marker=dict(size=5),
                        customdata=[p for _, p in pts],
                        hovertemplate=f"{name}<br>%{{x|%d %b %Y}}<br>₹%{{customdata:,.0f}}<extra></extra>")
    if mode == "Indexed":
        fig.add_hline(y=100, line=dict(color=MUTED, width=1, dash="dot"))
        fig.update_layout(yaxis=dict(ticksuffix=""), title="Journeys compared (first known price = 100)")
    else:
        fig.update_layout(yaxis=dict(tickprefix="₹", tickformat=",.0f", type="log"), title="Journeys compared (₹, log scale)")
    fig.update_layout(height=400)
    return fig


def launch_dumbbell(rows):
    """rows: [{name, msrp, low, median, today}] -> dot plot from launch MSRP to today."""
    fig = go.Figure()
    names = [r["name"] for r in rows]
    for r in rows:
        vals = [v for v in (r["msrp"], r["low"], r["median"], r["today"]) if v]
        fig.add_scatter(x=[min(vals), max(vals)], y=[r["name"]] * 2, mode="lines", line=dict(color="#2A3040", width=6),
                        showlegend=False, hoverinfo="skip")
    for key, lab, col, sym in (("msrp", "Launch MSRP", "#A3E635", "circle-open"), ("low", "12-mo low", GOOD, "circle"),
                               ("median", "12-mo median", "#94A3B8", "diamond"), ("today", "Today", ACCENT, "star")):
        fig.add_scatter(x=[r[key] for r in rows], y=names, mode="markers", name=lab,
                        marker=dict(size=14 if key == "today" else 11, color=col, symbol=sym, line=dict(width=2, color=col)),
                        hovertemplate=f"%{{y}} · {lab}: ₹%{{x:,.0f}}<extra></extra>")
    for r in rows:
        if r["msrp"] and r["today"]:
            prem = (r["today"] / r["msrp"] - 1) * 100
            fig.add_annotation(x=r["today"], y=r["name"], text=f"{prem:+.0f}% vs MSRP", showarrow=False, xshift=58,
                               font=dict(color=BAD if prem > 0 else GOOD, size=11))
    fig.update_layout(height=80 + 60 * len(rows), title="GPUs since launch: MSRP → 12-month low/median → today",
                      xaxis=dict(tickprefix="₹", tickformat=",.0f"))
    return fig


# ---------------- market charts ----------------
def market_map(df):
    g = df.groupby(["category", "key"], as_index=False).agg(listings=("name", "size"), cheapest=("price", "min"))
    g = g[g["key"].astype(str).str.len() < 40]
    fig = go.Figure(go.Treemap(
        labels=list(g["category"].unique()) + list(g["key"]),
        parents=[""] * g["category"].nunique() + list(g["category"]),
        ids=list(g["category"].unique()) + [f"{c}/{k}" for c, k in zip(g["category"], g["key"])],
        values=[g[g["category"] == c]["listings"].sum() for c in g["category"].unique()] + list(g["listings"]),
        branchvalues="total", marker=dict(colorscale=[[0, "#1B2030"], [1, ACCENT]], line=dict(color="#0B0D12", width=1),
                                          colors=[0] * g["category"].nunique() + list(g["listings"])),
        customdata=[""] * g["category"].nunique() + [inr(v) for v in g["cheapest"]],
        hovertemplate="<b>%{label}</b><br>%{value} listings<br>from %{customdata}<extra></extra>",
        texttemplate="<b>%{label}</b><br>%{value}", tiling=dict(pad=2)))
    fig.update_layout(height=430, title="Market map — every model, sized by number of listings", margin=dict(t=40, l=0, r=0, b=0))
    return fig


def price_spread(d, n=18):
    top = d.groupby("key")["price"].agg(["size", "min"]).sort_values("size", ascending=False).head(n)
    sub = d[d["key"].isin(top.index)]
    order = sub.groupby("key")["price"].median().sort_values().index.tolist()
    fig = go.Figure()
    for i, k in enumerate(order):
        s = sub[sub["key"] == k]
        fig.add_box(x=s["price"], name=str(k), orientation="h", boxpoints="all", jitter=0.4, pointpos=0,
                    marker=dict(size=5, color=PALETTE[i % len(PALETTE)], opacity=0.8), line=dict(width=1, color="#3A4155"),
                    fillcolor="rgba(0,0,0,0)", customdata=s["name"],
                    hovertemplate="%{customdata}<br>₹%{x:,.0f}<extra></extra>", showlegend=False)
    fig.update_layout(height=max(320, 30 * len(order) + 80), title="Price spread per model — each dot is one listing",
                      xaxis=dict(tickprefix="₹", tickformat=",.0f"), yaxis=dict(categoryorder="array", categoryarray=order))
    return fig


def value_chart(cat, d, scores):
    d = d.copy()
    num = lambda c: pd.to_numeric(d.get(c), errors="coerce")
    if cat == "GPU":
        g = d.groupby("key", as_index=False).agg(price=("price", "min"), listings=("name", "size"), vram=("vram_gb", "first"))
        g["perf"] = g["key"].map(scores)
        g = g.dropna(subset=["perf"])
        if g.empty:
            return None, "Add GPU performance scores in market.json → gpu_scores to unlock this chart."
        g["value"] = g["perf"] / g["price"] * 100000
        fig = go.Figure(go.Scatter(x=g["price"], y=g["perf"], mode="markers+text", text=g["key"], textposition="top center",
                                   marker=dict(size=14 + g["listings"].clip(upper=20), color=g["value"],
                                               colorscale=[[0, BAD], [0.5, WARN], [1, GOOD]], showscale=False,
                                               line=dict(color="#0B0D12", width=1)),
                                   hovertemplate="%{text}<br>₹%{x:,.0f} · score %{y}<extra></extra>"))
        fig.update_layout(title="Performance vs price — up and to the left is better value",
                          xaxis=dict(title="cheapest price", tickprefix="₹", tickformat=",.0f"), yaxis=dict(title="performance score"))
        return fig, ""
    if cat == "RAM":
        d["₹/GB"] = d["price"] / num("total_gb")
        d["speed"], d["cl"] = num("speed"), num("cl")
        d = d.dropna(subset=["₹/GB", "speed"])
        fig = go.Figure(go.Scatter(x=d["speed"], y=d["₹/GB"], mode="markers", text=d["name"],
                                   marker=dict(size=10, color=d["cl"], colorscale="Viridis_r", showscale=True,
                                               colorbar=dict(title="CL", thickness=10), opacity=0.85),
                                   hovertemplate="%{text}<br>%{x} MHz · ₹%{y:,.0f}/GB<extra></extra>"))
        fig.update_layout(title="RAM value: ₹ per GB vs speed (colour = CL latency, lower is better)",
                          xaxis=dict(title="speed (MHz)"), yaxis=dict(title="₹ per GB", tickprefix="₹"))
        return fig, ""
    if cat == "SSD":
        d["cap"] = num("capacity_gb") / 1000
        d["₹/TB"] = d["price"] / d["cap"]
        d["gen"] = num("gen").fillna(0).astype(int).astype(str).replace("0", "SATA/?")
        d = d.dropna(subset=["₹/TB"])
        fig = go.Figure()
        for i, (gname, g) in enumerate(d.groupby("gen")):
            fig.add_scatter(x=g["cap"], y=g["₹/TB"], mode="markers", name=f"Gen {gname}" if gname[0].isdigit() else gname,
                            text=g["name"], marker=dict(size=10, color=PALETTE[i], opacity=0.85),
                            hovertemplate="%{text}<br>%{x} TB · ₹%{y:,.0f}/TB<extra></extra>")
        fig.update_layout(title="SSD value: ₹ per TB vs capacity", xaxis=dict(title="capacity (TB)", type="log"),
                          yaxis=dict(title="₹ per TB", tickprefix="₹", tickformat=",.0f"))
        return fig, ""
    if cat == "Power Supply":
        d["watt"] = num("watt")
        d = d.dropna(subset=["watt"])
        fig = go.Figure()
        for i, r in enumerate(["Titanium", "Platinum", "Gold", "Silver", "Bronze", ""]):
            g = d[d["rating"].fillna("") == r]
            if len(g):
                fig.add_scatter(x=g["watt"], y=g["price"], mode="markers", name=r or "Unrated", text=g["name"],
                                marker=dict(size=10, color=PALETTE[i], opacity=0.85),
                                hovertemplate="%{text}<br>%{x} W · ₹%{y:,.0f}<extra></extra>")
        fig.update_layout(title="PSU: price vs wattage by efficiency rating", xaxis=dict(title="watts"),
                          yaxis=dict(tickprefix="₹", tickformat=",.0f"))
        return fig, ""
    group = {"CPU": "socket", "Motherboard": "chipset", "CPU Cooler": "key", "Case": "key"}.get(cat, "key")
    if group not in d:
        return None, ""
    g = d.groupby(group)["price"].agg(["min", "median", "max", "size"]).sort_values("median").reset_index()
    g = g[g[group].astype(str).str.len() > 0].head(20)
    fig = go.Figure()
    fig.add_bar(y=g[group].astype(str), x=g["max"] - g["min"], base=g["min"], orientation="h", marker=dict(color="#2A3040"),
                name="min–max", hovertemplate="%{y}: ₹%{base:,.0f} – ₹%{x:,.0f}<extra></extra>")
    fig.add_scatter(y=g[group].astype(str), x=g["median"], mode="markers", name="median",
                    marker=dict(size=11, color=ACCENT), hovertemplate="%{y} median ₹%{x:,.0f}<extra></extra>")
    fig.update_layout(title=f"Price range by {group}", height=max(300, 28 * len(g) + 80),
                      xaxis=dict(tickprefix="₹", tickformat=",.0f"))
    return fig, ""


def brand_share(d):
    g = d.groupby("brand").size().sort_values(ascending=False)
    top = g.head(8)
    if len(g) > 8:
        top = pd.concat([top, pd.Series({"Others": g.iloc[8:].sum()})])
    fig = go.Figure(go.Pie(labels=top.index, values=top.values, hole=0.65, textinfo="none",
                           marker=dict(colors=PALETTE, line=dict(color="#0B0D12", width=2)),
                           hovertemplate="%{label}: %{value} listings (%{percent})<extra></extra>"))
    fig.update_layout(height=320, title="Brand share", legend=dict(orientation="v", x=1, y=0.5))
    return fig


def price_histogram(d):
    fig = go.Figure(go.Histogram(x=d["price"], nbinsx=30, marker=dict(color=ACCENT, line=dict(color="#0B0D12", width=1)),
                                 hovertemplate="₹%{x}<br>%{y} listings<extra></extra>"))
    fig.update_layout(height=320, title="How prices are distributed", xaxis=dict(tickprefix="₹", tickformat=",.0f"), bargap=0.05)
    return fig


def daily_min(mh, key=None, category=None):
    df = pd.DataFrame(mh)
    if df.empty:
        return df
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    if key:
        df = df[df["key"] == key]
    if category:
        df = df[df["category"] == category]
    # each listing keeps its price until it changes -> forward fill per URL, then daily min per key
    days = pd.date_range(df["date"].min(), df["date"].max()) if not df.empty else []
    piv = df.pivot_table(index="date", columns="url", values="price", aggfunc="last").reindex(days).ffill()
    keys = df.drop_duplicates("url").set_index("url")["key"]
    out = piv.T.groupby(keys).min().T
    out.index.name = "date"
    return out


def category_index(mh):
    df = pd.DataFrame(mh)
    if df.empty or df["date"].nunique() < 2:
        return None, None
    lines, heat = {}, {}
    for cat in sorted(df["category"].unique()):
        piv = daily_min(mh, category=cat)
        if piv.empty or len(piv) < 2:
            continue
        idx = (piv / piv.iloc[0]).median(axis=1) * 100
        lines[cat] = idx
        heat[cat] = idx.pct_change().fillna(0) * 100
    if not lines:
        return None, None
    fig = go.Figure()
    for i, (c, s) in enumerate(lines.items()):
        fig.add_scatter(x=s.index, y=s.values, mode="lines", name=c, line=dict(width=2, color=PALETTE[i % len(PALETTE)]),
                        hovertemplate=f"{c}<br>%{{x|%d %b}} · %{{y:.1f}}<extra></extra>")
    fig.add_hline(y=100, line=dict(color=MUTED, dash="dot", width=1))
    fig.update_layout(height=360, title="Market price index by category (first scan = 100)", xaxis=dict(tickformat="%d %b", dtick=86400000))
    h = pd.DataFrame(heat).T
    hf = go.Figure(go.Heatmap(z=h.values, x=h.columns, y=h.index, zmid=0,
                              colorscale=[[0, GOOD], [0.5, "#141821"], [1, BAD]], colorbar=dict(title="% Δ", thickness=10),
                              hovertemplate="%{y} · %{x|%d %b}<br>%{z:+.2f}%<extra></extra>"))
    hf.update_layout(height=320, title="Daily market heat — red = prices rising, green = falling", xaxis=dict(tickformat="%d %b", dtick=86400000))
    return fig, hf


def launch_radar(new_df):
    fig = go.Figure()
    for i, (c, g) in enumerate(new_df.groupby("category")):
        fig.add_scatter(x=pd.to_datetime(g["first_seen"]), y=[c] * len(g), mode="markers", name=c, text=g["name"],
                        marker=dict(size=(pd.to_numeric(g["price"], errors="coerce").fillna(1000) ** 0.5 / 6).clip(6, 40),
                                    color=PALETTE[i % len(PALETTE)], opacity=0.75, line=dict(color="#0B0D12", width=1)),
                        customdata=pd.to_numeric(g["price"], errors="coerce"),
                        hovertemplate="%{text}<br>₹%{customdata:,.0f} · %{x|%d %b}<extra></extra>")
    fig.update_layout(height=300, title="Launch radar — new listings over time (bubble size = price)", showlegend=False,
                      xaxis=dict(tickformat="%d %b"))
    return fig


def drops_chart(dd):
    dd = dd.sort_values("drop %").tail(20)
    fig = go.Figure(go.Bar(x=-dd["drop %"], y=dd["name"].str.slice(0, 48), orientation="h",
                           marker=dict(color=GOOD), text=[f"−{v:.0f}%  {inr(p, True)}" for v, p in zip(dd["drop %"], dd["price"])],
                           textposition="outside", hovertemplate="%{y}<br>%{text}<extra></extra>"))
    fig.update_traces(width=0.55)
    fig.update_layout(height=max(220, 34 * len(dd) + 90), title="Biggest price drops", xaxis=dict(ticksuffix="%"))
    return fig


def picks_dotplot(rows, title):
    rows = [r for r in rows if r["price"]]
    rows.sort(key=lambda r: r["price"])
    fig = go.Figure(go.Scatter(
        x=[r["price"] for r in rows], y=[r["model"] for r in rows], mode="markers+text",
        text=[inr(r["price"], True) for r in rows], textposition="middle right",
        marker=dict(size=[18 if r["yours"] else 11 for r in rows], symbol=["star" if r["yours"] else "circle" for r in rows],
                    color=[ACCENT if r["yours"] else "#3A4155" for r in rows]),
        hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>"))
    fig.update_layout(height=60 + 34 * len(rows), title=title, xaxis=dict(tickprefix="₹", tickformat=",.0f"), showlegend=False)
    return fig
