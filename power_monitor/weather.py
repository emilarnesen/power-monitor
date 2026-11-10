"""Hourly outdoor temperature from Open-Meteo (free, no key; uses MET Norway's models for Norway).

History comes from the archive API, recent hours and the next two days from the forecast API.
"""

from datetime import date

import httpx

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"


def _rows(body: dict, forecast_from: str | None) -> list[dict]:
    hourly = body["hourly"]
    return [
        {"ts": f"{t}:00+00:00", "temperature_c": temp,
         "forecast": forecast_from is not None and t >= forecast_from}
        for t, temp in zip(hourly["time"], hourly["temperature_2m"])
        if temp is not None
    ]


def history(latitude: float, longitude: float, start: date, end: date) -> list[dict]:
    resp = httpx.get(ARCHIVE, timeout=120, params={
        "latitude": latitude, "longitude": longitude, "start_date": start.isoformat(),
        "end_date": end.isoformat(), "hourly": "temperature_2m", "timezone": "GMT"})
    resp.raise_for_status()
    return _rows(resp.json(), None)


def recent_and_forecast(latitude: float, longitude: float, now_utc_hour: str) -> list[dict]:
    """The last 3 days and the next 2. Hours from now_utc_hour ("YYYY-MM-DDTHH:00") are forecasts."""
    resp = httpx.get(FORECAST, timeout=60, params={
        "latitude": latitude, "longitude": longitude, "hourly": "temperature_2m",
        "past_days": 3, "forecast_days": 3, "timezone": "GMT"})
    resp.raise_for_status()
    return _rows(resp.json(), now_utc_hour)
