# -*- coding: utf-8 -*-
"""
Streamlit app – London‑wide Vapour Pressure Deficit (VPD) monitor
================================================================

Data sources remain Met Office DataPoint, Open‑Meteo and Meteostat.
Updated to use ALL available London stations for comprehensive coverage.
Enhanced with comprehensive loading indicators for better UX.
"""
import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta, date
import matplotlib as mpl
import time          # <-- add this
from datetime import datetime, timedelta, date

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
ACCENT = "#34a853"  # Define early
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

st.markdown(
    """
    <style>
    /* crude but effective “zoom” */
    html {               /* all major browsers except Firefox */
        zoom: 105%;      /* 100 % → normal, 120 % → 1.2× bigger */
    }
    /* Firefox fallback: use a transform */
    @-moz-document url-prefix() {
        html {           /* keep origin top-left so scroll bars behave */
            transform: scale(1.05);
            transform-origin: 0 0;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


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
#  Accent colours choose blue / green / amber based on past / today / future
ACCENT_MAP = {"past": "#0e62a7", "today": "#34a853", "future": "#aa6805"}

# hard-wired values now that the controls are gone
run_diag          = False      # diagnostic panel off
min_stations      = 2          # keep the old default
show_station_count = True      # still include the column
dev_mode          = False      # no raw-frame dump


# ──────────────────────────────────────────────────────────────────────────────
#  CONSTANTS & STATION META
# ──────────────────────────────────────────────────────────────────────────────
API_KEY = "c60bd66f-905f-48d0-885b-b5aa75c436cc"  # Met Office DataPoint key
THRESHOLD = 706                                   # Pa threshold for Firewave
MAX_FORECAST_DAYS = 5
HIST_DAYS = 9

#  Meteostat optional import
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




# ---------------------------------------------------------------------------
#  1. Borough list — add the City of London for completeness
# ---------------------------------------------------------------------------
LONDON_BOROUGHS = [
    "City of London",                # NEW
    "Barking and Dagenham", "Barnet", "Bexley", "Brent", "Bromley",
    "Camden", "Croydon", "Ealing", "Enfield", "Greenwich", "Hackney",
    "Hammersmith and Fulham", "Haringey", "Harrow", "Havering",
    "Hillingdon", "Hounslow", "Islington", "Kensington and Chelsea",
    "Kingston upon Thames", "Lambeth", "Lewisham", "Merton", "Newham",
    "Redbridge", "Richmond upon Thames", "Southwark", "Sutton",
    "Tower Hamlets", "Waltham Forest", "Wandsworth", "Westminster",
]

# ---------------------------------------------------------------------
# 🚀  Hard-wired London station catalogue (142 sites)
#      – parsed once from the multiline string below –
# ---------------------------------------------------------------------
import io, csv, textwrap

_STATION_TSV = textwrap.dedent("""\
    Name	MetOffice dp_id	Latitude	Longitude	Meteostat ID
    Addlestone	350036	51.3689	-0.4886	3772
    All England Tennis Club Wimbledon	324383	51.4337	-0.2141	3779
    Arsenal F.C.	350150	51.5535	-0.1033	3779
    Banstead	350240	51.3217	-0.2035	3781
    Barking	324164	51.53926	0.081146	3781
    Barnet	324151	51.6528	-0.1991	3781
    Beckton	350286	51.5145	0.0582	3781
    Bexley	350413	51.4414	0.1487	3781
    Biggin Hill	350426	51.3116	0.0344	3781
    Borehamwood	350516	51.6573	-0.2707	3781
    Brands Hatch	350571	51.3554	0.2636	3781
    Bromley (Greater London)	350635	51.4056	0.0148	3781
    Bromley Ski Centre	350638	51.405	0.1278	3781
    Bushey	350694	51.6472	-0.3569	3781
    Camden Town	350734	51.5392	-0.1425	3779
    Capel Manor	350752	51.6779	-0.0562	3779
    Charlton Athletic F.C.	350868	51.4862	0.042	3779
    Chelsea	350881	51.4847	-0.1752	3779
    Chelsea F.C.	350882	51.4816	-0.1918	3779
    Chertsey	350886	51.3866	-0.5082	3772
    Chessington World Of Adventures	350890	51.3466	-0.3221	3781
    Chigwell	350898	51.6258	0.0823	3781
    City Of London	350928	51.5102	-0.0837	3779
    City Of London Youth Hostel	350929	51.5103	-0.0969	3779
    Claremont Landscape Garden	350934	51.3554	-0.3741	3772
    Cobham	350969	51.3284	-0.4078	3772
    Croydon	324152	51.3775	-0.0933	3781
    Crystal Palace F.C.	351118	51.3971	-0.0848	3781
    Crystal Palace National Sports Centre	351119	51.4213	-0.0702	3779
    Dagenham	351142	51.54	0.1478	3779
    Dartford	351167	51.4457	0.2185	3779
    Down House	351234	51.3295	0.0487	3779
    Ealing	351297	51.5117	-0.3023	3672
    Earl's Court Youth Hostel	351301	51.4917	-0.1833	3779
    Earls Court	354376	51.4881	-0.1996	3779
    Enfield	351387	51.654	-0.0814	3779
    Epping Forest Youth Hostel	351390	51.6668	0.0323	3779
    Epsom	351391	51.3356	-0.2658	3781
    Epsom Downs Racecourse	351392	51.307	-0.2518	3781
    Esher	351401	51.3686	-0.3635	3772
    Ewell	351409	51.3507	-0.2513	3781
    Excel	354377	51.509	-0.029	3779
    Fenton House	351456	51.5623	-0.1824	3779
    Fulham	351525	51.4789	-0.1995	3779
    Fulham F.C.	351527	51.4731	-0.2175	3779
    Garston	322216	51.68	-0.38	3779
    Greenwich	351683	51.4779	-0.01	3779
    Greenwich Park	352533	51.477	0.004	3779
    Hackney	351713	51.5458	-0.0549	3779
    Hammersmith	351743	51.49	-0.2256	3779
    Hampstead	99139	51.56	-0.178	3779
    Hampstead Heath Youth Hostel	351746	51.5705	-0.1797	3779
    Hampton Court Palace	351747	51.4007	-0.3337	3772
    Hampton W Wks	371494	51.41194	-0.3781	3772
    Harringay	351763	51.582	-0.1027	3779
    Harrow	351771	51.5801	-0.3404	3672
    Hayes	322281	51.5	-0.42	3772
    Heathrow	3772	51.479	-0.449	3772
    Hillingdon	351897	51.5334	-0.4527	3672
    Holland House Youth Hostel	351918	51.502	-0.1998	3779
    Horseguards Parade	324386	51.5047	-0.1283	3779
    Hounslow	351956	51.4655	-0.3605	3772
    Hyde Park	324387	51.5077	-0.165	3779
    Ilford	351996	51.5562	0.0779	3779
    Islington	352036	51.5353	-0.102	3779
    Kempton Park Racecourse	352068	51.4182	-0.3963	3772
    Kemsing	352069	51.3067	0.2503	3772
    Kenley	3781	51.303	-0.09	3781
    Kensington	352075	51.5015	-0.1962	3779
    Kew Gardens	99095	51.482	-0.29	3772
    Kingston Upon Thames	324153	51.4119	-0.2991	3772
    Lambeth	352196	51.4922	-0.1178	3779
    Leatherhead	324199	51.2916	-0.3241	3781
    Lewisham	352275	51.463	-0.0076	3781
    London	352409	51.5081	-0.1248	3779
    London  Olympic Park North	99204	51.542	-0.017	3779
    London Ashford Airport	352410	50.9516	0.9454	3882
    London Biggin Hill Airport	352411	51.3264	0.0322	3882
    London City Airport	5	51.5048	0.058	3882
    London Fields	352413	52.5133	-2.1112	3416
    London Gatwick Airport	352414	51.1511	-0.1768	3776
    London Luton Airport	352416	51.8746	-0.3708	3673
    London Southend Airport	352417	51.5696	0.6955	3691
    London Stansted Airport	352418	51.8832	0.2434	3683
    Londonderry (Derry)	322472	54.9952	-7.3227	3683
    Londonderry (West Midlands)	352419	52.4857	-1.9842	3534
    Londonolympic Park South	99203	51.534	-0.009	3779
    Lord's Marylebone C.C.	352438	51.5294	-0.1728	3779
    Loughton	352448	51.6555	0.0698	3779
    Merton	352613	51.4152	-0.1857	3779
    Millwall F.C.	354363	51.48593	-0.05096	3779
    Morden Hall Park	352677	51.4004	-0.1889	3781
    Myddelton House	352731	51.675	-0.0662	3779
    New Addington	352758	51.3494	-0.0142	3779
    Northolt	3672	51.548	-0.415	3672
    Northwood	3670	51.6169	-0.4	3672
    Orpington	352912	51.3744	0.0958	3672
    Osterley Park	352918	51.4883	-0.3497	3772
    Oxford Street Youth Hostel	352932	51.5149	-0.1367	3779
    Qpr F.C.	354365	51.50927	-0.23218	3779
    R.H.S. Garden Wisley	353144	51.3158	-0.4719	3772
    Radlett	353148	51.6864	-0.3158	3772
    Richmond (Greater London)	353202	51.4609	-0.3022	3772
    Rickmansworth	353207	51.6383	-0.4726	3772
    Robert Fitzroy Academy	355869	51.38651	-0.08205	3781
    Romford	353233	51.5766	0.1799	3781
    Rotherhithe Youth Hostel	353241	51.5033	-0.0357	3779
    Royal Botanic Gardens Kew	353260	51.4743	-0.3009	3772
    Rugby Football Union Twickenham	353279	51.4567	-0.3409	3772
    Sandown Active Sports	353356	51.3744	-0.3582	3772
    Sandown Park Racecourse	353358	51.3741	-0.3638	3772
    Southwark	353605	51.504	-0.1052	3779
    St Pancras Youth Hostel	353331	51.525	-0.1257	3779
    Stepney	353669	51.5175	-0.044	3779
    Sunbury	353766	51.4046	-0.4109	3772
    Sutton	353773	51.3617	-0.1923	3781
    Swanley	353788	51.3969	0.1782	3781
    Syon House	353800	51.4749	-0.3149	3772
    The Mall	354379	51.505	-0.132	3779
    The O2	354378	51.503	0.003	3779
    The Oval Surrey C.C.C.	353846	51.4846	-0.1164	3779
    The Royal Artillery Barracks	324382	51.486	0.062	3779
    Tottenham Hotspur F.C.	353961	51.605	-0.0619	3779
    Uxbridge	354040	51.5481	-0.4781	3672
    Waltham Abbey	354070	51.6846	0.0043	3779
    Walthamstow	354071	51.5901	-0.0198	3779
    Walton-On-Thames	354074	51.3875	-0.4152	3772
    Wandsworth	354075	51.4571	-0.2044	3779
    Warlingham	354088	51.3088	-0.0543	3781
    Watford (Hertfordshire)	354101	51.6561	-0.3888	3781
    Watford F.C.	354103	51.6488	-0.4001	3781
    Wembley	354121	51.5501	-0.3033	3672
    Wembley Arena	354380	51.558	-0.283	3672
    Wembley Stadium	324377	51.55602	-0.27956	3672
    West Byfleet	354129	51.3363	-0.5018	3772
    West Ham United F.C.	354137	51.5313	0.0397	3772
    Westminster	354160	51.4982	-0.1323	3779
    Weybridge	354170	51.3692	-0.4577	3772
    Wimbledon	354361	51.4218	-0.2088	3779
    Wisley	99080	51.317	-0.467	3772
    Wood Green	354286	51.6001	-0.1082	3779
    Woolwich	354312	51.4898	0.0675	3779
    Yiewsley	322958	51.52	-0.45	3672
""")

# --- build the {name: {...}} dict -----------------------------------
reader = csv.DictReader(io.StringIO(_STATION_TSV), delimiter="\t")
STATIONS: dict[str, dict] = {}
for row in reader:
    meteostat_raw = row["Meteostat ID"].strip()
    STATIONS[row["Name"]] = {
        "dp_id"  : row["MetOffice dp_id"].strip(),
        "lat"    : float(row["Latitude"]),
        "lon"    : float(row["Longitude"]),
        # pad to 5 digits, leave empty if not a number
        "meta_id": f"{int(meteostat_raw):05d}" if meteostat_raw else "",
    }

total_stations = len(STATIONS)            # still used later





# -----------------------------------------------------------------------------
#  DATA FETCHERS – each returns a station-specific dataframe
# -----------------------------------------------------------------------------

def _fetch_met_office_obs(dp_id: str, *, dev=False) -> pd.DataFrame:
    url = f"http://datapoint.metoffice.gov.uk/public/data/val/wxobs/all/json/{dp_id}?res=hourly&key={API_KEY}"
    try:
        raw = requests.get(url, timeout=10).json()
        periods = raw["SiteRep"]["DV"]["Location"].get("Period", [])
        if isinstance(periods, dict):
            periods = [periods]
    except Exception:
        return pd.DataFrame(columns=["time", "vpd"])

    today = date.today()
    now   = datetime.now()

    all_rows   = []         # <- keep everything
    filtered   = []         # <- keep only rows you normally use

    for p in periods:
        base = datetime.strptime(p["value"], "%Y-%m-%dZ")
        for rep in p.get("Rep", []):
            if not isinstance(rep, dict):
                continue
            ts = base + timedelta(minutes=int(rep.get("$", 0)))
            t, h = rep.get("T"), rep.get("H")
            if t is None or h is None:
                continue
            vpd_val = calculate_vpd(float(t), float(h))
            all_rows.append({"time": ts, "vpd": vpd_val})
            # original filter
            if ts.date() == today and ts <= now:
                filtered.append({"time": ts, "vpd": vpd_val})

    return pd.DataFrame(all_rows if dev else filtered)


def _fetch_met_office_fcst(dp_id: str) -> pd.DataFrame:
    """3‑hourly forecast for up to MAX_FORECAST_DAYS ahead for one station."""
    url = f"http://datapoint.metoffice.gov.uk/public/data/val/wxfcs/all/json/{dp_id}?res=3hourly&key={API_KEY}"
    cutoff = date.today() + timedelta(days=MAX_FORECAST_DAYS)
    try:
        raw_fcst = requests.get(url, timeout=10).json()
        periods  = raw_fcst["SiteRep"]["DV"]["Location"].get("Period", [])
        if isinstance(periods, dict):
            periods = [periods]
    except Exception:
        return pd.DataFrame(columns=["time", "vpd"])

    recs = []
    for p in periods:
        if not isinstance(p, dict):
            continue
        if not isinstance(p, dict):          # extra safety
            continue
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
    """Fetch historical data from Open-Meteo for one station."""
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
    """Replace any missing hours (or the entire day) using Meteostat."""
    if not METEOSTAT_AVAILABLE or not meta_id:
        return df                                       # nothing we can do

    start_dt = datetime.combine(day, datetime.min.time())
    end_dt   = datetime.combine(day, datetime.max.time())

    # Hours we still need, *or* all 24 if df is empty
    expected = pd.date_range(start_dt, end_dt, freq="H", inclusive="left")
    missing  = expected.difference(df["time"]) if not df.empty else expected
    if missing.empty:
        return df                                       # already complete

    # Retrieve Meteostat and keep only the missing slots
    try:
        stn = Hourly(meta_id, start_dt, end_dt).fetch().reset_index()
        stn["time"] = pd.to_datetime(stn["time"]).dt.tz_localize(None)
        stn["vpd"]  = calculate_vpd(stn["temp"], stn["rhum"])
        fill        = stn[stn["time"].isin(missing)][["time", "vpd"]].dropna()
    except Exception:
        fill = pd.DataFrame()                           # Meteostat failed

    return (pd.concat([df, fill])
              .drop_duplicates("time")
              .sort_values("time")
              .reset_index(drop=True))


# -------------------------------------------------------------------------
#  HELPERS THAT RETURN *FULL* ROWS (time, temp, rh, vpd)  – per station
# -------------------------------------------------------------------------
def _met_office_fcst_full(dp_id: str) -> pd.DataFrame:
    """Met Office 3-hourly forecast with raw T & RH as well as VPD."""
    url = (f"http://datapoint.metoffice.gov.uk/public/data/val/wxfcs/"
           f"all/json/{dp_id}?res=3hourly&key={API_KEY}")
    try:
        js   = requests.get(url, timeout=10).json()
        per  = js["SiteRep"]["DV"]["Location"]["Period"]
        per  = [per] if isinstance(per, dict) else per
    except Exception:
        return pd.DataFrame()

    rows = []
    for p in per:
        base = datetime.strptime(p["value"], "%Y-%m-%dZ")
        for rep in p.get("Rep", []):
            if isinstance(rep, dict):
                ts = base + timedelta(minutes=int(rep["$"]))
                t  = float(rep.get("T", np.nan))
                h  = float(rep.get("H", np.nan))
                rows.append({
                    "time": ts, "temperature": t, "humidity": h,
                    "vpd": calculate_vpd(t, h)
                })
    return pd.DataFrame(rows)


def _met_office_obs_full(dp_id: str) -> pd.DataFrame:
    """Met Office *observations* (hourly) with raw T & RH + VPD."""
    url = (f"http://datapoint.metoffice.gov.uk/public/data/val/wxobs/"
           f"all/json/{dp_id}?res=hourly&key={API_KEY}")
    try:
        js  = requests.get(url, timeout=10).json()
        per = js["SiteRep"]["DV"]["Location"]["Period"]
        per = [per] if isinstance(per, dict) else per
    except Exception:
        return pd.DataFrame()

    rows = []
    for p in per:
        base = datetime.strptime(p["value"], "%Y-%m-%dZ")
        for rep in p.get("Rep", []):
            if isinstance(rep, dict):
                ts = base + timedelta(minutes=int(rep["$"]))
                t  = float(rep.get("T", np.nan))
                h  = float(rep.get("H", np.nan))
                rows.append({
                    "time": ts, "temperature": t, "humidity": h,
                    "vpd": calculate_vpd(t, h)
                })
    return pd.DataFrame(rows)


def _open_meteo_full(lat: float, lon: float, day: date) -> pd.DataFrame:
    """Open-Meteo archive with raw T & RH + VPD (one historical day)."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude":  lat,
        "longitude": lon,
        "start_date": day.isoformat(),
        "end_date":   day.isoformat(),
        "hourly":     "temperature_2m,relativehumidity_2m",
        "timezone":   "Europe/London",
    }
    try:
        hr = requests.get(url, params=params, timeout=10).json()["hourly"]
    except Exception:
        return pd.DataFrame()                          # network / JSON error

    # If either variable is missing altogether → force fallback
    if "relativehumidity_2m" not in hr or "temperature_2m" not in hr:
        return pd.DataFrame()

    df = pd.DataFrame({
        "time":        pd.to_datetime(hr["time"]),
        "temperature": hr["temperature_2m"],
        "humidity":    hr["relativehumidity_2m"],
    })

    # Throw away rows with *either* value missing – they’ll be filled later
    df = df.dropna(subset=["temperature", "humidity"])
    if df.empty:
        return df                                       # triggers Meteostat

    df["vpd"] = calculate_vpd(df["temperature"], df["humidity"])
    return df[["time", "vpd"]]

@st.cache_data(show_spinner=True, ttl=1800, max_entries=10)
def gather_station_day(day: date) -> pd.DataFrame:
    """
    Return a dataframe with one row per *station-timestamp* containing:
        station • time • temperature • humidity • vpd
    Falls back to Open-Meteo/Meteostat for history, uses forecast for future.
    """
    frames = []
    for name, meta in STATIONS.items():
        dp_id, lat, lon, meta_id = (meta["dp_id"], meta["lat"],
                                    meta["lon"], meta["meta_id"])
        if   day > date.today():
            df = _met_office_fcst_full(dp_id)
        elif day == date.today():
            # prefer obs but they arrive hourly – still include partial rows
            df = _met_office_obs_full(dp_id)
            if df.empty:                       # obs not in yet → forecast
                df = _met_office_fcst_full(dp_id)
        else:
            df = _open_meteo_full(lat, lon, day)
            df = _fill_with_meteostat(df, meta_id, day)

        if not df.empty:
            df["station"] = name
            frames.append(df[df["time"].dt.date == day])

    return (pd.concat(frames, ignore_index=True)
              if frames else pd.DataFrame(columns=[
                  "station", "time", "temperature", "humidity", "vpd"]))



# -----------------------------------------------------------------------------
#  PUBLIC FETCH API - NOW USES ALL STATIONS WITH ENHANCED LOADING MESSAGES
# -----------------------------------------------------------------------------

def fetch_forecast(*, quiet: bool = False) -> tuple[pd.DataFrame, int]:    
    """Fetch forecast data from ALL London stations and return averaged data + station count."""
    all_dfs = []
    successful_stations = 0
    
    if not quiet:                       # ← wrap the widgets
        progress_bar = st.progress(0)
        status_text  = st.empty()
    
    total_stations = len(STATIONS)
    
    for i, (station_name, station_info) in enumerate(STATIONS.items()):
        # Update progress
        progress = i / total_stations
        if not quiet:
            progress_bar.progress(progress)
            status_text.text(f"🔮 Fetching … {station_name} …")
        
        df = _fetch_met_office_fcst(station_info["dp_id"])
        if not df.empty:
            df["station"] = station_name
            all_dfs.append(df)
            successful_stations += 1
    
    # Complete progress
    if not quiet:
        progress_bar.progress(1.0)
        status_text.text("✅ Forecast done")
        time.sleep(0.8)
        progress_bar.empty()
        status_text.empty()
    
    # Clear progress indicators
    time.sleep(1)
    if not quiet:
        progress_bar.empty()
        status_text.empty()

    if not all_dfs:
        return pd.DataFrame(columns=["time", "vpd"]), 0
    
    # Combine all station data
    combined = pd.concat(all_dfs, ignore_index=True)
    
    # Calculate average VPD per timestamp
    time_groups = combined.groupby("time")
    averaged_data = []
    
    for time_val, group in time_groups:
        if len(group) >= min_stations:
            avg_vpd = group["vpd"].mean()
            averaged_data.append({"time": time_val, "vpd": avg_vpd, "station_count": len(group)})
    
    result_df = pd.DataFrame(averaged_data)
    return result_df, successful_stations

@st.cache_data(ttl=1800, show_spinner=True)
def fetch_today_predicted() -> tuple[pd.DataFrame, int]:
    """
    Return the 24-hour Met Office forecast for the current day, averaged
    across all London sites (same station-count guard as fetch_forecast).
    """
    fcst_df, ok_stations = fetch_forecast()
    if fcst_df.empty:
        return fcst_df, ok_stations

    today = date.today()
    today_df = fcst_df[fcst_df["time"].dt.date == today]
    return today_df, ok_stations

def fetch_historical(day: date, *, quiet: bool = False) -> tuple[pd.DataFrame, int]:
    """Historical (or today’s obs) averaged across all stations."""
    all_dfs, successful = [], 0

    if not quiet:                      # widgets only if not “quiet”
        progress_bar = st.progress(0)
        status_text  = st.empty()

    total_stations = len(STATIONS)

    for i, (name, info) in enumerate(STATIONS.items()):
        frac = i / total_stations
        if not quiet:
            progress_bar.progress(frac)
            status_text.text(f"📚  {day} • {name} ({i+1}/{total_stations})")

        lat, lon, meta_id = info["lat"], info["lon"], info["meta_id"]

        # ────────────────────────────────
        # NEW: use Met-Office OBS for *today*
        # ────────────────────────────────
        if day == date.today():
            df = _fetch_met_office_obs(info["dp_id"])
            if df.empty:                               # fallback if a site has no obs yet
                df = _open_meteo_full(lat, lon, day)
        else:
            df = _open_meteo_full(lat, lon, day)
            df = _fill_with_meteostat(df, meta_id, day)

        if not df.empty:
            df["station"] = name
            all_dfs.append(df)
            successful += 1

    if not quiet:
        progress_bar.progress(1.0)
        status_text.text("✅  Historical done")
        time.sleep(0.8)
        progress_bar.empty()
        status_text.empty()

    if not all_dfs:
        return pd.DataFrame(columns=["time", "vpd"]), 0

    combined = pd.concat(all_dfs, ignore_index=True)
    mean_rows = (
        combined.groupby("time")
                .filter(lambda g: len(g) >= min_stations)
                .groupby("time")["vpd"]
                .mean()
                .reset_index()
    )
    return mean_rows, successful

def _blend_to_hour_grid(obs_df: pd.DataFrame,
                        fcst_df: pd.DataFrame) -> pd.Series:
    """
    Return a 24-value Series indexed by each clock-hour of *today*.

    • obs_df   – hourly Met-Office observations (already averaged per timestamp)
    • fcst_df  – 3-hourly Met-Office forecast   (already averaged per timestamp)

    Rules
    -----
    1. Start with the forecast, upsampled to an hourly step
       (linear interpolation keeps area under the curve correct).
    2. Where an observation exists for that hour, it overwrites the forecast.
    3. The result therefore has one — and only one — value per hour.
    """
    # (i) build a 24-hour index: 00:00 … 23:00 local time
    today0 = datetime.combine(date.today(), datetime.min.time())
    hour_grid = pd.date_range(today0, periods=24, freq="H")

    fcst_hourly = (fcst_df.set_index("time")
                            .resample("1H")
                            .interpolate("time")          # fill inside range
                            .reindex(hour_grid)
                            .interpolate("time",
                                         limit_direction="both")  # ← NEW: extrapolate ends
                            .ffill().bfill())              #       final safety net

    # (iii) overlay observations (they land exactly on the grid already)
    blended = fcst_hourly["vpd"].copy()
    blended.update(obs_df.set_index("time")["vpd"])

    return blended



# ---------- new compact helper ------------------------------------
def _open_meteo_daily(lat: float, lon: float,
                      start: date, end: date) -> pd.DataFrame:
    """
    One call returns daily mean T & RH for the whole range.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude":  lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date":   end.isoformat(),
        # 🔑  correct variable names  🔑
        "daily": "temperature_2m_mean,relative_humidity_2m_mean",
        "timezone": "Europe/London",
    }
    try:
        js = requests.get(url, params=params, timeout=10).json()["daily"]
    except Exception:                       # network / malformed JSON
        return pd.DataFrame()

    # both arrays are guaranteed to be same length if present
    if "relative_humidity_2m_mean" not in js:
        return pd.DataFrame()               # guard: RH missing → skip

    df = pd.DataFrame({
        # ----- FIX: DatetimeIndex already has a `.date` property -----
        "date": pd.to_datetime(js["time"]).date,    # <- was …dt.date
        "t"   : js["temperature_2m_mean"],
        "rh"  : js["relative_humidity_2m_mean"],
    })
    df["vpd"] = calculate_vpd(df["t"], df["rh"])
    return df[["date", "vpd"]]


###############################################################################
# 1️⃣  NEW helper – identical maths, but shows a progress bar while it runs
###############################################################################
def build_daily_window(window: int = 15) -> pd.DataFrame:
    """
    Same result as gather_daily_window(), but with a visible progress bar.
    Runtime-heavy calls to _open_meteo_daily() are still cached, so the
    progress bar appears instantly after the first run.
    """
    # visual widgets
    progress = st.progress(0.0)
    status   = st.empty()

    today   = date.today()
    past    = 9                    # 9 past + today + future = window
    future  = window - past - 1
    start   = today - timedelta(days=past)
    end     = today + timedelta(days=future)

    per_station = []
    total = len(STATIONS)*(1/0.9)

    for i, (station_name, meta) in enumerate(STATIONS.items(), 1):
        # ---------- status text with name + counter ----------
        status.text(
            f"📆  Building daily means • {station_name}  ({i}/143)"
        )

        dfd = _open_meteo_daily(meta["lat"], meta["lon"], start, end)  # cached
        if not dfd.empty:
            per_station.append(dfd.assign(station=1))

        progress.progress(i / total)
    
    joined = pd.concat(per_station, ignore_index=True) if per_station else pd.DataFrame()
    ok = joined.groupby("date").filter(lambda x: x["station"].count() >= min_stations)  

    # ── B. Met-Office *OBS* for today  (quiet) ─────────────────
    progress.progress(0.90)
    status.text("📡  Pulling today’s observations …")
    obs_today, _ = fetch_historical(date.today(), quiet=True)

    # ── C. Met-Office *FORECAST* for today  (quiet) ───────────
    status.text("🔮  Pulling today’s forecast …")
    fc_today, _  = fetch_forecast(quiet=True)
    fc_today     = fc_today[fc_today["time"].dt.date == date.today()]
    progress.progress(1.00)

    # ── D. Blend & inject today’s mean ─────────────────────────
    hourly_today = _blend_to_hour_grid(obs_today, fc_today)
    if not hourly_today.empty:
        ok = ok[ok["date"] != date.today()]           # drop any placeholder
        today_row = pd.DataFrame([{
            "date": date.today(),
            "vpd":  hourly_today.mean()              # correct 24-hour mean
        }])
        ok = pd.concat([ok, today_row], ignore_index=True)

    # ── tidy up widgets ────────────────────────────────────────
    progress.empty(); status.empty()

    return (ok.groupby("date")["vpd"]
              .mean()
              .reset_index()
              .sort_values("date"))

@st.cache_resource
def _daily_overview_fig(daily_df, dark):
    COL_PAST, COL_FUTURE = "#0e62a7", "#aa6805"
    fig, ax = plt.subplots(figsize=(10, 4))
    if dark:
        fig.patch.set_alpha(0)
        _darken_axes(ax)

    past_df = daily_df[daily_df["date"] <  date.today()]
    fut_df  = daily_df[daily_df["date"] >= date.today()]

    ax.plot(past_df["date"], past_df["vpd"], "--o", lw=2,
            color=COL_PAST,  ms=6)
    ax.plot(fut_df["date"],  fut_df["vpd"], "--o", lw=2,
            color=COL_FUTURE, ms=6)

    # … ⟨ your Today halo + bridge code stays unchanged ⟩ …

    # ------------------------------------------------------------------
    # ✨  INLINE LABELS  (replace the ax.legend call)
    # ------------------------------------------------------------------
    # small rounded badges sitting just inside the plot frame

    badge_kw = dict(boxstyle="round,pad=0.25",
                    lw=1.4, alpha=0.92)        #  ← no fontsize here!

    ax.text(0.01, 0.97, "Historical",
            transform=ax.transAxes, ha="left", va="top",
            color=COL_PAST, fontsize=13,        #  ← fontsize here
            bbox=dict(fc="white", ec=COL_PAST, **badge_kw))

    ax.text(0.99, 0.97, "Forecast",
            transform=ax.transAxes, ha="right", va="top",
            color=COL_FUTURE, fontsize=13,
            bbox=dict(fc="white", ec=COL_FUTURE, **badge_kw))

    # (delete the old ax.legend(...) line)
    # ------------------------------------------------------------------
    if not fut_df.empty:
        idx_today = fut_df["date"].iloc[0]
        y_today   = fut_df["vpd"].iloc[0]

        ACCENT_TODAY = "#34a853"          # keep green theme (works in dark too)

        # draw a “halo” behind the marker so it pops
        ax.scatter(idx_today, y_today,
                s=260,  marker="o",  linewidths=0,
                facecolors=ACCENT_TODAY, alpha=0.15,  zorder=4)

        # re-draw the marker itself (on top of the halo)
        ax.scatter(idx_today, y_today,
                s=60,  marker="o",  linewidths=0.4,
                edgecolors="white", facecolors=ACCENT_TODAY, zorder=5)

    # tidy arrowed annotation
    ax.annotate(
        "Today",
        xy=(idx_today, y_today),          # arrow tip
        xytext=(idx_today, y_today + 100),  # label position
        ha="center",
        textcoords="data",
        bbox=dict(boxstyle="round,pad=0.4",
                fc="white", ec=ACCENT_TODAY, lw=1.6, alpha=0.95),
        arrowprops=dict(arrowstyle="-|>",
                        lw=1.8, color=ACCENT_TODAY,
                        shrinkA=0, shrinkB=4),
        fontsize=13, color=ACCENT_TODAY, zorder=6,
    )

    # ─── Bridge yesterday → today  (blue dashed) ───────────────────────
    if not past_df.empty and not fut_df.empty:
        yesterday_x = past_df["date"].iloc[-1]
        today_x     = fut_df["date"].iloc[0]
        yesterday_y = past_df["vpd"].iloc[-1]
        today_y     = fut_df["vpd"].iloc[0]

        ax.plot([yesterday_x, today_x], [yesterday_y, today_y], "--", lw=2, color=COL_PAST, zorder=3)   # COL_PAST = blue

    ax.axhline(THRESHOLD, ls="--", color="red")
    ax.axvline(fut_df["date"].iloc[0], ls="--", color="#4E4D4D", lw=1)

    ax.set_xticks(daily_df["date"])
    ax.set_xticklabels([d.strftime("%d/%m") for d in daily_df["date"]],
                       rotation=0, ha="center")
    ax.set_ylabel("VPD (Pa)", fontsize=13)
    ax.tick_params(axis="x", labelsize=11)
    ax.tick_params(axis="y", labelsize=11)
    return fig


###############################################################################
# helper: refresh daily figure only if needed
###############################################################################
def refresh_daily_overview():
    today_str = date.today().isoformat()

    must_refresh = (
        "daily_fig" not in st.session_state
        or st.session_state.daily_fig_date != today_str
        or st.session_state.daily_fig_dark != dark        # dark-mode toggle
    )

    if must_refresh:
        daily_df = build_daily_window(15)                 # progress bar 1st time
        st.session_state.daily_df       = daily_df
        st.session_state.daily_fig      = _daily_overview_fig(daily_df, dark)
        st.session_state.daily_fig_date = today_str
        st.session_state.daily_fig_dark = dark
    else:
        daily_df = st.session_state.daily_df              # already cached

    st.markdown("<div class='section-title'>Average Daily VPD</div>",
                unsafe_allow_html=True)
    st.pyplot(st.session_state.daily_fig)

    return daily_df

###############################################################################
# Blended OBS + FORECAST for *today* (hourly resolution, all stations)
###############################################################################
@st.cache_data(ttl=900)
def blended_today() -> pd.DataFrame:
    """
    Hour-by-hour VPD for today, using observations when available and
    forecast elsewhere.  **Exactly one value per clock-hour.**
    """
    obs_df, _  = fetch_historical(date.today())           # hourly
    fcst_df, _ = fetch_forecast()
    fcst_df    = fcst_df[fcst_df["time"].dt.date == date.today()]

    hourly = _blend_to_hour_grid(obs_df, fcst_df)          # <-- NEW
    return (hourly.reset_index()
                   .rename(columns={"index": "time", 0: "vpd"}))


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

st.markdown("<h2 style='text-align:center;font-size:24px;'>London‑wide VPD Monitoring</h2>", unsafe_allow_html=True)

# Update subtitle to reflect all stations usage
total_stations = len(STATIONS)
st.markdown(
    f"<p style='text-align:center; margin-top:-0.3rem; color:{SUB_COLOUR}; font-size:0.9rem;'>"
    f"Data represent the <strong>average of all {total_stations} available London weather stations</strong>.<br>"
    "</p>",
    unsafe_allow_html=True,
)


daily_df = refresh_daily_overview()


# ── 🔥 Firewave‐risk banner ─────────────────────────────────────────
# 1.  Look at the most-recent 10 calendar days *ending today*.
window = (daily_df[daily_df["date"] <= date.today()]
          .tail(10)["vpd"]            # latest ≤ today
          .tolist())

# 2.  Count consecutive days (from most-recent backwards) above threshold.
consec = 0
for v in reversed(window):
    if v is not None and v > THRESHOLD:
        consec += 1
    else:
        break

# 3.  Decide colour / text.
firewave   = consec >= 10
col_border = "darkred"   if firewave else "darkgreen"
col_bg     = "rgba(255,0,0,0.12)" if firewave else "rgba(0,128,0,0.12)"
banner_txt = "Firewave Predicted" if firewave else "No Firewave Risk"

# 4.  Display just beneath the first plot.
st.markdown(
    f"""
    <div style='border:1.6px solid {col_border}; border-radius:6px;
                padding:6px 8px; background:{col_bg}; color:{col_border};
                font-weight:600; text-align:center;
                margin:12px 0 18px 0;'>  <!-- ⬅️  top / sides / bottom -->
        {banner_txt} &nbsp;–&nbsp; {consec}/10 recent days &gt; {THRESHOLD} Pa
    </div>
    """,
    unsafe_allow_html=True,
)




with st.expander("📍 Station inventory", expanded=False):
    inv_df = (
        pd.DataFrame.from_dict(STATIONS, orient="index")
        .reset_index()
        .rename(
            columns={
                "index": "Name",
                "dp_id": "MetOffice dp_id",
                # "meta_id": "Meteostat ID",   # ← leave the rename commented-out
                "lat": "Latitude",
                "lon": "Longitude",
            }
        )
        .drop(columns=["meta_id"])          # ← <-- hide Meteostat IDs
        .sort_values("Name")
    )

    st.dataframe(inv_df, use_container_width=True)

    # optional CSV download (no Meteostat ID either)
    csv = inv_df.to_csv(index=False).encode()
    st.download_button(
        "💾 Download as CSV",
        csv,
        file_name="london_station_inventory.csv",
        mime="text/csv",
        use_container_width=True,
    )


#  Date picker
picked = st.date_input(
    "Select day:",
    value=date.today(),
    min_value=date.today() - timedelta(days=HIST_DAYS),
    max_value=date.today() + timedelta(days=MAX_FORECAST_DAYS),
)


# ─── Hourly VPD for the day chosen in the date-picker ─────────────
if picked > date.today():                       # ⇒ future
    day_df, _ = fetch_forecast()
    day_df    = day_df[day_df["time"].dt.date == picked]
    title     = f"Forecasted Hourly VPD – {picked:%Y-%m-%d}"
    accent    = "#aa6805"        # ← amber

elif picked == date.today():                    # ⇒ today
    day_df = blended_today()
    title  = "Observed & Forecast VPD – Today"
    accent = "#34a853"          # ← green

else:                                           # ⇒ past
    day_df, _ = fetch_historical(picked)
    title     = f"Hourly VPD on {picked:%Y-%m-%d}"
    accent    = "#0e62a7"        # ← blue


#  Plot hourly line
st.markdown(
    f"<div class='section-title' style='color:{accent};'>{title}</div>",
    unsafe_allow_html=True
)
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
    # Always show a full midnight-to-midnight window
    start_of_day = datetime.combine(picked, datetime.min.time())
    end_of_day   = start_of_day + timedelta(hours=24)   # 00:00 → 24:00
    ax.set_xlim(start_of_day, end_of_day)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%d/%m"))
    ax.set_xlabel("Time", fontsize=16)
    ax.set_ylabel("VPD (Pa)", fontsize=16)
    st.pyplot(fig)
    #  Download CSV
    st.download_button("📥 Download this day as CSV", clean.to_csv(index=False).encode(), file_name=f"vpd_avg_{picked}.csv", mime="text/csv", use_container_width=True)

# -----------------------------------------------------------------
#  🔍  Raw station-by-station readings table
# -----------------------------------------------------------------
with st.expander("🧾  Raw readings for every station on this day", expanded=False):
    raw_df = gather_station_day(picked)
    if raw_df.empty:
        st.info("No raw data available for this date.")
    else:
        # nicer ordering
        raw_df = raw_df.sort_values(["station", "time"])
        st.dataframe(raw_df, use_container_width=True)
        st.download_button(
            "⬇️  Download raw readings as CSV",
            raw_df.to_csv(index=False).encode(),
            file_name=f"raw_readings_{picked}.csv",
            mime="text/csv",
            use_container_width=True,
        )



# ──────────────────────────────────────────────────────────────────────
# 📍 LIVE STATION MAP – 143 markers, progress bar, built only once
# ---------------------------------------------------------------------
import pydeck as pdk

st.markdown("<div class='section-title'>Live station map</div>",
            unsafe_allow_html=True)

# ------------------------------------------------------------------ #
#  Decide whether a rebuild is needed
# ------------------------------------------------------------------ #
needs_map = (
    "station_map_deck" not in st.session_state      # first run
    or st.session_state.get("station_map_dark") != dark   # dark-mode toggled
)

if needs_map:
    # 0️⃣  Visual feedback widgets
    progress = st.progress(0.0)
    status   = st.empty()

    # 1️⃣  Assemble one row per station (iterate so we can update progress)
    rows, total = [], len(STATIONS)
    for i, (name, meta) in enumerate(STATIONS.items(), 1):
        rows.append({
            "name"     : name,
            "met_id"   : meta["dp_id"],
            "latitude" : meta["lat"],
            "longitude": meta["lon"],
        })
        # cheap but effective “loading … n/143” line
        if i == 1 or i == total or i % 15 == 0:
            status.text(f"Placing markers … {i}/{total}")
        progress.progress(i / total)

    stations_df = pd.DataFrame(rows)

    # 2️⃣  Layer (single colour + 1-px halo so markers pop)
    MARKER_COLOUR = [32, 150, 255, 230]            # bright blue, 90 % alpha
    HALO_COLOUR   = [0, 0, 0, 255] if not dark else [255, 255, 255, 255]

    layer = pdk.Layer(
        "ScatterplotLayer",
        stations_df,
        get_position=["longitude", "latitude"],
        get_fill_color=MARKER_COLOUR,
        get_radius=400,               # ≈ 400 m on-screen
        radius_min_pixels=5,
        stroked=True,
        line_width_min_pixels=1,
        get_line_color=HALO_COLOUR,
        pickable=True,
    )

    # 3️⃣  Build deck object & stash in session_state
    deck_obj = pdk.Deck(
        layers=[layer],
        initial_view_state=dict(
            latitude=51.507, longitude=-0.128,
            zoom=8.6, pitch=0, bearing=0
        ),
        map_style=("mapbox://styles/mapbox/light-v11"
                   if not dark else
                   "mapbox://styles/mapbox/dark-v11"),
        tooltip={
            "html": (
                "<b>{name}</b><br/>"
                "Met Office ID: {met_id}<br/>"
                "Lat/Lon: {latitude}, {longitude}"
            ),
            "style": {"backgroundColor": "white",
                      "color": "black",
                      "fontSize": "12px"},
        },
    )

    st.session_state["station_map_deck"] = deck_obj
    st.session_state["station_map_dark"] = dark

    # 4️⃣  tidy up widgets
    progress.empty(); status.empty()

# ------------------------------------------------------------------ #
#  Show cached map (fast – no rebuild on date selection)
# ------------------------------------------------------------------ #
st.pydeck_chart(
    st.session_state["station_map_deck"],
    use_container_width=True,
)



# ── Footer ─────────────────────────────────────────────────────────
st.markdown(
    (
        "<div style='border:1.5px solid darkgreen; border-radius:7px; "
        "padding:5px; background-color:rgba(0,128,0,0.1); color:darkgreen; "
        "font-weight:bold; text-align:center; margin-top:10px;'>"
        "London VPD Monitoring • Powered by Streamlit"
        "</div>"
    ),
    unsafe_allow_html=True,
)
