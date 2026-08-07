"""ZMP — GitHub Releases based mod catalog and downloader.

Each mod in a mod repository is published as its own GitHub release:
the release tag doubles as the mod slug, the release body as the
description and a ``*.zip`` asset as the installable archive.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

API_BASE = "https://api.github.com"


class GitHubClientError(Exception):
    """Базовое исключение GitHub-клиента."""


@dataclass
class RepoRef:
    owner: str
    repo: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"

    def __str__(self) -> str:
        return self.full_name


_REPO_RE = re.compile(r"^(?:https?://)?(?:www\.)?github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def parse_repo(value: str) -> RepoRef:
    """Разбирает ссылку на репозиторий или ``owner/repo`` в ``RepoRef``."""
    raw = (value or "").strip().strip("/")
    if not raw:
        raise GitHubClientError("Укажите репозиторий, например https://github.com/peachoff/Zapret-Mods")
    m = _REPO_RE.match(raw)
    if not m:
        # allow paths like /tree/main or /releases by taking first two segments
        parts = [p for p in raw.split("/") if p and p != "tree" and p != "releases" and p != "blob"]
        if len(parts) >= 2 and "." not in parts[0] and "." not in parts[1]:
            owner, repo = parts[0], parts[1].removesuffix(".git")
        else:
            raise GitHubClientError(f"Не удалось разобрать репозиторий: {value}")
    else:
        owner, repo = m.group(1), m.group(2)
    if not owner or not repo:
        raise GitHubClientError(f"Не удалось разобрать репозиторий: {value}")
    return RepoRef(owner=owner, repo=repo)


def _size_label(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} МБ"
    if size >= 1024:
        return f"{size / 1024:.0f} КБ"
    return f"{size} Б"


def _clean_body(body: Optional[str]) -> str:
    if not body:
        return ""
    lines: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        if s.startswith(("|", "---", "```", "![", "```", "- ")):
            if s.startswith("```"):
                continue
        lines.append(s)
    text = " ".join(l for l in lines if l).strip()
    return text


class GitHubClient:
    def __init__(self, token: Optional[str] = None, timeout: float = 20) -> None:
        self.token = token or os.environ.get("ZMP_GITHUB_TOKEN")
        self.session = requests.Session()
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            resp = self.session.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        except requests.RequestException as e:
            raise GitHubClientError(f"Сеть недоступна: {e}")
        if resp.status_code == 404:
            raise GitHubClientError("Репозиторий не найден (404)")
        if resp.status_code == 403:
            raise GitHubClientError(
                "GitHub API ограничил запросы (rate limit). Попробуйте позже или "
                "задайте токен через переменную окружения ZMP_GITHUB_TOKEN"
            )
        if resp.status_code >= 400:
            raise GitHubClientError(f"GitHub API ошибка: {resp.status_code}")
        try:
            return resp.json()
        except ValueError:
            raise GitHubClientError("GitHub API вернул некорректный ответ")

    def get_repo_info(self, ref: RepoRef) -> Dict[str, Any]:
        data = self._get_json(f"{API_BASE}/repos/{ref.owner}/{ref.repo}")
        return {
            "owner": ref.owner,
            "repo": ref.repo,
            "name": data.get("name", ref.repo),
            "full_name": data.get("full_name", ref.full_name),
            "description": data.get("description") or "",
            "html_url": data.get("html_url", ref.url),
            "avatar_url": (data.get("owner") or {}).get("avatar_url"),
            "default_branch": data.get("default_branch", "main"),
        }

    def list_mods(self, ref: RepoRef) -> List[Dict[str, Any]]:
        """Возвращает каталог модов из релизов репозитория."""
        releases: List[Dict[str, Any]] = []
        page = 1
        while True:
            data = self._get_json(
                f"{API_BASE}/repos/{ref.owner}/{ref.repo}/releases",
                params={"per_page": 100, "page": page},
            )
            if not isinstance(data, list):
                break
            releases.extend(data)
            if len(data) < 100:
                break
            page += 1

        items: List[Dict[str, Any]] = []
        for r in releases:
            if r.get("draft"):
                continue
            item = self._release_to_mod(r, ref)
            if item:
                items.append(item)
        return items

    @staticmethod
    def _pick_asset(release: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        assets = release.get("assets") or []
        zips = [a for a in assets if a.get("name", "").lower().endswith(".zip")]
        if not zips:
            return None
        # prefer the plain "<tag>.zip" (zapret-discord-youtube variant)
        plain = [a for a in zips if not a["name"].lower().endswith("_hub.zip")]
        if plain:
            return plain[0]
        return zips[0]

    def _release_to_mod(self, release: Dict[str, Any], ref: RepoRef) -> Optional[Dict[str, Any]]:
        tag = release.get("tag_name")
        if not tag:
            return None
        asset = self._pick_asset(release)
        if not asset:
            return None
        name = release.get("name") or tag
        published = (release.get("published_at") or "")[:10] or "latest"
        return {
            "slug": tag,
            "title": name,
            "summary": _clean_body(release.get("body")),
            "author": ref.owner,
            "compatibility": "zapret",
            "version": published,
            "latest_version": {"version": published},
            "icon_url": None,
            "downloads_compact": str(asset.get("download_count", 0)),
            "file_size_label": _size_label(asset.get("size", 0)),
            "_repo": ref.full_name,
            "_repo_url": ref.url,
            "_release_url": release.get("html_url", ""),
            "_download_url": asset.get("browser_download_url", ""),
            "released_at": published,
        }

    def download_zip(self, url: str, dest: Path) -> Path:
        last_err: Optional[Exception] = None
        try:
            with self.session.get(
                url, headers=self._headers(), stream=True, timeout=120
            ) as r:
                r.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(256 * 1024):
                        if chunk:
                            f.write(chunk)
                return dest
        except Exception as e:  # noqa: BLE001
            last_err = e
        raise GitHubClientError(f"Ошибка скачивания архива: {last_err}")
