#!/usr/bin/env python3
"""Upload every dashboard in grafana/dashboards/ to Grafana Cloud, into the folder "Strøm".

The JSON files in the repo are the source of truth: changes made in the Grafana UI are
overwritten. Export from the UI and commit if you want to keep one.

Usage: GRAFANA_URL=https://<stack>.grafana.net scripts/grafana-sync.py
Reads a service account token (Editor) from ~/.config/grafana-cloud/editor-token.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

URL = os.environ.get("GRAFANA_URL", "https://emilarnesen.grafana.net").rstrip("/")
TOKEN = (Path.home() / ".config/grafana-cloud/editor-token").read_text().strip()
DASHBOARDS = Path(__file__).resolve().parent.parent / "grafana" / "dashboards"
FOLDER = {"uid": "power-monitor", "title": "Strøm"}


def api(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(URL + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "{}")


def main() -> None:
    status, _ = api("GET", f"/api/folders/{FOLDER['uid']}")
    if status == 404:
        status, out = api("POST", "/api/folders", FOLDER)
        print(f"folder {FOLDER['title']}: {'created' if status == 200 else out}")

    for path in sorted(DASHBOARDS.glob("*.json")):
        dashboard = json.loads(path.read_text())
        # Shared (public) dashboards fetch data per panel id, so every panel needs a stable one.
        for number, panel in enumerate(dashboard["panels"], start=1):
            panel.setdefault("id", number)
            # A shared dashboard also asks for data for text panels and shows "Failed to extract
            # queries from panel" when there is none. A constant query keeps it quiet.
            if panel["type"] == "text" and not panel.get("targets"):
                panel["datasource"] = {"type": "prometheus", "uid": "grafanacloud-prom"}
                panel["targets"] = [{"refId": "A", "expr": "vector(1)", "instant": True}]
        status, out = api("POST", "/api/dashboards/db",
                          {"dashboard": dashboard, "folderUid": FOLDER["uid"], "overwrite": True,
                           "message": "grafana-sync.py"})
        print(f"{path.name}: {URL + out['url'] if status == 200 else f'FAILED {status} {out}'}")


if __name__ == "__main__":
    main()
