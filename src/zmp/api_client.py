"""ZMP — Zapret Marketplace API client."""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import requests

API_BASE = "https://goshkow.com/api/marketplace/v1"
DEVICE_ID_FILE = Path.home() / ".zmp_device_id"


def get_device_id() -> str:
    if DEVICE_ID_FILE.exists():
        return DEVICE_ID_FILE.read_text(encoding="utf-8").strip()
    did = str(uuid.uuid4())
    DEVICE_ID_FILE.write_text(did, encoding="utf-8")
    return did


class MarketplaceAPI:
    def __init__(self, device_id: Optional[str] = None) -> None:
        self.device_id = device_id or get_device_id()
        self.session = requests.Session()
        self.timeout = 20

    def _headers(self) -> Dict[str, str]:
        return {"Accept": "application/json", "X-Zapret-Device": self.device_id}

    def _req(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None,
             json_body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        resp = self.session.request(
            method, f"{API_BASE}/{path.lstrip('/')}",
            headers=self._headers(), params=params, json=json_body, timeout=self.timeout,
        )
        data = resp.json()
        if isinstance(data, dict) and data.get("ok") is False:
            raise RuntimeError(data.get("error", "unknown_error"))
        return data

    def list_projects(self, q: Optional[str] = None, limit: int = 50) -> list[Dict[str, Any]]:
        params: Dict[str, Any] = {"page": 1, "limit": limit, "lang": "ru"}
        if q:
            params["q"] = q
        return self._req("GET", "projects", params=params).get("projects", [])

    def get_project(self, slug: str) -> Dict[str, Any]:
        data = self._req("GET", f"projects/{slug}", params={"lang": "ru"})
        return data.get("project", data)

    def create_ticket(self, slug: str, version_id: Optional[int] = None) -> Dict[str, Any]:
        return self._req("POST", "downloads", json_body={"slug": slug, "version_id": version_id})

    def complete_ticket(self, ticket: str, ok: bool, size: int) -> None:
        self._req("POST", f"downloads/{ticket}/complete", json_body={"success": ok, "bytes_sent": size})

    def download_zip(self, ticket: Dict[str, Any], dest: Path) -> Path:
        urls = [ticket["direct_url"]] + ([ticket["fallback_url"]] if ticket.get("fallback_url") else [])
        last_err: Optional[Exception] = None
        for url in urls:
            try:
                with self.session.get(url, headers=self._headers(), stream=True, timeout=60) as r:
                    r.raise_for_status()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(256 * 1024):
                            if chunk:
                                f.write(chunk)
                    return dest
            except Exception as e:
                last_err = e
        raise RuntimeError(f"Ошибка скачивания: {last_err}")

    def verify_zip(self, ticket: Dict[str, Any], path: Path) -> bool:
        if not path.exists() or path.stat().st_size != ticket["size"]:
            return False
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest() == ticket["sha256"]
