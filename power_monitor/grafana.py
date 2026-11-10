"""Push metrics to Grafana Cloud as Influx line protocol.

Grafana Cloud turns `power_monitor,phase=L1 voltage_v=227.1` into the Prometheus series
`power_monitor_voltage_v{phase="L1"}`. Failed pushes are kept and retried, up to a limit.
"""

from collections import deque

import httpx

MEASUREMENT = "power_monitor"
MAX_BUFFERED_LINES = 50_000  # about a day of readings


def line(fields: dict[str, float | None], tags: dict[str, str] | None = None, ts_ns: int | None = None) -> str | None:
    values = ",".join(f"{k}={float(v)}" for k, v in fields.items() if v is not None)
    if not values:
        return None
    tag_str = "".join(f",{k}={v}" for k, v in (tags or {}).items())
    return f"{MEASUREMENT}{tag_str} {values}" + (f" {ts_ns}" if ts_ns else "")


class Grafana:
    def __init__(self, url: str, user: str, token: str):
        self.url = url
        self.http = httpx.AsyncClient(auth=(user, token), timeout=20)
        self.pending: deque[str] = deque(maxlen=MAX_BUFFERED_LINES)

    async def push(self, lines: list[str | None]) -> None:
        self.pending.extend(l for l in lines if l)
        if not self.pending:
            return
        batch = list(self.pending)
        try:
            resp = await self.http.post(self.url, content="\n".join(batch))
            resp.raise_for_status()
        except httpx.HTTPError as e:
            print(f"grafana push failed, {len(batch)} lines kept: {e}", flush=True)
            return
        for _ in batch:
            self.pending.popleft()
