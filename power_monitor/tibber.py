"""Tibber GraphQL API: prices and consumption history."""

import time
from collections.abc import Iterator

import httpx

API = "https://api.tibber.com/v1-beta/gql"
LIVE = "wss://websocket-api.tibber.com/v1-beta/gql/subscriptions"
USER_AGENT = "power-monitor/0.1 (+https://github.com/emilarnesen/power-monitor)"

# Seconds to wait after Tibber answers 429 (IP temporarily banned).
BAN_WAIT = 300
# Pause between history pages, to stay clear of the ban.
PAGE_PAUSE = 3

# Largest page Tibber returns per resolution.
PAGE_SIZE = {"HOURLY": 744, "QUARTER_HOURLY": 672, "DAILY": 366}

CONSUMPTION = """
query($home: ID!, $first: Int!, $after: String) {
  viewer { home(id: $home) {
    consumption(resolution: HOURLY, first: $first, after: $after) {
      pageInfo { endCursor hasNextPage }
      nodes { from consumption cost unitPrice }
    }
  } }
}"""

PRICES = """
query($home: ID!, $resolution: PriceInfoRangeResolution!, $first: Int!, $after: String) {
  viewer { home(id: $home) { currentSubscription {
    priceInfoRange(resolution: $resolution, first: $first, after: $after) {
      pageInfo { endCursor hasNextPage }
      nodes { startsAt total energy tax level currency }
    }
  } } }
}"""


PRICES_TODAY_TOMORROW = """
query($home: ID!, $resolution: PriceInfoResolution!) {
  viewer { home(id: $home) { currentSubscription {
    priceInfo(resolution: $resolution) {
      today { startsAt total energy tax level currency }
      tomorrow { startsAt total energy tax level currency }
    }
  } } }
}"""

RECENT_CONSUMPTION = """
query($home: ID!, $last: Int!) {
  viewer { home(id: $home) {
    consumption(resolution: HOURLY, last: $last) { nodes { from consumption cost unitPrice } }
  } }
}"""

LIVE_SUBSCRIPTION = """
subscription($home: ID!) {
  liveMeasurement(homeId: $home) {
    timestamp power powerProduction accumulatedConsumption accumulatedCost
    accumulatedConsumptionLastHour powerFactor
    voltagePhase1 voltagePhase2 voltagePhase3 currentL1 currentL2 currentL3
  }
}"""


class Tibber:
    def __init__(self, token: str, home_id: str):
        self.home_id = home_id
        self.http = httpx.Client(
            headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}, timeout=60
        )

    def query(self, query: str, **variables) -> dict:
        body = {"query": query, "variables": {"home": self.home_id, **variables}}
        resp = self.http.post(API, json=body)
        # Tibber bans the IP "for a few minutes" after a burst (about 200 calls in a few
        # minutes did it). Wait it out rather than make it worse.
        for _ in range(3):
            if resp.status_code != 429:
                break
            time.sleep(BAN_WAIT)
            resp = self.http.post(API, json=body)
        resp.raise_for_status()
        body = resp.json()
        if body.get("errors"):
            raise RuntimeError(f"Tibber: {body['errors']}")
        return body["data"]["viewer"]["home"]

    def _pages(self, query: str, path: tuple[str, ...], page_size: int, after: str | None, **variables) -> Iterator[list[dict]]:
        while True:
            node = self.query(query, first=page_size, after=after, **variables)
            for key in path:
                node = node[key]
            yield node["nodes"]
            if not node["pageInfo"]["hasNextPage"]:
                return
            after = node["pageInfo"]["endCursor"]
            time.sleep(PAGE_PAUSE)

    def consumption_hourly(self, after: str | None = None) -> Iterator[list[dict]]:
        """Hourly consumption from the first day as a customer, oldest first, one page at a time."""
        return self._pages(CONSUMPTION, ("consumption",), PAGE_SIZE["HOURLY"], after)

    def prices_today_tomorrow(self, resolution: str) -> list[dict]:
        """Today's and (after about 13:00) tomorrow's prices."""
        info = self.query(PRICES_TODAY_TOMORROW, resolution=resolution)["currentSubscription"]["priceInfo"]
        return info["today"] + info["tomorrow"]

    def recent_consumption(self, hours: int) -> list[dict]:
        return self.query(RECENT_CONSUMPTION, last=hours)["consumption"]["nodes"]

    def prices(self, resolution: str, after: str | None = None) -> Iterator[list[dict]]:
        """Prices from the first day as a customer, oldest first, one page at a time."""
        return self._pages(PRICES, ("currentSubscription", "priceInfoRange"), PAGE_SIZE[resolution], after,
                           resolution=resolution)
