# -*- coding: utf-8 -*-
"""
Streamlit app – London‑wide Vapour Pressure Deficit (VPD) monitor
================================================================

Data sources remain Met Office DataPoint, Open‑Meteo and Meteostat.
"""
import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta, date
import requests
import matplotlib as mpl

st.set_page_config(
    page_title="VPD Monitor",
    page_icon="🌡️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Optional Meteostat fallback
import numpy as np
# Monkey-patch numpy.NaN for Meteostat compatibility
if not hasattr(np, 'NaN'):
    np.NaN = np.nan
try:
    from meteostat import Stations, Hourly
    METEOSTAT_AVAILABLE = True
except ImportError:
    METEOSTAT_AVAILABLE = False

# =====================================================
#                  ✨  LOOK & FEEL  ✨
# =====================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .section-title { font-size:18px; font-weight:500; display:flex; align-items:center; }
    .section-title:after { content:""; flex:1; margin-left:10px; border-bottom:2px solid; }
    .section-title            {{ color:{ACCENT}; }}
    .section-title:after      {{ border-bottom:2px solid {ACCENT}; }}
    .stDateInput label { font-size:18px; font-weight:500; } 
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- global Matplotlib theme ----------
mpl.rcParams.update({
    "font.family"   : "sans-serif",
    "font.sans-serif": ["Inter"],

    # colour cycle & faces …
    "axes.prop_cycle": mpl.cycler(color=["#1a73e8", "#ea4335", "#34a853", "#fbbc05"]),
    "axes.facecolor": "none",
    "figure.facecolor": "none",
    "savefig.facecolor": "none",

    # >>>  MAKE THEM BIGGER  <<<
    "axes.titlesize" : 20,      # figure titles  (if you use ax.set_title)**
    "axes.labelsize" : 18,      # x/y-axis labels**
    "xtick.labelsize": 16,      # tick numbers**
    "ytick.labelsize": 16,

})
# ---------- extra modern-look tweaks ----------
mpl.rcParams.update({
    # grids & ticks
    "axes.grid"       : True,
    "grid.color"      : "#d0d0d0",
    "grid.linestyle"  : "--",
    "grid.linewidth"  : 0.6,
    "axes.spines.right": False,      # hide heavy borders
    "axes.spines.top" : False,
    "xtick.major.size": 0,           # no heavy ticks
    "ytick.major.size": 0,

    # lines / markers
    "lines.linewidth" : 2.25,
    "lines.markersize": 6,

    # padding
    "figure.autolayout": True,       # tight-layout everywhere
})


# ---------- Dark-mode toggle ----------
dark = st.sidebar.toggle("🌙  Dark mode", key="dark_mode")
st.sidebar.markdown("<hr>", unsafe_allow_html=True)
st.sidebar.caption("⚙️  Adjust view options")
if dark:
    st.markdown(
        """
        <style>
        /* ───────── existing dark-mode rules … ───────── */
        body, .stApp              { background:#202124;  color:#e8eaed; }
        .stMarkdown div           { color:#e8eaed !important; }
        .stDateInput label        { color:#e8eaed !important; }
        .section-title            { color:#e8eaed !important; }
        .section-title:after      { border-bottom:2px solid #e8eaed !important; }

        /* --- DOWNLOAD-BUTTON : DARK THEME ---------------------------------- */
        /* outer <a> that really owns the background ------------------------- */
        div[data-testid="stDownloadButton"] > a{
            display:block;                 /* let the border span full width  */
            width:100%;
            background:transparent !important;   /* kill the white fill      */
            border:1px solid #8ab4f8 !important; /* same blue you chose       */
            color:#8ab4f8 !important;
            font-weight:600;
            border-radius:6px;
            padding:0.4rem 0.75rem;        /* little breathing-space          */
            text-align:center;             /* keep label centred              */
            transition:background .15s ease,color .15s ease;
        }
        div[data-testid="stDownloadButton"] > a:hover{
            background:#8ab4f8 !important; /* blue on hover                   */
            color:#202124 !important;      /* readable foreground             */
        }

        /* inner <button> – strip any residual styling ---------------------- */
        div[data-testid="stDownloadButton"] button{
            all:unset;                     /* wipe Streamlit's default rules  */
        }

        </style>
        """,
        unsafe_allow_html=True,
    )
    # ── NEW (keep the import line together with the call) ──────────────────
    import matplotlib.colors as _mcol
    _mcol.get_named_colors_mapping()['green'] = '#34c759'   # brighter green
    # ────

SUB_COLOUR = "#ffffff" if dark else "#5f6368"  # body text colour
#  Accent colours choose blue / green / amber based on past / today / future
ACCENT_MAP = {"past": "#2196f3", "today": "#34a853", "future": "#ff9800"}
# ──────────────────────────────────────────────────────────────────────────────
#  CONSTANTS & STATION META
# ──────────────────────────────────────────────────────────────────────────────
API_KEY = "c60bd66f-905f-48d0-885b-b5aa75c436cc"  # Met Office DataPoint key
THRESHOLD = 706                                   # Pa threshold for Firewave
MAX_FORECAST_DAYS = 4
HIST_DAYS = 9

#  Triple‑station inventory (Met Office DataPoint ID, Meteostat ID, lat/lon)
STATIONS = {
    "Northolt":  {"dp_id": "3672", "meta_id": "03672", "lat": 51.55, "lon": -0.42},
    "Heathrow":  {"dp_id": "3772", "meta_id": "03772", "lat": 51.48, "lon": -0.45},
    "Kenley":    {"dp_id": "3781", "meta_id": "03781", "lat": 51.30, "lon": -0.08},
}

#  Meteostat optional import
import numpy as np
if not hasattr(np, "NaN"):
    np.NaN = np.nan
try:
    from meteostat import Hourly
    METEOSTAT_AVAILABLE = True
except ImportError:
    METEOSTAT_AVAILABLE = False

# ──────────────────────────────────────────────────────────────────────────────
#  HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def calculate_vpd(temp, hum):
    """Calculate VPD (Pa) from °C and %RH."""
    esat = 610.7 * 10 ** (7.5 * temp / (237.3 + temp))
    return esat * (1 - hum / 100)


# -----------------------------------------------------------------------------
#  DATA FETCHERS – each returns a *station‑averaged* dataframe
# -----------------------------------------------------------------------------

def _fetch_met_office_obs(dp_id: str) -> pd.DataFrame:
    """Hourly observations for today for one station (Met Office DataPoint)."""
    url = f"http://datapoint.metoffice.gov.uk/public/data/val/wxobs/all/json/{dp_id}?res=hourly&key={API_KEY}"
    try:
        raw = requests.get(url, timeout=10).json()
        periods = raw["SiteRep"]["DV"]["Location"]["Period"]
    except Exception:
        return pd.DataFrame(columns=["time", "vpd"])

    records = []
    today = date.today()
    now = datetime.now()
    for p in periods:
        base = datetime.strptime(p["value"], "%Y-%m-%dZ")
        for rep in p.get("Rep", []):
            if not isinstance(rep, dict):
                continue
            ts = base + timedelta(minutes=int(rep.get("$", 0)))
            if ts.date() != today or ts > now:
                continue
            t, h = rep.get("T"), rep.get("H")
            if t is None or h is None:
                continue
            records.append({"time": ts, "vpd": calculate_vpd(float(t), float(h))})
    return pd.DataFrame(records)


def _fetch_met_office_fcst(dp_id: str) -> pd.DataFrame:
    """3‑hourly forecast for up to MAX_FORECAST_DAYS ahead for one station."""
    url = f"http://datapoint.metoffice.gov.uk/public/data/val/wxfcs/all/json/{dp_id}?res=3hourly&key={API_KEY}"
    cutoff = date.today() + timedelta(days=MAX_FORECAST_DAYS)
    try:
        periods = requests.get(url, timeout=10).json()["SiteRep"]["DV"]["Location"]["Period"]
    except Exception:
        return pd.DataFrame(columns=["time", "vpd"])

    recs = []
    for p in periods:
        base = datetime.strptime(p["value"], "%Y-%m-%dZ")
        for rep in p.get("Rep", []):
            if not isinstance(rep, dict):
                continue
            ts = base + timedelta(minutes=int(rep.get("$", 0)))
            if ts.date() > cutoff:
                continue
            t, h = rep.get("T"), rep.get("H")
            if t is None or h is None:
                continue
            recs.append({"time": ts, "vpd": calculate_vpd(float(t), float(h))})
    return pd.DataFrame(recs)


def _fetch_open_meteo(lat: float, lon: float, day: date) -> pd.DataFrame:
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": day.isoformat(),
        "end_date": day.isoformat(),
        "hourly": "temperature_2m,relativehumidity_2m",
        "timezone": "Europe/London",
    }
    try:
        hourly = requests.get(url, params=params, timeout=10).json()["hourly"]
    except Exception:
        return pd.DataFrame(columns=["time", "vpd"])
    df = pd.DataFrame({
        "time": pd.to_datetime(hourly.get("time", [])),
        "temperature": hourly.get("temperature_2m", []),
        "humidity": hourly.get("relativehumidity_2m", []),
    })
    df["vpd"] = calculate_vpd(df["temperature"], df["humidity"])
    return df[["time", "vpd"]]


def _fill_with_meteostat(df: pd.DataFrame, meta_id: str, day: date) -> pd.DataFrame:
    if not METEOSTAT_AVAILABLE:
        return df
    start_dt = datetime.combine(day, datetime.min.time())
    end_dt = datetime.combine(day, datetime.max.time())
    exp = pd.date_range(start_dt, end_dt, freq="H", inclusive="left")
    missing = exp.difference(df["time"]) if not df.empty else exp
    if missing.empty:
        return df
    try:
        stn = Hourly(meta_id, start_dt, end_dt).fetch().reset_index()
        stn["time"] = pd.to_datetime(stn["time"]).dt.tz_localize(None)
        stn["vpd"] = calculate_vpd(stn["temp"], stn["rhum"])
        fill = stn[stn["time"].isin(missing)][["time", "vpd"]].dropna()
    except Exception:
        fill = pd.DataFrame(columns=["time", "vpd"])
    out = pd.concat([df, fill]).drop_duplicates("time").sort_values("time")
    return out.reset_index(drop=True)


# -----------------------------------------------------------------------------
#  PUBLIC FETCH API (already returns station‑AVERAGED dataframes)
# -----------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def fetch_today() -> pd.DataFrame:
    dfs = []
    for s in STATIONS.values():
        df = _fetch_met_office_obs(s["dp_id"])
        if not df.empty:
            dfs.append(df)
    if not dfs:
        return pd.DataFrame(columns=["time", "vpd"])
    merged = pd.concat(dfs).groupby("time", as_index=False)["vpd"].mean()
    return merged


@st.cache_data(show_spinner=False)
def fetch_forecast() -> pd.DataFrame:
    dfs = []
    for s in STATIONS.values():
        df = _fetch_met_office_fcst(s["dp_id"])
        if not df.empty:
            dfs.append(df)
    if not dfs:
        return pd.DataFrame(columns=["time", "vpd"])
    return pd.concat(dfs).groupby("time", as_index=False)["vpd"].mean()


@st.cache_data(show_spinner=False)
def fetch_historical(day: date) -> pd.DataFrame:
    dfs = []
    for s in STATIONS.values():
        df = _fetch_open_meteo(s["lat"], s["lon"], day)
        df = _fill_with_meteostat(df, s["meta_id"], day)
        if not df.empty:
            dfs.append(df)
    if not dfs:
        return pd.DataFrame(columns=["time", "vpd"])
    return pd.concat(dfs).groupby("time", as_index=False)["vpd"].mean()


# -----------------------------------------------------------------------------
#  UTILITIES
# -----------------------------------------------------------------------------

def count_consecutive_days(vpds):
    cnt = 0
    for v in reversed(vpds):
        if v is not None and v > THRESHOLD:
            cnt += 1
        else:
            break
    return cnt


def plot_colored_lines(ax, times, vpds):
    for i in range(len(vpds) - 1):
        x0, x1 = times[i], times[i + 1]
        y0, y1 = vpds[i], vpds[i + 1]
        if y0 <= THRESHOLD and y1 <= THRESHOLD:
            ax.plot([x0, x1], [y0, y1], color="green")
        elif y0 > THRESHOLD and y1 > THRESHOLD:
            ax.plot([x0, x1], [y0, y1], color="red")
        else:
            if y1 != y0:
                t = (THRESHOLD - y0) / (y1 - y0)
                if 0 <= t <= 1:
                    cross = x0 + timedelta(seconds=t * (x1 - x0).total_seconds())
                    if y0 < THRESHOLD:
                        ax.plot([x0, cross], [y0, THRESHOLD], color="green")
                        ax.plot([cross, x1], [THRESHOLD, y1], color="red")
                    else:
                        ax.plot([x0, cross], [y0, THRESHOLD], color="red")
                        ax.plot([cross, x1], [THRESHOLD, y1], color="green")
            else:
                ax.plot([x0, x1], [y0, y1], color="green" if y0 <= THRESHOLD else "red")


def plot_daily_dashed(ax, idxs, vals):
    for i in range(len(idxs) - 1):
        j, k = idxs[i], idxs[i + 1]
        y0, y1 = vals[i], vals[i + 1]
        frac = None if y1 == y0 else (THRESHOLD - y0) / (y1 - y0)
        if y0 <= THRESHOLD and y1 <= THRESHOLD:
            ax.plot([j, k], [y0, y1], "--", lw=2, color="green")
        elif y0 > THRESHOLD and y1 > THRESHOLD:
            ax.plot([j, k], [y0, y1], "--", lw=2, color="red")
        elif frac is not None:
            cross = j + frac * (k - j)
            if y0 < THRESHOLD:
                ax.plot([j, cross], [y0, THRESHOLD], "--", lw=2, color="green")
                ax.plot([cross, k], [THRESHOLD, y1], "--", lw=2, color="red")
            else:
                ax.plot([j, cross], [y0, THRESHOLD], "--", lw=2, color="red")
                ax.plot([cross, k], [THRESHOLD, y1], "--", lw=2, color="green")


def _darken_axes(ax):
    ax.tick_params(colors="white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.grid(color="white", alpha=0.15)
    for spine in ax.spines.values():
        spine.set_color("white")

# -----------------------------------------------------------------------------
#  MAIN APP LOGIC
# -----------------------------------------------------------------------------

st.markdown("<h2 style='text-align:center;font-size:24px;'>London‑wide VPD Monitoring </h2>", unsafe_allow_html=True)

st.markdown(
    "<p style='text-align:center; margin-top:-0.3rem; color:{SUB_COLOUR}; font-size:0.9rem;'>"
    "Data represent the <strong>mean of RAF Northolt, London Heathrow and Kenley Airfield</strong>."
    "</p>",
    unsafe_allow_html=True,
)

#  Date picker
picked = st.date_input(
    "Select day:",
    value=date.today(),
    min_value=date.today() - timedelta(days=HIST_DAYS),
    max_value=date.today() + timedelta(days=MAX_FORECAST_DAYS),
)

#  Context flavour
context = "past" if picked < date.today() else "today" if picked == date.today() else "future"
ACCENT = ACCENT_MAP[context]

#  Daily means for 10‑day window
WINDOW = 10
end_date = picked
start_date = picked - timedelta(days=WINDOW - 1)
window_dates = [start_date + timedelta(days=i) for i in range(WINDOW)]

daily_vals = []
fcst_df = fetch_forecast() if any(d > date.today() for d in window_dates) else pd.DataFrame()
for d in window_dates:
    if d < date.today():
        df = fetch_historical(d)
    elif d == date.today():
        df = fetch_today()
    else:
        if fcst_df.empty:
            df = pd.DataFrame()
        else:
            df = fcst_df[fcst_df["time"].dt.date == d]
    vpd_mean = None if df.empty else df["vpd"].mean()
    daily_vals.append(None if pd.isna(vpd_mean) else vpd_mean)

#  Firewave banner
consec = count_consecutive_days(daily_vals)
col_border, col_bg, banner = ("darkred", "rgba(255,0,0,0.1)", "Firewave Predicted") if consec >= 10 else ("darkgreen", "rgba(0,128,0,0.1)", "No Firewave Predicted")

st.markdown(
    f"""
    <div style='border:1.5px solid {col_border};border-radius:7px;padding:5px;background-color:{col_bg};color:{col_border};font-weight:bold;text-align:center;margin:10px 0;'>
      {banner} – {consec}/10 days above {THRESHOLD} Pa
    </div>
    """,
    unsafe_allow_html=True,
)

#  Hourly data for picked day
if picked > date.today():
    day_df = fcst_df[fcst_df["time"].dt.date == picked]
    title = f"Forecasted Hourly VPD for {picked:%Y-%m-%d}"
elif picked == date.today():
    day_df = fetch_today()
    title = "Hourly VPD Today (station average)"
else:
    day_df = fetch_historical(picked)
    title = f"Hourly VPD on {picked:%Y-%m-%d}"

#  Plot hourly line
st.markdown(f"<div class='section-title' style='color:{ACCENT};'>{title}</div>", unsafe_allow_html=True)
st.caption(f"Viewing data for {picked:%Y-%m-%d}  •  Today is {date.today():%Y-%m-%d}")
if day_df.empty:
    st.warning("No data available for this date.")
else:
    fig, ax = plt.subplots(figsize=(14, 6))
    if dark:
        fig.patch.set_alpha(0)
        _darken_axes(ax)
    ax.set_ylim(1, 3500)

    clean = day_df.dropna().drop_duplicates("time").sort_values("time")
    times, vals = clean["time"].tolist(), clean["vpd"].tolist()
    plot_colored_lines(ax, times, vals)
    ax.scatter(times, vals, c=["#34a853" if v < THRESHOLD else "#ea4335" for v in vals], s=60, linewidths=0.4, edgecolors="#ffffff", zorder=5)
    ax.axhline(THRESHOLD, color="red", linestyle="--")
    ax.set_xlim([datetime.combine(picked, datetime.min.time()), datetime.now() if picked == date.today() else datetime.combine(picked, datetime.max.time())])
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%d/%m"))
    ax.set_xlabel("Time", fontsize=16)
    ax.set_ylabel("VPD (Pa)", fontsize=16)
    st.pyplot(fig)
    #  Download CSV
    st.download_button("📥 Download this day as CSV", clean.to_csv(index=False).encode(), file_name=f"vpd_avg_{picked}.csv", mime="text/csv", use_container_width=True)

#  10‑day dashed plot
st.markdown("<div class='section-title'>Average Daily VPD (Last 10 Days)</div>", unsafe_allow_html=True)
cols = st.columns([2, 1])
with cols[0]:
    fig2, ax2 = plt.subplots(figsize=(10, 6))
    if dark:
        fig2.patch.set_alpha(0)
        _darken_axes(ax2)
    idxs = [i for i, v in enumerate(daily_vals) if v is not None]
    vals = [v for v in daily_vals if v is not None]
    plot_daily_dashed(ax2, idxs, vals)
    for i, v in enumerate(daily_vals):
        if v is None:
            continue
        ax2.scatter(i, v, c="#34a853" if v < THRESHOLD else "#ea4335", s=60, linewidths=0.4, edgecolors="#ffffff", zorder=5)
    ax2.axhline(THRESHOLD, color="red", linestyle="--")
    if start_date <= date.today() <= end_date:
        idx_today = (date.today() - start_date).days
        y_today = daily_vals[idx_today]
        if y_today is not None:
            ax2.vlines(idx_today, y_today, y_today + 40, color=ACCENT, lw=1.5, clip_on=False)
            ax2.text(idx_today, y_today + 45, "Today", ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=ACCENT, lw=1.2), color=ACCENT, fontsize=16)
    ax2.set_xticks(range(WINDOW))
    ax2.set_xticklabels([d.strftime("%d/%m") for d in window_dates])
    ax2.set_xlabel("Day", fontsize=16)
    ax2.set_ylabel("VPD (Pa)", fontsize=16)
    st.pyplot(fig2)
with cols[1]:
    for d, v in zip(window_dates, daily_vals):
        if v is None:
            txt, colour = f"{d:%Y-%m-%d}: No data", "gray"
        else:
            txt, colour = f"{d:%Y-%m-%d}: {v:.1f} Pa", ("green" if v < THRESHOLD else "red")
        st.markdown(f"<div style='color:{colour};font-weight:bold;text-align:center;'>{txt}</div>", unsafe_allow_html=True)

#  Footer
st.markdown(
    f"<div style='border:1.5px solid darkgreen; border-radius:7px; padding:5px; background-color:rgba(0,128,0,0.1); color:darkgreen; font-weight:bold;text-align:center; margin-top:10px;'>"
    f"Data loaded for {start_date} to {end_date}."
    "</div>",
    unsafe_allow_html=True,
)

st.markdown(
    "<div style='font-size:0.8rem; text-align:center; color:grey; margin-top:1.2rem;'>"
    "Built with Streamlit • Data © Met Office / Open‑Meteo / Meteostat"
    "</div>",
    unsafe_allow_html=True,
)
