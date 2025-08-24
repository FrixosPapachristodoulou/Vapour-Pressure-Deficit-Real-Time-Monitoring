# London-wide Vapour Pressure Deficit (VPD) Monitor

A **Streamlit web app** for monitoring the **Vapour Pressure Deficit (VPD)** across **all available weather stations in Greater London**.  
The app integrates multiple data sources (Met Office DataPoint, Open-Meteo, Meteostat) to provide **hourly, daily, and forecasted VPD trends**, enhanced with a modern UI, interactive maps, and real-time fire-risk assessment.

---

## Live Features

- **London-wide coverage**  
  Data is aggregated from **133 London stations** (Met Office + Meteostat IDs).  
  Results are averaged to give a *robust city-wide VPD index*.

- **Hourly, Daily & Forecast Data**
  - **Past 9 days** → sourced from Open-Meteo archives (with Meteostat fallback).
  - **Today** → blended from live Met Office **observations** + forecast overwrite.
  - **Future 5 days** → 3-hourly Met Office forecast, interpolated to hourly.

- **Automatic Firewave Risk Detection**  
  - A “Firewave” is predicted if **≥ 10 consecutive days** exceed the critical threshold (`706 Pa`).  
  - A banner highlights fire-risk in real-time.

- **Daily VPD Overview (15-day window)**  
  - Combines **past, present, and future** into one chart.  
  - Inline legends (“Historical” / “Forecast”), with a **halo marker for Today**.

- **Hourly VPD Plot**  
  - Full **midnight-to-midnight view** for any selected date.  
  - Threshold crossing lines are colored:
    - 🟢 Below threshold  
    - 🔴 Above threshold  
    - Segmented when crossing occurs.

- **Interactive Map of Stations**  
  - Built with [PyDeck](https://deckgl.readthedocs.io).  
  - 139+ markers, interactive hover tooltips (station name, ID, coordinates).  
  - Automatically adapts to **dark / light mode**.

- **Station Inventory & Raw Data**
  - Downloadable **CSV inventory** of all London stations.
  - Raw **per-station hourly readings** available for any chosen day.

- **Dark-Mode Toggle**  
  - Complete **theming support** including charts, map, and download buttons.  
  - Subtle CSS polish for a modern look (Google Inter font, zoomed layout, minimal borders).

---

## Data Sources

1. **[Met Office DataPoint](https://www.metoffice.gov.uk/services/data/datapoint)**
   - Live **observations** (hourly).  
   - 3-hourly **forecasts** up to 5 days ahead.

2. **[Open-Meteo Archive API](https://open-meteo.com/en/docs/historical-weather-api)**
   - Historical hourly archives for past 9 days.  
   - Also supports bulk daily mean fetches (temperature + RH).

3. **[Meteostat](https://meteostat.net/)**
   - Used as a **fallback** to fill missing historical values.  
   - Hourly `temp` & `rhum` converted into VPD.

---

## VPD Calculation

The Vapour Pressure Deficit (Pa) is computed from temperature (`T`, °C) and relative humidity (`RH`, %):

```python
def calculate_vpd(temp, rh):
    esat = 610.7 * 10 ** (7.5 * temp / (237.3 + temp))
    return esat * (1 - rh / 100)
```

---

## Parallel Fetching

Fetching data from ~133 London stations per request is computationally heavy.  
To achieve interactive speeds, the app uses **`concurrent.futures.ThreadPoolExecutor`** with up to **32 workers** to query APIs **concurrently**.  

```python
with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    futures = {
        ex.submit(_fetch_met_office_fcst, meta["dp_id"]): name
        for name, meta in STATIONS.items()
    }
    for n, fut in enumerate(as_completed(futures), 1):
        name = futures[fut]        # station name
        df   = fut.result()        # individual station DataFrame
        if not df.empty:
            df["station"] = name
            all_dfs.append(df)
```

---

## Multi-Source Integration

To ensure **data completeness and robustness**, the app layers multiple providers and selects the right source per date:

- **Met Office DataPoint** → live hourly **observations** + 3-hourly **forecasts** (future).
- **Open-Meteo Archive API** → **historical** hourly values (last 9 days).
- **Meteostat** → **fallback** to fill missing historical hours.

```python
def _station_day(meta: dict, day: date) -> pd.DataFrame:
    dp_id, lat, lon, meta_id = meta["dp_id"], meta["lat"], meta["lon"], meta["meta_id"]

    if day > date.today():                       # future → forecast
        df = _met_office_fcst_full(dp_id)

    elif day == date.today():                    # today → obs (fallback: forecast)
        df = _met_office_obs_full(dp_id)
        if df.empty:
            df = _met_office_fcst_full(dp_id)

    else:                                        # past → Open-Meteo (+ Meteostat fill)
        df = _open_meteo_full(lat, lon, day)
        df = _fill_with_meteostat(df, meta_id, day)

    if not df.empty:
        df = _ensure_dt(df, "time")
        df = df[_safe_dt_date(df["time"]) == day]
    return df
```
