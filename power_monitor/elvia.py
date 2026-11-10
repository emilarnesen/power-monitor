"""Elvia GridTariff API: grid tariff energy charge and capacity steps for one metering point."""

import time
from datetime import datetime

import httpx

API = "https://elvia.azure-api.net/grid-tariff/digin/api/1/tariffquery/meteringpointsgridtariffs"


class Elvia:
    def __init__(self, api_key: str, metering_point_id: str):
        self.metering_point_id = metering_point_id
        self.http = httpx.Client(headers={"X-API-Key": api_key}, timeout=60)

    def tariff(self, start: datetime, end: datetime) -> dict | None:
        """The grid tariff between start and end, or None when Elvia has no prices for the period.

        Returns {"tariff_key", "hours": [...], "fixed_prices": [...]} in Elvia's own shapes.
        """
        body = {
            "startTime": start.isoformat(),
            "endTime": end.isoformat(),
            "meteringPointIds": [self.metering_point_id],
        }
        resp = self.http.post(API, json=body)
        # 200 calls/hour; when over it, Elvia says how long to wait.
        while resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After", "60")) + 1)
            resp = self.http.post(API, json=body)
        resp.raise_for_status()
        tariff = resp.json()["gridTariffCollections"][0]["gridTariff"]
        price = tariff["tariffPrice"]
        if not price.get("hours"):
            return None
        return {
            "tariff_key": tariff["tariffType"]["tariffKey"],
            "hours": price["hours"],
            "fixed_prices": price["priceInfo"].get("fixedPrices") or [],
        }
