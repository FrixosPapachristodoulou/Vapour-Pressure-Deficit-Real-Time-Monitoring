# -*- coding: utf-8 -*-
"""
Streamlit app for Vapour Pressure Deficit (VPD) Monitoring
- Single-day picker
- Uses Met Office DataPoint API for real-time hourly data on selected day (if today)
- Uses Open-Meteo Historical API for past 10 days for daily averages
- Hourly VPD plot with original plot_colored_lines
- Daily VPD with colored dashed connectors
"""
import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta, date

# --- CSS Styling ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');
html, body, [class*="css"] { font-family: 'Roboto', sans-serif; }
.section-title { font-size:18px; font-weight:bold; text-align:left; padding-bottom:3px; margin-bottom:0; display:flex; align-items:center; }
.section-title:after { content:""; flex:1; margin-left:10px; border-bottom:2px solid #000; }
</style>
""", unsafe_allow_html=True)

# --- Constants ---
LATITUDE = 51.56
LONGITUDE = -0.36
LOCATION_ID = '3672'  # Northolt
API_KEY = 'c60bd66f-905f-48d0-885b-b5aa75c436cc'
THRESHOLD = 706

# --- Helper functions ---
def fetch_met_office_today():
    """Fetch last 24h hourly obs from Met Office DataPoint."""
    url = f"http://datapoint.metoffice.gov.uk/public/data/val/wxobs/all/json/{LOCATION_ID}?res=hourly&key={API_KEY}"
    resp = requests.get(url)
    resp.raise_for_status()
    data = resp.json()
    period = data['SiteRep']['DV']['Location']['Period'][0]
    base_date = datetime.strptime(period['value'], "%Y-%m-%dZ")
    records = []
    for rep in period['Rep']:
        minutes = int(rep['$'])
        ts = base_date + timedelta(minutes=minutes)
        try:
            t = float(rep['T'])
            h = float(rep['H'])
            v = calculate_vpd(t, h)
            records.append({'time': ts, 'vpd': v})
        except:
            continue
    return pd.DataFrame(records)


def fetch_historical_data(lat, lon, start_date, end_date):
    """Fetch hourly temp & humidity, then compute VPD"""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        'latitude': lat, 'longitude': lon,
        'start_date': start_date, 'end_date': end_date,
        'hourly': 'temperature_2m,relative_humidity_2m',
        'timezone': 'Europe/London'
    }
    r = requests.get(url, params=params)
    r.raise_for_status()
    d = r.json()['hourly']
    df = pd.DataFrame({
        'time': pd.to_datetime(d['time']),
        'temperature': d['temperature_2m'],
        'humidity': d['relative_humidity_2m']
    })
    df['vpd'] = calculate_vpd(df.temperature, df.humidity)
    return df


def calculate_vpd(temp, hum):
    esat = 610.7 * 10**(7.5 * temp/(237.3 + temp))
    return esat * (1 - hum/100)


def count_consecutive_days(vpds):
    cnt = 0
    for v in reversed(vpds):
        if v is not None and v > THRESHOLD:
            cnt += 1
        else:
            break
    return cnt


def plot_colored_lines(ax, timestamps, vpd_values):
    for i in range(len(vpd_values) - 1):
        x = [timestamps[i], timestamps[i + 1]]
        y = [vpd_values[i], vpd_values[i + 1]]

        if not all(isinstance(t, datetime) for t in x):
            continue
        if not all(isinstance(v, (float, int)) for v in y):
            continue

        try:
            slope = (y[1] - y[0]) / (x[1].timestamp() - x[0].timestamp())
            intercept = y[0] - slope * x[0].timestamp()
            crossing_x = (THRESHOLD - intercept) / slope
            crossing_time = datetime.fromtimestamp(crossing_x)

            if y[0] <= THRESHOLD and y[1] <= THRESHOLD:
                ax.plot(x, y, color='green')
            elif y[0] > THRESHOLD and y[1] > THRESHOLD:
                ax.plot(x, y, color='red')
            else:
                if y[0] < THRESHOLD:
                    ax.plot([x[0], crossing_time], [y[0], THRESHOLD], color='green')
                    ax.plot([crossing_time, x[1]], [THRESHOLD, y[1]], color='red')
                else:
                    ax.plot([x[0], crossing_time], [y[0], THRESHOLD], color='red')
                    ax.plot([crossing_time, x[1]], [THRESHOLD, y[1]], color='green')
        except Exception:
            continue


def plot_daily_dashed(ax, idxs, vals):
    for i in range(len(idxs)-1):
        j,k=idxs[i],idxs[i+1]
        y0,y1=vals[i],vals[i+1]
        if y0<=THRESHOLD and y1<=THRESHOLD:
            ax.plot([j,k],[y0,y1],linestyle='--',linewidth=2,color='green')
        elif y0>THRESHOLD and y1>THRESHOLD:
            ax.plot([j,k],[y0,y1],linestyle='--',linewidth=2,color='red')
        else:
            frac=(THRESHOLD-y0)/(y1-y0)
            xcross=j+frac*(k-j)
            if y0<THRESHOLD:
                ax.plot([j,xcross],[y0,THRESHOLD],linestyle='--',linewidth=2,color='green')
                ax.plot([xcross,k],[THRESHOLD,y1],linestyle='--',linewidth=2,color='red')
            else:
                ax.plot([j,xcross],[y0,THRESHOLD],linestyle='--',linewidth=2,color='red')
                ax.plot([xcross,k],[THRESHOLD,y1],linestyle='--',linewidth=2,color='green')

# --- App ---
st.markdown("<h2 style='text-align:center;font-size:24px;'>Vapour Pressure Deficit (VPD) Monitoring</h2>", unsafe_allow_html=True)
# Select day
day_sel = st.date_input('Select day:', value=date.today(), max_value=date.today())
start = day_sel - timedelta(days=9)
end = day_sel

# Fetch historical for averages
df_hist = fetch_historical_data(LATITUDE, LONGITUDE, start.isoformat(), end.isoformat())
daily = df_hist.set_index('time')['vpd'].resample('D').mean().reindex(pd.date_range(start, end), fill_value=None)
avg = [None if pd.isna(x) else x for x in daily]
consec = count_consecutive_days(avg)

# Firewave banner (previous style)
if consec >= 10:
    st.markdown(
        f"""
        <div style="
            border: 1px solid darkred;
            border-radius: 5px;
            padding: 5px;
            background-color: rgba(255, 0, 0, 0.1);
            color: darkred;
            font-weight: bold;
            text-align: center;
            margin-bottom: 10px;">
            Firewave Predicted - Consecutive Days with VPD Above {THRESHOLD} Pa: {consec}/10
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    st.markdown(
        f"""
        <div style="
            border: 1px solid darkgreen;
            border-radius: 5px;
            padding: 5px;
            background-color: rgba(0, 128, 0, 0.1);
            color: darkgreen;
            font-weight: bold;
            text-align: center;
            margin-bottom: 10px;">
            No Firewave Predicted - Consecutive Days with VPD Above {THRESHOLD} Pa: {consec}/10
        </div>
        """,
        unsafe_allow_html=True
    )

# Today section
st.markdown("<div class='section-title'>Today</div>", unsafe_allow_html=True)
col1, col2 = st.columns([2, 1])
# Choose source
if day_sel == date.today():
    df_today = fetch_met_office_today()
else:
    df_today = df_hist[df_hist.time.dt.date == day_sel]
df_today = df_today.dropna(subset=['vpd'])

with col1:
    if df_today.empty:
        st.warning('Not enough data for selected day.')
    else:
        fig, ax = plt.subplots(figsize=(10,6))
        ax.set_ylim(0, 2500)
        timestamps = list(df_today.time)
        vpd_vals = list(df_today.vpd)
        plot_colored_lines(ax, timestamps, vpd_vals)
        ax.axhline(THRESHOLD, color='red', linestyle='--', linewidth=1.5)
        ax.set_xlim([
            datetime.combine(day_sel, datetime.min.time()),
            datetime.combine(day_sel, datetime.max.time())
        ])
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M\n(%d/%m)'))
        ax.set_xlabel('Time')
        ax.set_ylabel('VPD (Pa)')
        ax.set_title(f'Hourly VPD on {day_sel}')
        ax.grid(True)
        plt.xticks(rotation=0)
        st.pyplot(fig)

with col2:
    st.markdown("<h3 style='text-align:center;'>Last 10 Hours</h3>", unsafe_allow_html=True)
    last10 = df_today.sort_values('time', ascending=False).head(10)
    for _, row in last10.iterrows():
        ts = row['time'].strftime('%H:%M (%d/%m)')
        color = 'green' if row['vpd'] < THRESHOLD else 'red'
        st.markdown(
            f"<div style='color: {color}; font-weight:bold; text-align:center;'>{ts}: {row['vpd']:.2f} Pa</div>",
            unsafe_allow_html=True
        )

# Last 10 Days section
st.markdown("<div class='section-title'>Last 10 Days</div>", unsafe_allow_html=True)
col3, col4 = st.columns([2, 1])
with col3:
    fig2, ax2 = plt.subplots(figsize=(10,6))
    idxs = [i for i, v in enumerate(avg) if v is not None]
    vals = [v for v in avg if v is not None]
    plot_daily_dashed(ax2, idxs, vals)
    for i, v in enumerate(avg):
        if v is None:
            continue
        col = 'green' if v < THRESHOLD else 'red'
        ax2.scatter(i, v, marker='o', s=50, color=col)
    ax2.axhline(THRESHOLD, color='red', linestyle='--', linewidth=1.5)
    ax2.set_xticks(range(len(daily)))
    ax2.set_xticklabels([d.strftime('%d/%m') for d in daily.index], rotation=0)
    ax2.set_xlabel('Day')
    ax2.set_ylabel('Avg VPD (Pa)')
    ax2.set_title('Average Daily VPD Over the Last 10 Days')
    ax2.grid(True)
    st.pyplot(fig2)

with col4:
    st.markdown("<h3 style='text-align:center;'>Average Daily VPD</h3>", unsafe_allow_html=True)
    for d, v in zip(daily.index, avg):
        if v is None:
            st.markdown(f"<div style='color:gray; font-weight:bold; text-align:center;'>{d.strftime('%Y-%m-%d')}: No data fetched</div>", unsafe_allow_html=True)
        else:
            col = 'green' if v < THRESHOLD else 'red'
            st.markdown(f"<div style='color:{col}; font-weight:bold; text-align:center;'>{d.strftime('%Y-%m-%d')}: {v:.2f} Pa</div>", unsafe_allow_html=True)

# Status footer
st.markdown(
    f"""
    <div style="
        border: 1px solid darkgreen;
        border-radius: 5px;
        padding: 5px;
        background-color: rgba(0, 128, 0, 0.1);
        color: darkgreen;
        font-weight: bold;
        text-align: center;
        margin-top: 10px;">
        Data loaded for {start} to {end}.
    </div>
    """,
    unsafe_allow_html=True
)

