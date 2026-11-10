"""Settings from environment variables. See docs/configuration.md."""

import os
from dataclasses import dataclass


def _required(name: str) -> str:
    # Keys pasted from a browser often carry spaces, which make an illegal HTTP header.
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing environment variable {name} (see docs/configuration.md)")
    return value


def _optional(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None


@dataclass(frozen=True)
class Config:
    tibber_token: str
    tibber_home_id: str
    elvia_api_key: str
    metering_point_id: str
    main_fuse_amps: int
    grid_voltage: int
    price_area: str
    database_url: str
    entsoe_token: str | None
    grafana_influx_url: str | None
    grafana_metrics_user: str | None
    grafana_metrics_token: str | None

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            tibber_token=_required("TIBBER_TOKEN"),
            tibber_home_id=_required("TIBBER_HOME_ID"),
            elvia_api_key=_required("ELVIA_API_KEY"),
            metering_point_id=_required("METERING_POINT_ID"),
            main_fuse_amps=int(os.environ.get("MAIN_FUSE_AMPS", "0")),
            grid_voltage=int(os.environ.get("GRID_VOLTAGE", "230")),
            price_area=os.environ.get("PRICE_AREA", "NO1"),
            database_url=_required("DATABASE_URL"),
            entsoe_token=_optional("ENTSOE_TOKEN"),
            grafana_influx_url=_optional("GRAFANA_INFLUX_URL"),
            grafana_metrics_user=_optional("GRAFANA_METRICS_USER"),
            grafana_metrics_token=_optional("GRAFANA_METRICS_TOKEN"),
        )
