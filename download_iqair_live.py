"""
Build a complete hourly dataset for Phnom Penh from 2024-01-01 to NOW:
1. Historical/recent hourly data:
   Uses CAMS air-quality data and weather data via Open-Meteo. The recent
   30-day window is refreshed on every run to backfill the local cache.
2. Current IQAir observation:
   Fetches the current response from IQAir AirVisual API v2. If the response
   includes pollutant concentrations, they are used directly. If PM2.5
   concentration is absent, PM2.5 is estimated from the returned US AQI. If
   PM10 is absent, a same-hour Open-Meteo model value is used when available;
   otherwise it remains missing. Per-field source columns record this.

The API key must be set in the IQAIR_API_KEY environment variable.
Output file: iqair_phnom_penh_live.csv (2024-01-01 00:00:00 -> latest available hour)
"""
import calendar
from datetime import date
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------- SETTINGS (change here) ----------------
IQAIR_API_KEY = os.environ.get("IQAIR_API_KEY", "c3877ca8-f31c-4a7b-a47b-d2dfca54fb7b").strip()

COUNTRY = "Cambodia"
STATE = "Phnom Penh"
CITY = "Phnom Penh"
LAT, LON = 11.56, 104.93
TZ = "Asia/Bangkok"
START = date(2024, 1, 1)
END = pd.Timestamp.now(tz=TZ).date()
RECENT_DAYS = 30

HIST_CACHE_CSV = Path("cambodia_air_quality_hourly_from2024.csv")
OUTPUT_CSV = Path("iqair_phnom_penh_live.csv")
# --------------------------------------------------------

IQAIR_URL = "https://api.airvisual.com/v2/city"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
RECENT_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

AIR_VARS = "pm2_5,pm10"
WEATHER_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,rain"

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (student mini project)"})
session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=5,
            connect=5,
            read=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
        )
    ),
)

# US EPA (2024) PM2.5 <-> Instant US AQI* breakpoints (used by IQAir "US AQI*")
EPA_BREAKPOINTS = [
    (0.0, 9.0, 0, 50),
    (9.1, 35.4, 51, 100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 500.4, 301, 500),
]


def pm25_to_iqair_aqi(pm25: float) -> int:
    """Convert PM2.5 (µg/m³) to IQAir's instantaneous US AQI* (0-500)."""
    c = max(0.0, float(pm25))
    for c_lo, c_hi, i_lo, i_hi in EPA_BREAKPOINTS:
        if c <= c_hi:
            aqi = (i_hi - i_lo) / (c_hi - c_lo) * (c - c_lo) + i_lo
            return int(round(aqi))
    return 500


def iqair_aqi_to_pm25(aqi: float) -> float:
    """Convert IQAir's US AQI* (0-500) back to approximate PM2.5 (µg/m³)."""
    a = max(0.0, float(aqi))
    for c_lo, c_hi, i_lo, i_hi in EPA_BREAKPOINTS:
        if a <= i_hi:
            pm25 = (a - i_lo) / (i_hi - i_lo) * (c_hi - c_lo) + c_lo
            return round(pm25, 1)
    return 500.0


def month_chunks(start: date, end: date):
    """Split date range into calendar months."""
    chunks = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        last_day = calendar.monthrange(year, month)[1]
        s = max(start, date(year, month, 1))
        e = min(end, date(year, month, last_day))
        if s <= e:
            chunks.append((s.isoformat(), e.isoformat()))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return chunks


def download_openmeteo_range(url: str, hourly_vars: str) -> pd.DataFrame:
    """Download monthly chunks from Open-Meteo."""
    frames = []
    for s, e in month_chunks(START, END):
        params = {
            "latitude": LAT,
            "longitude": LON,
            "hourly": hourly_vars,
            "start_date": s,
            "end_date": e,
            "timezone": TZ,
        }
        r = session.get(url, params=params, timeout=120)
        if r.status_code == 400:
            continue
        r.raise_for_status()
        frames.append(pd.DataFrame(r.json()["hourly"]))
    out = pd.concat(frames, ignore_index=True)
    out["time"] = pd.to_datetime(out["time"])
    return out


def download_recent_history() -> pd.DataFrame:
    """Refresh recent modeled air quality and weather to backfill the local cache."""
    air_params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": AIR_VARS,
        "past_days": RECENT_DAYS,
        "forecast_days": 1,
        "timezone": TZ,
    }
    air_response = session.get(AIR_URL, params=air_params, timeout=120)
    air_response.raise_for_status()
    air = pd.DataFrame(air_response.json()["hourly"])
    air["time"] = pd.to_datetime(air["time"])
    air = air.rename(columns={"pm2_5": "pm25"})

    weather_params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": WEATHER_VARS,
        "past_days": RECENT_DAYS,
        "forecast_days": 1,
        "timezone": TZ,
    }
    weather_response = session.get(
        RECENT_WEATHER_URL, params=weather_params, timeout=120
    )
    weather_response.raise_for_status()
    weather = pd.DataFrame(weather_response.json()["hourly"])
    weather["time"] = pd.to_datetime(weather["time"])

    recent = air.merge(weather, on="time", how="inner")
    recent.insert(0, "country", COUNTRY)
    recent.insert(1, "city", CITY)
    recent.insert(2, "latitude", LAT)
    recent.insert(3, "longitude", LON)
    recent["pm25_source"] = "CAMS via Open-Meteo (modeled)"
    recent["pm10_source"] = "CAMS via Open-Meteo (modeled)"
    recent["weather_source"] = "Open-Meteo (modeled)"
    return recent


def ensure_hourly_timeline(frame: pd.DataFrame) -> pd.DataFrame:
    """Add missing hourly timestamps without inventing pollutant readings."""
    frame = frame.drop_duplicates(subset=["city", "time"], keep="last")
    frame = frame.sort_values(["city", "time"]).reset_index(drop=True)
    hourly_index = pd.date_range(frame["time"].min(), frame["time"].max(), freq="h")
    frame = frame.set_index("time").reindex(hourly_index)
    frame.index.name = "time"
    frame = frame.reset_index()
    frame["country"] = frame["country"].fillna(COUNTRY)
    frame["city"] = frame["city"].fillna(CITY)
    frame["latitude"] = frame["latitude"].fillna(LAT)
    frame["longitude"] = frame["longitude"].fillna(LON)
    for column in ["pm25_source", "pm10_source", "weather_source"]:
        frame[column] = frame[column].fillna("no source value for this hour")
    return frame


def load_or_download_history() -> pd.DataFrame:
    """Load 2024-present hourly history (from local CSV if available, else download)."""
    now_hour = pd.Timestamp.now(tz=TZ).tz_localize(None).floor("h")

    if HIST_CACHE_CSV.exists():
        print(f"Loading 2024-present base history from {HIST_CACHE_CSV}...")
        hist = pd.read_csv(HIST_CACHE_CSV, parse_dates=["time"])
    else:
        print("Downloading 2024-present hourly history...")
        air = download_openmeteo_range(AIR_URL, AIR_VARS)
        weather = download_openmeteo_range(WEATHER_URL, WEATHER_VARS)
        r_recent = session.get(
            RECENT_WEATHER_URL,
            params={
                "latitude": LAT,
                "longitude": LON,
                "hourly": WEATHER_VARS,
                "past_days": RECENT_DAYS,
                "forecast_days": 1,
                "timezone": TZ,
            },
            timeout=120,
        )
        r_recent.raise_for_status()
        recent = pd.DataFrame(r_recent.json()["hourly"])
        recent["time"] = pd.to_datetime(recent["time"])
        weather = (
            weather.set_index("time")
            .combine_first(recent.set_index("time"))
            .reset_index()
        )
        hist = air.merge(weather, on="time", how="inner").rename(columns={"pm2_5": "pm25"})
        hist.insert(0, "country", COUNTRY)
        hist.insert(1, "city", CITY)
        hist.insert(2, "latitude", LAT)
        hist.insert(3, "longitude", LON)

    # Older CSVs do not record source provenance; preserve that uncertainty.
    known_sources = {
        "pm25_source": "CAMS via Open-Meteo (modeled)",
        "pm10_source": "CAMS via Open-Meteo (modeled)",
        "weather_source": "Open-Meteo archive/reanalysis",
    }
    for column, source in known_sources.items():
        if column not in hist.columns:
            hist[column] = source
        else:
            hist[column] = hist[column].fillna(source)

    # Refresh the recent window on every run, even when a historical cache exists.
    recent = pd.DataFrame()
    try:
        recent = download_recent_history()
    except (requests.RequestException, ValueError, KeyError) as err:
        print(f"Recent Open-Meteo refresh failed; keeping cached history: {err}")

    # Preserve known IQAir observations. Older rows without source tags are
    # refreshed by Open-Meteo where that recent window overlaps them.
    if OUTPUT_CSV.exists():
        prev_live = pd.read_csv(OUTPUT_CSV, parse_dates=["time"])
        for column in ["pm25_source", "pm10_source", "weather_source"]:
            if column not in prev_live.columns:
                prev_live[column] = "legacy row; exact source unknown"
        from_iqair = pd.Series(False, index=prev_live.index)
        for column in ["pm25_source", "pm10_source", "weather_source"]:
            from_iqair |= prev_live[column].astype(str).str.contains("IQAir", case=False)
        hist = pd.concat(
            [hist, prev_live.loc[~from_iqair], recent, prev_live.loc[from_iqair]],
            ignore_index=True,
        )
    else:
        hist = pd.concat([hist, recent], ignore_index=True)
    # For repeated timestamps, use the newest non-null value in each field.
    # This lets refreshed modeled data backfill a blank in an older saved row.
    hist = hist.groupby(["city", "time"], as_index=False).last()

    hist = hist[hist["time"] <= now_hour]
    hist = ensure_hourly_timeline(hist)

    # Compute IQAir-compatible instantaneous US AQI* for all historical rows
    hist["us_aqi"] = [
        pm25_to_iqair_aqi(v) if pd.notna(v) else np.nan for v in hist["pm25"]
    ]
    return hist


def fetch_iqair_live(api_key: str) -> dict:
    """Fetch the latest Phnom Penh IQAir observation and preserve missing values."""
    params = {
        "city": CITY,
        "state": STATE,
        "country": COUNTRY,
        "key": api_key,
    }
    r = session.get(IQAIR_URL, params=params, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"IQAir API error ({r.status_code}): {r.text}")

    payload = r.json()
    if payload.get("status") != "success":
        raise RuntimeError(f"IQAir API returned non-success: {payload}")

    data = payload["data"]
    pollution = data["current"]["pollution"]
    weather = data["current"]["weather"]

    ts_local = (
        pd.to_datetime(pollution["ts"])
        .tz_convert(TZ)
        .tz_localize(None)
        .floor("h")
    )
    us_aqi = int(pollution["aqius"])
    pm25_concentration = (pollution.get("p2") or {}).get("conc")
    pm10_concentration = (pollution.get("p1") or {}).get("conc")
    pm25 = (
        round(float(pm25_concentration), 1)
        if pm25_concentration is not None
        else iqair_aqi_to_pm25(us_aqi)
    )
    pm25_source = (
        "IQAir PM2.5 concentration"
        if pm25_concentration is not None
        else "estimated from IQAir US AQI"
    )
    pm10 = round(float(pm10_concentration), 1) if pm10_concentration is not None else np.nan
    wind_speed = weather.get("ws")
    wind_speed_kmh = round(float(wind_speed) * 3.6, 1) if wind_speed is not None else np.nan

    return {
        "country": COUNTRY,
        "city": CITY,
        "latitude": LAT,
        "longitude": LON,
        "time": ts_local,
        "pm25": pm25,
        "pm10": pm10,
        "us_aqi": us_aqi,
        "temperature_2m": float(weather.get("tp", np.nan)),
        "relative_humidity_2m": float(weather.get("hu", np.nan)),
        "wind_speed_10m": wind_speed_kmh,
        "wind_direction_10m": float(weather.get("wd", np.nan)),
        "rain": np.nan,
        "pm25_source": pm25_source,
        "pm10_source": (
            "IQAir PM10 concentration"
            if pm10_concentration is not None
            else np.nan
        ),
        "weather_source": "IQAir current weather; rain unavailable",
    }


def main():
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 1000)

    if not IQAIR_API_KEY:
        raise SystemExit(
            "IQAIR_API_KEY is not set. Add your rotated key to the environment "
            "before running this downloader."
        )

    # 1. Load 2024 -> present hourly dataset
    df = load_or_download_history()

    # 2. Fetch live current hour from IQAir API and merge into dataset
    live_row = fetch_iqair_live(IQAIR_API_KEY)
    same_hour = df.loc[df["time"] == live_row["time"]]
    if not same_hour.empty:
        for column, source_column in [
            ("pm10", "pm10_source"),
            ("rain", "weather_source"),
        ]:
            if pd.isna(live_row[column]) and pd.notna(same_hour.iloc[-1][column]):
                live_row[column] = same_hour.iloc[-1][column]
                live_row[source_column] = same_hour.iloc[-1][source_column]
                if column == "rain":
                    live_row["weather_source"] = "IQAir + Open-Meteo (modeled)"
        for column in ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "wind_direction_10m"]:
            if pd.isna(live_row[column]) and pd.notna(same_hour.iloc[-1][column]):
                live_row[column] = same_hour.iloc[-1][column]
                live_row["weather_source"] = "IQAir + Open-Meteo (modeled)"
    live_df = pd.DataFrame([live_row])

    combined = pd.concat([df, live_df], ignore_index=True)
    combined = ensure_hourly_timeline(combined)

    # Ensure column order matches training dataset
    cols = [
        "country",
        "city",
        "latitude",
        "longitude",
        "time",
        "pm25",
        "pm10",
        "us_aqi",
        "temperature_2m",
        "relative_humidity_2m",
        "wind_speed_10m",
        "wind_direction_10m",
        "rain",
        "pm25_source",
        "pm10_source",
        "weather_source",
    ]
    combined = combined[cols]
    combined.to_csv(OUTPUT_CSV, index=False)

    print(f"\nSaved complete 2024-to-now dataset: {OUTPUT_CSV}")
    print(f"Total rows : {len(combined)}")
    print(f"Start time : {combined['time'].min()}")
    print(f"Latest dataset time: {combined['time'].max()}")
    print(f"Latest IQAir observation time: {live_row['time']}")
    print("Timestamps are hourly; missing source readings remain blank.")
    print("\nMissing values per column:")
    print(combined.isna().sum())
    print("\nLast 5 hourly rows (source labels identify modeled vs. IQAir values):")
    print(combined.tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
