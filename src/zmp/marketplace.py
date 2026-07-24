"""
zapret_marketplace.py

Python-клиент для Zapret Marketplace API:
https://goshkow.com/api/marketplace/v1
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import requests


BASE_URL = "https://goshkow.com/api/marketplace/v1"


class ZapretMarketplaceError(Exception):
    """Базовое исключение клиента Zapret Marketplace."""


class ZapretMarketplaceApiError(ZapretMarketplaceError):
    """Ошибка, которую вернул API (ok=false)."""

    def __init__(self, error: str, payload: Dict[str, Any]):
        super().__init__(error)
        self.error = error
        self.payload = payload


@dataclass
class DownloadTicket:
    ok: bool
    ticket: str
    ticket_id: int
    filename: str
    size: int
    sha256: str
    direct_url: str
    fallback_url: Optional[str]
    expires_at: int
    raw: Dict[str, Any]


class ZapretMarketplaceClient:
    """
    Клиент Zapret Marketplace.

    - Публичные методы не требуют авторизации.
    - Можно передать Bearer-токен официального клиента и X-Zapret-Device.
    """

    def __init__(
        self,
        base_url: str = BASE_URL,
        bearer_token: Optional[str] = None,
        device_id: Optional[str] = None,
        session: Optional[requests.Session] = None,
        timeout: Union[int, float] = 15,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.device_id = device_id
        self.session = session or requests.Session()
        self.timeout = timeout

    # -------------------- internal helpers --------------------

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Accept": "application/json",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        if self.device_id:
            headers["X-Zapret-Device"] = self.device_id
        if extra:
            headers.update(extra)
        return headers

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = self._url(path)
        resp = self.session.request(
            method=method,
            url=url,
            headers=self._headers(
                {"Content-Type": "application/json"} if json is not None else None
            ),
            params=params,
            json=json,
            timeout=self.timeout,
        )
        try:
            data = resp.json()
        except ValueError:
            raise ZapretMarketplaceError(
                f"Non-JSON response from {url}: {resp.status_code}"
            )

        if isinstance(data, dict) and data.get("ok") is False:
            raise ZapretMarketplaceApiError(data.get("error", "unknown_error"), data)

        return data

    # -------------------- catalog --------------------

    def list_projects(
        self,
        q: Optional[str] = None,
        compatibility: Optional[str] = None,
        category: Optional[str] = None,
        sort: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
        lang: str = "ru",
    ) -> Dict[str, Any]:
        """
        GET /projects

        Возвращает каталог модификаций.
        """
        params: Dict[str, Any] = {
            "page": page,
            "limit": limit,
            "lang": lang,
        }
        if q is not None:
            params["q"] = q
        if compatibility is not None:
            params["compatibility"] = compatibility
        if category is not None:
            params["category"] = category
        if sort is not None:
            params["sort"] = sort

        return self._request("GET", "/projects", params=params)

    def get_project(
        self,
        slug: str,
        lang: str = "ru",
    ) -> Dict[str, Any]:
        """
        GET /projects/{slug}?lang=ru

        Полная карточка проекта + версии, зависимости, скриншоты, комментарии.
        """
        params = {"lang": lang}
        return self._request("GET", f"/projects/{slug}", params=params)

    def get_project_versions(
        self,
        slug: str,
        lang: str = "ru",
    ) -> Dict[str, Any]:
        """
        GET /projects/{slug}/versions?lang=ru

        Список опубликованных версий проекта.
        """
        params = {"lang": lang}
        return self._request("GET", f"/projects/{slug}/versions", params=params)

    def get_latest_version(
        self,
        slug: str,
        lang: str = "ru",
    ) -> Dict[str, Any]:
        """
        GET /projects/{slug}/latest?lang=ru

        Последняя версия проекта.
        """
        params = {"lang": lang}
        return self._request("GET", f"/projects/{slug}/latest", params=params)

    # -------------------- downloads / tickets --------------------

    def create_download_ticket(
        self,
        slug: str,
        version_id: Optional[int] = None,
    ) -> DownloadTicket:
        """
        POST /downloads

        Создаёт ticket для скачивания ZIP.
        """
        body: Dict[str, Any] = {
            "slug": slug,
            "version_id": version_id,
        }
        data = self._request("POST", "/downloads", json=body)

        return DownloadTicket(
            ok=bool(data.get("ok", True)),
            ticket=data["ticket"],
            ticket_id=data["ticket_id"],
            filename=data["filename"],
            size=data["size"],
            sha256=data["sha256"],
            direct_url=data["direct_url"],
            fallback_url=data.get("fallback_url"),
            expires_at=data["expires_at"],
            raw=data,
        )

    def get_download_status(self, ticket: str) -> Dict[str, Any]:
        """
        GET /downloads/{ticket}

        Статус ticket.
        """
        return self._request("GET", f"/downloads/{ticket}")

    def complete_download(
        self,
        ticket: str,
        success: bool,
        bytes_sent: int,
    ) -> Dict[str, Any]:
        """
        POST /downloads/{ticket}/complete

        Завершение ticket.
        """
        body = {
            "success": success,
            "bytes_sent": bytes_sent,
        }
        return self._request("POST", f"/downloads/{ticket}/complete", json=body)

    # -------------------- high-level helpers --------------------

    def download_zip(
        self,
        ticket: DownloadTicket,
        dest_path: str,
        use_fallback_if_direct_fails: bool = True,
        chunk_size: int = 1024 * 1024,
    ) -> str:
        """
        Скачивает ZIP по direct_url (или fallback_url) в dest_path.

        НЕ проверяет sha256 и размер — см. verify_zip().
        """
        url = ticket.direct_url
        try_urls: List[str] = [url]
        if use_fallback_if_direct_fails and ticket.fallback_url:
            try_urls.append(self._url(ticket.fallback_url))

        last_exc: Optional[Exception] = None
        for u in try_urls:
            try:
                with self.session.get(
                    u,
                    headers=self._headers(),
                    stream=True,
                    timeout=self.timeout,
                ) as resp:
                    resp.raise_for_status()
                    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
                    with open(dest_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                return dest_path
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue

        raise ZapretMarketplaceError(
            f"Failed to download ZIP from all URLs: {try_urls}. Last error: {last_exc}"
        )

    def verify_zip(
        self,
        ticket: DownloadTicket,
        file_path: str,
    ) -> bool:
        """
        Проверяет размер и sha256 скачанного файла.
        """
        if not os.path.exists(file_path):
            return False

        size = os.path.getsize(file_path)
        if size != ticket.size:
            return False

        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                sha256.update(chunk)
        digest = sha256.hexdigest()

        return digest == ticket.sha256

    def download_and_verify(
        self,
        slug: str,
        version_id: Optional[int],
        dest_path: str,
    ) -> str:
        """
        Высокоуровневый сценарий:

        1. Создать ticket.
        2. Скачать ZIP.
        3. Проверить size и sha256.
        4. Закрыть ticket.
        """
        ticket = self.create_download_ticket(slug=slug, version_id=version_id)
        self.download_zip(ticket, dest_path)

        ok = self.verify_zip(ticket, dest_path)
        self.complete_download(
            ticket=ticket.ticket,
            success=ok,
            bytes_sent=os.path.getsize(dest_path) if os.path.exists(dest_path) else 0,
        )

        if not ok:
            # если проверка не прошла — удалить файл
            if os.path.exists(dest_path):
                os.remove(dest_path)
            raise ZapretMarketplaceError("ZIP verification failed (size or sha256)")

        return dest_path


# -------------------- пример использования --------------------

if __name__ == "__main__":
    client = ZapretMarketplaceClient(
        device_id="3f7b6d91-9c51-4e4b-9d26-c6c71e7d4211",  # стабильный UUID установки
    )

    # каталог
    catalog = client.list_projects(limit=5, lang="ru")
    projects = catalog.get("projects", [])
    if not projects:
        print("Нет проектов")
    else:
        p = projects[0]
        slug = p["slug"]
        print("Первый проект:", slug, "-", p["title"])

        # полная карточка
        details = client.get_project(slug, lang="ru")
        latest = details["project"].get("latest_version")
        version_id = latest["version_id"] if latest else None

        # скачивание и проверка
        path = client.download_and_verify(slug=slug, version_id=version_id, dest_path=f"./{slug}.zip")
        print("Скачано и проверено:", path)
