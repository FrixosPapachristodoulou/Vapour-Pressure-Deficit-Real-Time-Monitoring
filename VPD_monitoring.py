# -*- coding: utf-8 -*- 
"""
Streamlit app for Vapour Pressure Deficit (VPD) Monitoring
- Single-day picker
- Uses Met Office DataPoint API for real-time hourly data on selected day (if today)
- Uses Met Office DataPoint API for 3-hourly forecast on future days
- Uses Open-Meteo Historical API for past 10 days for daily averages
- Falls back to station data via Meteostat for any missing historical hours
- Hourly VPD plot with original plot_colored_lines
- Daily VPD with colored dashed connectors
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
    .section-title:after { content:""; flex:1; margin-left:10px; border-bottom:2px solid #000; }
    .stDateInput label { font-size:18px; font-weight:500; } 
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- global Matplotlib theme ----------
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Inter"],
    "axes.prop_cycle": mpl.cycler(color=["#1a73e8", "#ea4335", "#34a853", "#fbbc05"]),
    "axes.facecolor": "none",
    "figure.facecolor": "none",      # ← new
    "savefig.facecolor": "none",     # ← new
    "axes.labelsize": 14,
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
            all:unset;                     /* wipe Streamlit’s default rules  */
        }

        </style>
        """,
        unsafe_allow_html=True,
    )
    # ── NEW (keep the import line together with the call) ──────────────────
    import matplotlib.colors as _mcol
    _mcol.get_named_colors_mapping()['green'] = '#34c759'   # brighter green
    # ────

# --- Constants ---
LATITUDE = 51.56
LONGITUDE = -0.36
LOCATION_ID = '3672'  # Northolt, London
API_KEY = 'c60bd66f-905f-48d0-885b-b5aa75c436cc'
THRESHOLD = 706
MAX_FORECAST_DAYS = 5
HIST_DAYS = 9

# --- Meteostat station lookup (if available) ---
if METEOSTAT_AVAILABLE:
    stations = Stations().nearby(LATITUDE, LONGITUDE).fetch(3)
    STN_ID = stations.index[0] if not stations.empty else None
    # if STN_ID is not None:
    #    st.write("**Diagnostic: Meteostat station chosen**")
    #    st.write(stations.loc[[STN_ID]][['name','country','region','latitude','longitude','elevation']])
else:
    STN_ID = None

# --- Helper functions ---
def calculate_vpd(temp, hum):
    """Calculate VPD (Pa) from temperature (°C) and relative humidity (%)."""
    esat = 610.7 * 10**(7.5 * temp / (237.3 + temp))
    return esat * (1 - hum/100)


def fetch_met_office_today():
    """Fetch hourly observations for today from Met Office DataPoint - ONLY up to current hour."""
    today = date.today()
    current_time = datetime.now()
    url = f"http://datapoint.metoffice.gov.uk/public/data/val/wxobs/all/json/{LOCATION_ID}?res=hourly&key={API_KEY}"

    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()

        # Navigate to the list of periods
        site_rep = data.get('SiteRep', {})
        dv = site_rep.get('DV', {})
        location = dv.get('Location', {})
        periods = location.get('Period', [])

        records = []
        for period in periods:
            base_str = period.get('value')
            # Parse the date for this period
            try:
                base = datetime.strptime(base_str, "%Y-%m-%dZ")
            except (TypeError, ValueError):
                continue

            for rep in period.get('Rep', []):
                if not isinstance(rep, dict):
                    continue

                # Minute offset from midnight
                minute_offset = int(rep.get('$', 0))
                ts = base + timedelta(minutes=minute_offset)

                # Only include observations for today up to the current time
                if ts.date() != today or ts > current_time:
                    continue

                # Extract temperature and humidity
                t_str = rep.get('T')
                h_str = rep.get('H')
                if t_str is None or h_str is None:
                    continue

                try:
                    t = float(t_str)
                    h = float(h_str)
                except ValueError:
                    continue

                vpd = calculate_vpd(t, h)
                records.append({'time': ts, 'vpd': vpd})

        # Build DataFrame
        df = pd.DataFrame(records)
        return df

    except requests.exceptions.RequestException as e:
        st.error(f"API request failed: {e}")
    except Exception as e:
        st.error(f"Unexpected error: {e}")

    # On error, return empty frame
    return pd.DataFrame(columns=['time', 'vpd'])


def fetch_met_office_forecast():
    """Fetch 3-hourly forecast for future days from Met Office DataPoint."""
    cutoff = date.today() + timedelta(days=MAX_FORECAST_DAYS)
    url = f"http://datapoint.metoffice.gov.uk/public/data/val/wxfcs/all/json/{LOCATION_ID}?res=3hourly&key={API_KEY}"
    
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        
        if not isinstance(data, dict):
            return pd.DataFrame(columns=['time', 'vpd'])
            
        periods = data.get('SiteRep', {}).get('DV', {}).get('Location', {}).get('Period', [])
        if not isinstance(periods, list):
            return pd.DataFrame(columns=['time', 'vpd'])
        
        records = []
        for period in periods:
            if not isinstance(period, dict) or 'value' not in period:
                continue
                
            try:
                base = datetime.strptime(period['value'], "%Y-%m-%dZ")
            except (ValueError, KeyError):
                continue
                
            reps = period.get('Rep', [])
            if not isinstance(reps, list):
                continue
                
            for rep in reps:
                # Check if rep is a dictionary, not a string
                if not isinstance(rep, dict):
                    continue
                    
                try:
                    minute_offset = int(rep.get('$', 0))
                    ts = base + timedelta(minutes=minute_offset)
                    
                    if ts.date() > cutoff:
                        continue
                        
                    temp_str = rep.get('T')
                    hum_str = rep.get('H')
                    
                    if temp_str is None or hum_str is None:
                        continue
                        
                    t, h = float(temp_str), float(hum_str)
                    records.append({'time': ts, 'vpd': calculate_vpd(t, h)})
                    
                except (ValueError, KeyError, TypeError):
                    continue
                    
    except requests.exceptions.RequestException as e:
        st.error(f"Forecast API request failed: {e}")
        return pd.DataFrame(columns=['time', 'vpd'])
    except Exception as e:
        st.error(f"Unexpected forecast error: {e}")
        return pd.DataFrame(columns=['time', 'vpd'])
    
    return pd.DataFrame(records)


def fetch_historical_data(lat, lon, start_date, end_date):
    """Fetch hourly temperature & humidity from Open-Meteo, then compute VPD."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        'latitude': lat,
        'longitude': lon,
        'start_date': start_date,
        'end_date': end_date,
        'hourly': 'temperature_2m,relativehumidity_2m',
        'timezone': 'Europe/London'
    }
    r = requests.get(url, params=params); r.raise_for_status()
    hourly = r.json().get('hourly', {})
    df = pd.DataFrame({
        'time': pd.to_datetime(hourly.get('time', [])),
        'temperature': hourly.get('temperature_2m', []),
        'humidity': hourly.get('relativehumidity_2m', [])
    })
    df['vpd'] = calculate_vpd(df['temperature'], df['humidity'])
    return df


def fill_missing_with_meteostat(df, day):
    """Back‑fill any missing hourly VPD entries for *day* from Meteostat.

    ‣ Always returns a frame where each expected hour has **at most one** row.
    ‣ If an hour exists in both data sources, the Open‑Meteo/Met Office value prevails.
    ‣ Now properly handles NaN VPD values from Open-Meteo as "missing"
    """
    if not METEOSTAT_AVAILABLE or STN_ID is None:
        return df

    start_dt = datetime.combine(day, datetime.min.time())
    end_dt   = datetime.combine(day, datetime.max.time())
    expected = pd.date_range(start_dt, end_dt, freq='H', inclusive='left')

    # Find missing timestamps (either completely absent OR have NaN VPD values)
    if 'time' in df and not df.empty:
        # Get timestamps that are completely missing
        missing_timestamps = expected.difference(df['time'])
        
        # Get timestamps that exist but have NaN VPD values
        nan_timestamps = df[df['vpd'].isna()]['time'] if 'vpd' in df else pd.Index([])
        
        # Combine both types of missing data
        missing = missing_timestamps.union(nan_timestamps)
        
        # Remove rows with NaN VPD from the base dataframe
        base = df[df['vpd'].notna()] if 'vpd' in df else df
    else:
        missing = expected
        base = pd.DataFrame(columns=['time','vpd'])

    if missing.empty:
        return base

    # Fetch Meteostat data for the entire day
    try:
        station_df = Hourly(STN_ID, start_dt, end_dt).fetch().reset_index()
        station_df = station_df.rename(columns={'temp':'temperature','rhum':'humidity'})
        station_df['time'] = pd.to_datetime(station_df['time']).dt.tz_localize(None)
        station_df['vpd']  = calculate_vpd(station_df['temperature'], station_df['humidity'])

        # Get rows that match the missing hours only
        fill = station_df[station_df['time'].isin(missing)][['time','vpd']]

        # Drop any NaN VPD values coming from Meteostat
        fill = fill.dropna(subset=['vpd'])
    except Exception as e:
        print(f"Error fetching Meteostat data: {e}")
        fill = pd.DataFrame(columns=['time','vpd'])

    # Combine base data (non-NaN Open-Meteo) with Meteostat fill data
    df_filled = (pd.concat([base, fill], ignore_index=True)
                   .drop_duplicates('time', keep='first')
                   .sort_values('time')
                   .reset_index(drop=True))

    return df_filled

def count_consecutive_days(vpds):
    cnt = 0
    for v in reversed(vpds):
        if v is not None and v > THRESHOLD: cnt += 1
        else: break
    return cnt


def plot_colored_lines(ax, times, vpds):
    for i in range(len(vpds)-1):
        x0, x1 = times[i], times[i+1]
        y0, y1 = vpds[i], vpds[i+1]
        try:
            slope = (y1 - y0) / (x1.timestamp() - x0.timestamp())
            intercept = y0 - slope * x0.timestamp()
            cross = datetime.fromtimestamp((THRESHOLD - intercept) / slope)
            if y0 <= THRESHOLD and y1 <= THRESHOLD:
                ax.plot([x0, x1], [y0, y1], color='green')
            elif y0 > THRESHOLD and y1 > THRESHOLD:
                ax.plot([x0, x1], [y0, y1], color='red')
            else:
                if y0 < THRESHOLD:
                    ax.plot([x0, cross], [y0, THRESHOLD], color='green')
                    ax.plot([cross, x1], [THRESHOLD, y1], color='red')
                else:
                    ax.plot([x0, cross], [y0, THRESHOLD], color='red')
                    ax.plot([cross, x1], [THRESHOLD, y1], color='green')
        except:
            pass


def plot_daily_dashed(ax, idxs, vals):
    for i in range(len(idxs)-1):
        j, k = idxs[i], idxs[i+1]
        y0, y1 = vals[i], vals[i+1]
        try:
            frac = (THRESHOLD - y0) / (y1 - y0)
        except:
            frac = None
        if y0 <= THRESHOLD and y1 <= THRESHOLD:
            ax.plot([j, k], [y0, y1], '--', linewidth=2, color='green')
        elif y0 > THRESHOLD and y1 > THRESHOLD:
            ax.plot([j, k], [y0, y1], '--', linewidth=2, color='red')
        elif frac is not None:
            cross = j + frac * (k - j)
            if y0 < THRESHOLD:
                ax.plot([j, cross], [y0, THRESHOLD], '--', linewidth=2, color='green')
                ax.plot([cross, k], [THRESHOLD, y1], '--', linewidth=2, color='red')
            else:
                ax.plot([j, cross], [y0, THRESHOLD], '--', linewidth=2, color='red')
                ax.plot([cross, k], [THRESHOLD, y1], '--', linewidth=2, color='green')

# --- App UI ---
st.markdown("<h2 style='text-align:center;font-size:24px;'>Vapour Pressure Deficit Monitoring</h2>", unsafe_allow_html=True)

st.markdown(
    "<p style='text-align:center; margin-top:-0.3rem; color:#5f6368; "
    "font-size:0.9rem;'>"
    "All figures relate to <b>Greater London (Northolt synoptic site, "
    "51.56 °N, 0.36 °W)</b>. Values elsewhere will differ."
    "</p>",
    unsafe_allow_html=True,
)


# Date picker
day_sel = st.date_input(
    'Select day:',
    value=date.today(),
    min_value=date.today() - timedelta(days=HIST_DAYS),
    max_value=date.today() + timedelta(days=MAX_FORECAST_DAYS),
    key='main_day_picker'
)
start = day_sel - timedelta(days=HIST_DAYS)
end   = day_sel





# ---- DAILY-MEAN VPD FOR A 10-DAY WINDOW ENDING ON *day_sel* ----
WINDOW = 10
rng = [day_sel - timedelta(days=i) for i in range(WINDOW - 1, -1, -1)]  # oldest → newest

# # Pull forecast once (only if the window reaches into the future)
# forecast_df = (
#     fetch_met_office_forecast()
#     if max(rng) > date.today()
#     else pd.DataFrame(columns=["time", "vpd"])
# )
# if not forecast_df.empty:
#     forecast_df["time"] = pd.to_datetime(forecast_df["time"])
#     forecast_df["day"]  = forecast_df["time"].dt.date


# Pull the 3-hour forecast once (only if the window reaches into the future)
forecast_df = (
    fetch_met_office_forecast()
    if max(rng) > date.today()
    else pd.DataFrame(columns=["time", "vpd"])
)

# Always create the helper columns, even for an empty frame
# forecast_df["time"] = pd.to_datetime(forecast_df.get("time"), errors="coerce")
# forecast_df["day"]  = forecast_df["time"].dt.date

# make sure the column exists and is datetime64               <— NEW
if "time" not in forecast_df.columns:
    forecast_df["time"] = pd.Series(dtype="datetime64[ns]")

forecast_df["time"] = pd.to_datetime(forecast_df["time"], errors="coerce")
forecast_df["day"]  = forecast_df["time"].dt.date

today_ = date.today()
forecast_df = forecast_df[forecast_df["day"] > today_]

# --- NEW: guarantee the forecast frame always has a vpd column -------------
if "vpd" not in forecast_df.columns:
    forecast_df["vpd"] = pd.Series(dtype="float64")
# ---------------------------------------------------------------------------

forecast_means = (
    forecast_df.groupby("day")["vpd"].mean()   # safe now: vpd always exists
    .dropna()                                  # remove NaNs if any
    .to_dict()
)



def mean_vpd_for_day(d: date) -> float | None:
    """Return the daily-mean VPD for *d*, or None if we really have no data."""
    if d < date.today():                                # ← past
        df = fetch_historical_data(LATITUDE, LONGITUDE, d.isoformat(), d.isoformat())
        df = fill_missing_with_meteostat(df, d)
        return None if df.empty else df["vpd"].mean()

    if d == date.today():                               # ← today
        df = fetch_met_office_today()
        df = fill_missing_with_meteostat(df, d)
        return None if df.empty else df["vpd"].mean()

    # ---------- future days ----------
    # Slice the forecast we already have:
    # slice_ = forecast_df[forecast_df["day"] == d]
    # return None if slice_.empty else slice_["vpd"].mean()

    # ---------- future days ----------
    
    
    # ---------- future days ----------
    # 1) fast path – use the dictionary we just built
    if d in forecast_means:
        return forecast_means[d]

    # 2) slow path – slice the one-shot forecast dataframe
    slice_ = forecast_df[forecast_df["day"] == d]
    if not slice_.empty:
        val = slice_["vpd"].mean()
        return None if pd.isna(val) else val

    # 3) last-resort – pull the forecast again (rare)
    fresh = fetch_met_office_forecast()
    if not fresh.empty:
        fresh["time"] = pd.to_datetime(fresh["time"], errors="coerce")
        fresh["day"]  = fresh["time"].dt.date
        val = fresh[fresh["day"] == d]["vpd"].mean()
        return None if pd.isna(val) else val

    return None


def _darken_axes(ax):
    """Paint axes, ticks and grid white so they pop on a dark canvas."""
    ax.tick_params(colors="white", which="both")            # ticks
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.grid(color="white", alpha=0.15)                      # gridlines
    # 4 spines
    for spine in ax.spines.values():
        spine.set_color("white")


# Build the 10-element list, oldest → newest
avg   = [mean_vpd_for_day(d) for d in rng]
consec = count_consecutive_days(avg)

bc, bb, bt = (
    ("darkred",  "rgba(255,0,0,0.1)", "Firewave Predicted")
    if consec >= 10 else
    ("darkgreen","rgba(0,128,0,0.1)", "No Firewave Predicted")
)

st.markdown(
    f"""
    <div style='border:1.5px solid {bc};border-radius:7px;padding:5px;background-color:{bb};color:{bc};
               font-weight:bold;text-align:center;margin:10px 0;'>
      {bt} – {consec}/10 days above {THRESHOLD} Pa
    </div>
    """,
    unsafe_allow_html=True,
)


# --- Hourly VPD ---
if day_sel > date.today():
    df_today = fetch_met_office_forecast()
    df_today = df_today[ df_today["time"].dt.date == day_sel ]   # ← NEW
    title    = f"Forecasted Hourly VPD for {day_sel:%Y-%m-%d}"
elif day_sel == date.today():
    df_today = fetch_met_office_today()
    title    = "Hourly VPD Today"
else:
    # Only fetch historical data for past dates
    try:
        df_raw = fetch_historical_data(LATITUDE, LONGITUDE, day_sel.isoformat(), day_sel.isoformat())
        df_today = df_raw[df_raw['time'].dt.date == day_sel]
        title = f"Hourly VPD on {day_sel:%Y-%m-%d}"
    except requests.exceptions.HTTPError as e:
        st.error(f"Error fetching historical data: {e}")
        df_today = pd.DataFrame(columns=['time','vpd'])
        title = f"Hourly VPD on {day_sel:%Y-%m-%d} (No Data Available)"

df_open = df_today.copy()

# Fill missing hours via Meteostat
filled = fill_missing_with_meteostat(df_open, day_sel)

# NEW: for *today* keep only data points up to the current time
if day_sel == date.today():
    now = datetime.now()
    filled = filled[filled["time"] <= now]

# Determine which rows came from Meteostat
# --- Show full Meteostat pull regardless of what was filled ---
if METEOSTAT_AVAILABLE and STN_ID is not None:
    start_dt = datetime.combine(day_sel, datetime.min.time())
    end_dt   = datetime.combine(day_sel, datetime.max.time())
    raw_meteo = Hourly(STN_ID, start_dt, end_dt).fetch().reset_index()
    raw_meteo = raw_meteo.rename(columns={'temp':'temperature','rhum':'humidity'})


# Identify which rows were actually used for back‑filling
if not filled.empty and 'time' in filled.columns and not df_open.empty and 'time' in df_open.columns:
    _df_fill_marker = filled[~filled['time'].isin(df_open['time'])]
elif not filled.empty and 'time' in filled.columns and (df_open.empty or 'time' not in df_open.columns):
    # All filled data is from Meteostat since df_open is empty or has no time column
    _df_fill_marker = filled.copy()
else:
    # No filled data or no time column
    _df_fill_marker = pd.DataFrame(columns=['time','vpd'])


# Keep original variable name if further code relies on it
df_fill = _df_fill_marker

# Use filled DataFrame for plotting
df_today = filled




# Plot hourly full-width
st.markdown(f"<div class='section-title'>{title}</div>", unsafe_allow_html=True)
if df_today.empty or 'time' not in df_today.columns or 'vpd' not in df_today.columns:
    st.warning('Not enough data for selected day.')
else:
    fig, ax = plt.subplots(figsize=(14,6))
    if dark:                       # new  ➜ only in dark-mode
        fig.patch.set_alpha(0)     # make hourly-plot canvas transparent
        _darken_axes(ax)
    ax.set_ylim(0, 3500)
    times = list(df_today['time'])
    vals  = list(df_today['vpd'])
    plot_colored_lines(ax, times, vals)
    ax.scatter(times, vals, c=[('#34a853' if v < THRESHOLD else '#ea4335') for v in vals], s=60, linewidths=0.4, edgecolors="#ffffff", zorder=5)
    ax.axhline(THRESHOLD, color='red', linestyle='--')

    if day_sel == date.today():                 # today → stop at current time
        ax.set_xlim([datetime.combine(day_sel, datetime.min.time()),
                     datetime.now()])
    else:                                       # any other day → full 24 h
        ax.set_xlim([datetime.combine(day_sel, datetime.min.time()),
                     datetime.combine(day_sel, datetime.max.time())])

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M\n%d/%m'))
    ax.set_xlabel('Time'); ax.set_ylabel('VPD (Pa)'); ax.grid(True)
    st.pyplot(fig)


if not df_today.empty:
    csv_bytes = df_today.to_csv(index=False).encode()
    st.download_button(
        "📥  Download this day as CSV",
        csv_bytes,
        file_name=f"vpd_{day_sel}.csv",
        mime="text/csv",
        help="Export the filled hourly VPD table for the selected day",
        use_container_width=True,          # ← NEW: full-width like the charts
    )
    
# --- Daily VPD ---
st.markdown("<div class='section-title'>Average Daily VPD (Last 10 Days)</div>", unsafe_allow_html=True)
col3, col4 = st.columns([2,1])
with col3:
    fig2, ax2 = plt.subplots(figsize=(10,6))
    if dark:                       # new  ➜ only in dark-mode
        fig2.patch.set_alpha(0)    # make 10-day plot canvas transparent
        _darken_axes(ax2)
    # idxs = [i for i, v in enumerate(avg) if v is not None]
    # vals = [v for v in avg if v is not None]

    idxs = [i for i, v in enumerate(avg) if v is not None and not pd.isna(v)]
    vals = [v for v in avg if v is not None and not pd.isna(v)]

    plot_daily_dashed(ax2, idxs, vals)
    for i, v in enumerate(avg):
        if v is None: continue
        ax2.scatter(i, v, s=60, c=('#34a853' if v < THRESHOLD else '#ea4335'), linewidths=0.4, edgecolors="#ffffff", zorder=5)
    ax2.axhline(THRESHOLD, color='red', linestyle='--')
    ax2.set_xticks(range(len(avg)))
    ax2.set_xticklabels([d.strftime('%d/%m') for d in pd.date_range(start, end)], rotation=0)
    ax2.set_xlabel('Day'); ax2.set_ylabel('VPD (Pa)'); ax2.grid(True)
    st.pyplot(fig2)
with col4:
    for d, v in zip(pd.date_range(start, end), avg):
        if v is None or pd.isna(v):
            label = f"{d:%Y-%m-%d}: No data"
            color = "gray"
        else:
            label = f"{d:%Y-%m-%d}: {v:.1f} Pa"
            color = "green" if v < THRESHOLD else "red"
        st.markdown(
            f"<div style='color:{color};font-weight:bold;text-align:center;'>{label}</div>",
            unsafe_allow_html=True,
        )


# Footer
st.markdown(
    f"<div style='border:1.5px solid darkgreen; border-radius:7px; padding:5px; background-color:rgba(0,128,0,0.1); color:darkgreen; font-weight:bold;text-align:center; margin-top:10px;'>"
    f"Data loaded for {start} to {end}." 
    "</div>",
    unsafe_allow_html=True
)

st.markdown(
    "<div style='font-size:0.8rem; text-align:center; color:grey; "
    "margin-top:1.2rem;'>"
    "Regional scope: VPD derived for the Northolt station &mdash; representative "
    "of London’s climate.</div>",
    unsafe_allow_html=True,
)


st.markdown(
    '<hr style="margin-top:3rem;">'
    '<div style="font-size:0.8rem;text-align:center;color:grey">'
    'Built with Streamlit • Data © Met Office / Open-Meteo / Meteostat'
    '</div>',
    unsafe_allow_html=True,
)
