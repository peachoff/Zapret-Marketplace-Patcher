"""
ZMP — Zapret Marketplace Patcher
Установщик модификаций из Zapret Marketplace в чистый Zapret / Zapret2.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk
import requests
import yaml

# ─────────────────────────── API Client ───────────────────────────

API_BASE = "https://goshkow.com/api/marketplace/v1"
DEVICE_ID_FILE = Path.home() / ".zmp_device_id"


def _get_device_id() -> str:
    if DEVICE_ID_FILE.exists():
        return DEVICE_ID_FILE.read_text(encoding="utf-8").strip()
    did = str(uuid.uuid4())
    DEVICE_ID_FILE.write_text(did, encoding="utf-8")
    return did


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


class MarketplaceAPI:
    def __init__(self, device_id: Optional[str] = None) -> None:
        self.device_id = device_id or _get_device_id()
        self.session = requests.Session()
        self.timeout = 20

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h: Dict[str, str] = {"Accept": "application/json"}
        if self.device_id:
            h["X-Zapret-Device"] = self.device_id
        if extra:
            h.update(extra)
        return h

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{API_BASE}/{path.lstrip('/')}"
        resp = self.session.request(
            method,
            url,
            headers=self._headers(
                {"Content-Type": "application/json"} if json_body is not None else None
            ),
            params=params,
            json=json_body,
            timeout=self.timeout,
        )
        data = resp.json()
        if isinstance(data, dict) and data.get("ok") is False:
            raise RuntimeError(data.get("error", "unknown_error"))
        return data

    def list_projects(
        self,
        q: Optional[str] = None,
        compatibility: Optional[str] = None,
        page: int = 1,
        limit: int = 20,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {"page": page, "limit": limit, "lang": "ru"}
        if q:
            params["q"] = q
        if compatibility:
            params["compatibility"] = compatibility
        return self._request("GET", "projects", params=params)

    def get_project(self, slug: str) -> Dict[str, Any]:
        return self._request("GET", f"projects/{slug}", params={"lang": "ru"})

    def create_download_ticket(
        self, slug: str, version_id: Optional[int] = None
    ) -> DownloadTicket:
        body: Dict[str, Any] = {"slug": slug, "version_id": version_id}
        data = self._request("POST", "downloads", json_body=body)
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
        )

    def complete_download(self, ticket: str, success: bool, bytes_sent: int) -> None:
        self._request(
            "POST",
            f"downloads/{ticket}/complete",
            json_body={"success": success, "bytes_sent": bytes_sent},
        )

    def download_zip(
        self,
        ticket: DownloadTicket,
        dest: Path,
        progress_cb: Optional[Callable[[int, int], None]] = None,
    ) -> Path:
        urls = [ticket.direct_url]
        if ticket.fallback_url:
            urls.append(ticket.fallback_url)
        last_err: Optional[Exception] = None
        for url in urls:
            try:
                with self.session.get(
                    url, headers=self._headers(), stream=True, timeout=60
                ) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("content-length", 0)) or ticket.size
                    downloaded = 0
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 256):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if progress_cb and total:
                                    progress_cb(downloaded, total)
                return dest
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(f"Ошибка скачивания: {last_err}")

    def verify_zip(self, ticket: DownloadTicket, path: Path) -> bool:
        if not path.exists():
            return False
        if path.stat().st_size != ticket.size:
            return False
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest() == ticket.sha256


# ─────────────────────────── Config (zmp.yml) ─────────────────────

@dataclass
class InstalledMod:
    slug: str
    name: str
    version: str
    compatibility: str
    installed_at: str
    author: str = ""
    description: str = ""


@dataclass
class ZmpConfig:
    mods: List[InstalledMod] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "ZmpConfig":
        if not path.exists():
            return cls()
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        mods = []
        for m in data.get("mods", []):
            mods.append(
                InstalledMod(
                    slug=m.get("slug", ""),
                    name=m.get("name", ""),
                    version=m.get("version", ""),
                    compatibility=m.get("compatibility", "zapret"),
                    installed_at=m.get("installed_at", ""),
                    author=m.get("author", ""),
                    description=m.get("description", ""),
                )
            )
        return cls(mods=mods)

    def save(self, path: Path) -> None:
        data = {
            "mods": [
                {
                    "slug": m.slug,
                    "name": m.name,
                    "version": m.version,
                    "compatibility": m.compatibility,
                    "installed_at": m.installed_at,
                    "author": m.author,
                    "description": m.description,
                }
                for m in self.mods
            ]
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def has(self, slug: str) -> bool:
        return any(m.slug == slug for m in self.mods)

    def add(self, mod: InstalledMod) -> None:
        self.mods = [m for m in self.mods if m.slug != mod.slug]
        self.mods.append(mod)

    def remove(self, slug: str) -> Optional[InstalledMod]:
        for i, m in enumerate(self.mods):
            if m.slug == slug:
                return self.mods.pop(i)
        return None


# ─────────────────────────── Mod Installer ────────────────────────

BLOCKED_EXTENSIONS = {".exe", ".dll", ".msi", ".cmd", ".com", ".scr", ".vbs", ".js"}


def _merge_list_file(target: Path, source: Path) -> int:
    """Append new lines from source into target. Returns count of added lines."""
    existing_lines: set[str] = set()
    if target.exists():
        existing_lines = {
            line.rstrip("\r\n")
            for line in target.read_text(encoding="utf-8", errors="ignore").splitlines()
        }

    new_lines: list[str] = []
    for line in source.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.rstrip("\r\n")
        if stripped and stripped not in existing_lines:
            new_lines.append(stripped)
            existing_lines.add(stripped)

    if new_lines:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            for line in new_lines:
                f.write(line + "\n")

    return len(new_lines)


def _unmerge_list_file(target: Path, lines_to_remove: set[str]) -> None:
    """Remove specific lines from target list file."""
    if not target.exists():
        return
    current = target.read_text(encoding="utf-8", errors="ignore").splitlines()
    kept = [line for line in current if line.rstrip("\r\n") not in lines_to_remove]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(kept) + "\n" if kept else "", encoding="utf-8")


def install_mod_from_zip(
    zip_path: Path,
    target_dir: Path,
    project_info: Dict[str, Any],
    config: ZmpConfig,
    config_path: Path,
) -> InstalledMod:
    compatibility = project_info.get("compatibility", "zapret")
    slug = project_info["slug"]
    title = project_info.get("title", slug)
    author = project_info.get("author", "")
    summary = project_info.get("summary", "")
    latest = project_info.get("latest_version", {})
    version = latest.get("version", "0.0.0") if latest else "0.0.0"

    mod_dir = target_dir / "mods" / slug

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_path)

        all_files = [f for f in tmp_path.rglob("*") if f.is_file()]
        if not all_files:
            raise RuntimeError("ZIP-архив пуст")

        blocked = [f.name for f in all_files if f.suffix.lower() in BLOCKED_EXTENSIONS]
        if blocked:
            raise RuntimeError(
                f"Архив содержит заблокированные файлы: {', '.join(blocked)}"
            )

        if mod_dir.exists():
            shutil.rmtree(mod_dir)
        mod_dir.mkdir(parents=True, exist_ok=True)

        copied_bats: list[str] = []
        merged_lists: Dict[str, List[str]] = {}

        for f in all_files:
            rel = f.relative_to(tmp_path)
            name = rel.name
            suffix = rel.suffix.lower()

            if suffix == ".bat":
                dest = target_dir / name
                shutil.copy2(f, dest)
                copied_bats.append(name)

            elif suffix == ".txt":
                dest = target_dir / rel
                count = _merge_list_file(dest, f)
                if count > 0:
                    merged_lists[str(rel)] = [
                        line.rstrip("\r\n")
                        for line in f.read_text(encoding="utf-8", errors="ignore").splitlines()
                        if line.strip()
                    ]

            else:
                dest = mod_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)

        meta = {
            "slug": slug,
            "name": title,
            "version": version,
            "compatibility": compatibility,
            "author": author,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "bat_files": copied_bats,
            "merged_lists": merged_lists,
        }
        (mod_dir / "zmp-meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    installed = InstalledMod(
        slug=slug,
        name=title,
        version=version,
        compatibility=compatibility,
        installed_at=datetime.now(timezone.utc).isoformat(),
        author=author,
        description=summary,
    )
    config.add(installed)
    config.save(config_path)
    return installed


def remove_mod(
    slug: str,
    target_dir: Path,
    config: ZmpConfig,
    config_path: Path,
) -> bool:
    mod = config.remove(slug)
    if mod is None:
        return False

    mod_dir = target_dir / "mods" / slug
    meta_path = mod_dir / "zmp-meta.json"

    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            for bat_name in meta.get("bat_files", []):
                bat_file = target_dir / bat_name
                if bat_file.exists():
                    bat_file.unlink()
            for list_rel, lines in meta.get("merged_lists", {}).items():
                _unmerge_list_file(target_dir / list_rel, set(lines))
        except Exception:
            pass

    if mod_dir.exists():
        shutil.rmtree(mod_dir, ignore_errors=True)

    config.save(config_path)
    return True


def detect_zapret_type(target_dir: Path) -> str:
    if (target_dir / "zapret2").is_dir() or (target_dir / "configs" / "zapret2").is_dir():
        return "zapret2"
    if (target_dir / "winws.exe").exists():
        return "zapret"
    if list(target_dir.glob("*.bat")):
        return "zapret"
    return "unknown"


# ─────────────────────────── GUI ──────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C_BG = "#1a1a2e"
C_CARD = "#1e2a4a"
C_BG2 = "#16213e"
C_BG3 = "#0f3460"
C_ACCENT = "#e94560"
C_ACCENT2 = "#ff6b81"
C_TEXT = "#eaeaea"
C_DIM = "#8899aa"
C_OK = "#2ecc71"
C_ERR = "#e74c3c"
C_PURPLE = "#9b59b6"
C_WARN = "#f39c12"
C_INPUT = "#253356"
C_BORDER = "#2a3a5c"
FONT = "Segoe UI"


class ZMPApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ZMP")
        self.geometry("620x680")
        self.minsize(520, 520)
        self.configure(fg_color=C_BG)

        self.api = MarketplaceAPI()
        self.target_dir: Optional[Path] = None
        self.config = ZmpConfig()
        self.config_path = Path()
        self._busy = False
        self._selected_slug: Optional[str] = None
        self._mod_cards: Dict[str, ctk.CTkFrame] = {}
        self._catalog_items: List[Dict[str, Any]] = []
        self._catalog_cards: List[ctk.CTkFrame] = []

        self._build_ui()

    # ── Shared top bar ───────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_topbar()
        self._build_tabs()
        self._build_status_bar()

    def _build_topbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=C_CARD, corner_radius=0, height=56)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        bar.grid_propagate(False)

        title = ctk.CTkLabel(
            bar, text="ZMP",
            font=ctk.CTkFont(family=FONT, size=20, weight="bold"),
            text_color=C_ACCENT,
        )
        title.grid(row=0, column=0, padx=16, pady=8, sticky="w")

        self.folder_var = ctk.StringVar(value="Папка не выбрана")
        folder_lbl = ctk.CTkLabel(
            bar, textvariable=self.folder_var,
            font=ctk.CTkFont(family=FONT, size=11),
            text_color=C_DIM, anchor="w",
        )
        folder_lbl.grid(row=0, column=1, sticky="ew", padx=4)

        browse_btn = ctk.CTkButton(
            bar, text="Обзор", width=70, height=28,
            font=ctk.CTkFont(family=FONT, size=11, weight="bold"),
            fg_color=C_BG3, hover_color=C_ACCENT, text_color=C_TEXT,
            corner_radius=6, command=self._browse_folder,
        )
        browse_btn.grid(row=0, column=2, padx=(0, 12), pady=8, sticky="e")

    def _build_tabs(self) -> None:
        self.tabview = ctk.CTkTabview(
            self, fg_color="transparent",
            segmented_button_fg_color=C_CARD,
            segmented_button_selected_color=C_ACCENT,
            segmented_button_selected_hover_color=C_ACCENT2,
            segmented_button_unselected_color=C_BG2,
            text_color=C_TEXT,
        )
        self.tabview.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 0))

        self.tab_install = self.tabview.add("Установка")
        self.tab_catalog = self.tabview.add("Каталог")

        self._build_install_tab()
        self._build_catalog_tab()

    def _build_status_bar(self) -> None:
        self.status_var = ctk.StringVar(value="Готово")
        self._status_lbl = ctk.CTkLabel(
            self, textvariable=self.status_var,
            font=ctk.CTkFont(family=FONT, size=10),
            text_color=C_DIM, anchor="w",
        )
        self._status_lbl.grid(row=3, column=0, sticky="ew", padx=12, pady=(2, 6))

    # ── Install tab ──────────────────────────────────────────────

    def _build_install_tab(self) -> None:
        tab = self.tab_install
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        input_frame = ctk.CTkFrame(tab, fg_color=C_CARD, corner_radius=10)
        input_frame.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 6))
        input_frame.grid_columnconfigure(1, weight=1)

        lbl = ctk.CTkLabel(
            input_frame, text="Slug:",
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            text_color=C_TEXT,
        )
        lbl.grid(row=0, column=0, padx=(10, 4), pady=8)

        self.slug_entry = ctk.CTkEntry(
            input_frame, placeholder_text="shizapret_mod", height=30,
            font=ctk.CTkFont(family=FONT, size=12),
            fg_color=C_INPUT, border_color=C_BORDER, text_color=C_TEXT,
            corner_radius=6,
        )
        self.slug_entry.grid(row=0, column=1, sticky="ew", pady=8)
        self.slug_entry.bind("<Return>", lambda e: self._install_mod())

        self.install_btn = ctk.CTkButton(
            input_frame, text="Установить", width=90, height=30,
            font=ctk.CTkFont(family=FONT, size=11, weight="bold"),
            fg_color=C_ACCENT, hover_color=C_ACCENT2, text_color="white",
            corner_radius=6, command=self._install_mod,
        )
        self.install_btn.grid(row=0, column=2, padx=(4, 10), pady=8)

        self.remove_btn = ctk.CTkButton(
            input_frame, text="Удалить", width=70, height=30,
            font=ctk.CTkFont(family=FONT, size=11, weight="bold"),
            fg_color="#555", hover_color=C_ERR, text_color="white",
            corner_radius=6, command=self._remove_mod,
        )
        self.remove_btn.grid(row=0, column=3, padx=(0, 10), pady=8)

        self.mod_list_frame = ctk.CTkScrollableFrame(
            tab, fg_color=C_CARD, corner_radius=10,
            scrollbar_button_color=C_BORDER,
            scrollbar_button_hover_color=C_BG3,
        )
        self.mod_list_frame.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.mod_list_frame.grid_columnconfigure(0, weight=1)

        self._refresh_mod_list()

    # ── Catalog tab ──────────────────────────────────────────────

    def _build_catalog_tab(self) -> None:
        tab = self.tab_catalog
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        search_frame = ctk.CTkFrame(tab, fg_color=C_CARD, corner_radius=10)
        search_frame.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 6))
        search_frame.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            search_frame, placeholder_text="Поиск в каталоге…", height=30,
            font=ctk.CTkFont(family=FONT, size=12),
            fg_color=C_INPUT, border_color=C_BORDER, text_color=C_TEXT,
            corner_radius=6,
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        self.search_entry.bind("<Return>", lambda e: self._search_catalog())

        search_btn = ctk.CTkButton(
            search_frame, text="Найти", width=70, height=30,
            font=ctk.CTkFont(family=FONT, size=11, weight="bold"),
            fg_color=C_BG3, hover_color=C_ACCENT, text_color=C_TEXT,
            corner_radius=6, command=self._search_catalog,
        )
        search_btn.grid(row=0, column=1, padx=(4, 10), pady=8)

        self.catalog_frame = ctk.CTkScrollableFrame(
            tab, fg_color=C_CARD, corner_radius=10,
            scrollbar_button_color=C_BORDER,
            scrollbar_button_hover_color=C_BG3,
        )
        self.catalog_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        self.catalog_frame.grid_columnconfigure(0, weight=1)

        self._load_catalog()

    # ── Mod list (installed) ─────────────────────────────────────

    def _refresh_mod_list(self) -> None:
        for w in self.mod_list_frame.winfo_children():
            w.destroy()
        self._selected_slug = None
        self._mod_cards = {}

        if not self.config.mods:
            ctk.CTkLabel(
                self.mod_list_frame, text="Модов пока нет",
                font=ctk.CTkFont(family=FONT, size=11), text_color=C_DIM,
            ).grid(row=0, column=0, pady=16)
            return

        for i, mod in enumerate(self.config.mods):
            self._make_installed_card(mod, i)

    def _make_installed_card(self, mod: InstalledMod, row: int) -> None:
        card = ctk.CTkFrame(
            self.mod_list_frame, fg_color=C_BG2, corner_radius=8,
            border_width=1, border_color=C_BORDER,
        )
        card.grid(row=row, column=0, sticky="ew", padx=4, pady=2)
        card.grid_columnconfigure(1, weight=1)

        color = C_OK if mod.compatibility == "zapret" else C_PURPLE
        badge = ctk.CTkLabel(
            card, text=mod.compatibility.upper(),
            font=ctk.CTkFont(family=FONT, size=8, weight="bold"),
            text_color="white", fg_color=color,
            corner_radius=3, width=50, height=18,
        )
        badge.grid(row=0, column=0, rowspan=2, padx=(8, 6), pady=6)

        ctk.CTkLabel(
            card, text=mod.name or mod.slug,
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            text_color=C_TEXT, anchor="w",
        ).grid(row=0, column=1, sticky="sw", padx=4, pady=(6, 0))

        info = f"v{mod.version}  {mod.slug}"
        if mod.author:
            info += f"  {mod.author}"
        ctk.CTkLabel(
            card, text=info,
            font=ctk.CTkFont(family=FONT, size=10),
            text_color=C_DIM, anchor="w",
        ).grid(row=1, column=1, sticky="nw", padx=4, pady=(0, 6))

        for w in (card, badge):
            w.bind("<Button-1>", lambda e, s=mod.slug: self._select_mod(s))

    def _select_mod(self, slug: str) -> None:
        self._selected_slug = slug
        for s, card in self._mod_cards.items():
            card.configure(
                border_color=C_ACCENT if s == slug else C_BORDER,
                border_width=2 if s == slug else 1,
            )

    # ── Catalog ──────────────────────────────────────────────────

    def _load_catalog(self) -> None:
        threading.Thread(target=self._do_load_catalog, daemon=True).start()

    def _do_load_catalog(self) -> None:
        try:
            data = self.api.list_projects(limit=50)
            items = data.get("projects", [])
            self.after(0, self._render_catalog, items)
        except Exception as e:
            self.after(0, self._set_status, f"Ошибка загрузки каталога: {e}", C_ERR)

    def _search_catalog(self) -> None:
        q = self.search_entry.get().strip()
        threading.Thread(target=self._do_search_catalog, args=(q,), daemon=True).start()

    def _do_search_catalog(self, q: str) -> None:
        try:
            data = self.api.list_projects(q=q if q else None, limit=50)
            items = data.get("projects", [])
            self.after(0, self._render_catalog, items)
        except Exception as e:
            self.after(0, self._set_status, f"Ошибка поиска: {e}", C_ERR)

    def _render_catalog(self, items: List[Dict[str, Any]]) -> None:
        for w in self.catalog_frame.winfo_children():
            w.destroy()
        self._catalog_items = items
        self._catalog_cards = []

        if not items:
            ctk.CTkLabel(
                self.catalog_frame, text="Ничего не найдено",
                font=ctk.CTkFont(family=FONT, size=11), text_color=C_DIM,
            ).grid(row=0, column=0, pady=16)
            return

        for i, proj in enumerate(items):
            self._make_catalog_card(proj, i)

    def _make_catalog_card(self, proj: Dict[str, Any], row: int) -> None:
        slug = proj.get("slug", "")
        title = proj.get("title", slug)
        author = proj.get("author", "")
        summary = proj.get("summary", "")
        compat = proj.get("compatibility", "zapret")
        downloads = proj.get("downloads_compact", "0")
        latest = proj.get("latest_version", {})
        version = latest.get("version", "?") if latest else "?"
        file_size = latest.get("file_size_label", "") if latest else ""

        card = ctk.CTkFrame(
            self.catalog_frame, fg_color=C_BG2, corner_radius=8,
            border_width=1, border_color=C_BORDER,
        )
        card.grid(row=row, column=0, sticky="ew", padx=4, pady=2)
        card.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 0))
        top.grid_columnconfigure(0, weight=1)

        color = C_OK if compat == "zapret" else C_PURPLE
        ctk.CTkLabel(
            top, text=compat.upper(),
            font=ctk.CTkFont(family=FONT, size=8, weight="bold"),
            text_color="white", fg_color=color,
            corner_radius=3, width=50, height=18,
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            top, text=title,
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            text_color=C_TEXT, anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(6, 0))

        ctk.CTkLabel(
            top, text=f"v{version}  {file_size}  {downloads} загр.",
            font=ctk.CTkFont(family=FONT, size=9),
            text_color=C_DIM, anchor="e",
        ).grid(row=0, column=2, sticky="e")

        if summary:
            ctk.CTkLabel(
                card, text=summary,
                font=ctk.CTkFont(family=FONT, size=10),
                text_color=C_DIM, anchor="w", wraplength=440,
            ).grid(row=1, column=0, sticky="ew", padx=8, pady=(2, 0))

        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.grid(row=2, column=0, sticky="ew", padx=8, pady=(2, 6))
        bottom.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bottom, text=author,
            font=ctk.CTkFont(family=FONT, size=9),
            text_color=C_DIM, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        is_installed = self.config.has(slug)
        btn_text = "Установлено" if is_installed else "Установить"
        btn_color = "#444" if is_installed else C_ACCENT
        btn_hover = btn_color

        install_btn = ctk.CTkButton(
            bottom, text=btn_text, width=85, height=24,
            font=ctk.CTkFont(family=FONT, size=10, weight="bold"),
            fg_color=btn_color, hover_color=btn_hover,
            text_color="white", corner_radius=5,
            state="disabled" if is_installed else "normal",
            command=lambda s=slug: self._install_from_catalog(s),
        )
        install_btn.grid(row=0, column=1, sticky="e")

        self._catalog_cards.append(card)

    def _install_from_catalog(self, slug: str) -> None:
        if self._busy or not self.target_dir:
            if not self.target_dir:
                self._set_status("Сначала выберите папку zapret", C_ERR)
            return
        self.slug_entry.delete(0, "end")
        self.slug_entry.insert(0, slug)
        self.tabview.set("Установка")
        self._install_mod()

    # ── Actions ──────────────────────────────────────────────────

    def _browse_folder(self) -> None:
        from tkinter import filedialog
        d = filedialog.askdirectory(title="Выберите папку zapret")
        if not d:
            return
        p = Path(d)
        self.target_dir = p
        self.folder_var.set(str(p))
        self.config_path = p / "zmp.yml"
        self.config = ZmpConfig.load(self.config_path)
        self._refresh_mod_list()
        self._set_status(f"Загружено {len(self.config.mods)} мод(ов)", C_OK)

    def _install_mod(self) -> None:
        if self._busy:
            return
        slug = self.slug_entry.get().strip()
        if not slug:
            self._set_status("Введите slug мода", C_ERR)
            return
        if not self.target_dir or not self.target_dir.is_dir():
            self._set_status("Сначала выберите папку zapret", C_ERR)
            return
        if self.config.has(slug):
            self._set_status(f"'{slug}' уже установлен", C_ERR)
            return

        self._busy = True
        self._set_buttons_state("disabled")
        self._set_status(f"Запрос '{slug}'…", C_DIM)
        threading.Thread(target=self._do_install, args=(slug,), daemon=True).start()

    def _do_install(self, slug: str) -> None:
        try:
            info = self.api.get_project(slug)
            project = info.get("project", info)
            title = project.get("title", slug)
            latest = project.get("latest_version")
            vid = latest["id"] if latest else None
            ver = latest.get("version", "?") if latest else "?"

            self._thread_status(f"Тикет для '{title}' v{ver}…")
            ticket = self.api.create_download_ticket(slug, vid)

            zip_dest = Path(tempfile.gettempdir()) / f"zmp_{slug}.zip"
            self._thread_status(f"Скачивание '{title}'…")
            self.api.download_zip(ticket, zip_dest, progress_cb=self._dl_progress)

            self._thread_status("SHA-256 проверка…")
            if not self.api.verify_zip(ticket, zip_dest):
                raise RuntimeError("SHA-256 не совпадает")
            self.api.complete_download(ticket.ticket, True, zip_dest.stat().st_size)

            self._thread_status("Распаковка…")
            installed = install_mod_from_zip(
                zip_dest, self.target_dir, project, self.config, self.config_path
            )

            try:
                zip_dest.unlink(missing_ok=True)
            except Exception:
                pass

            self._thread_status(f"✓ '{installed.name}' v{installed.version}", C_OK)
            self.after(0, self._on_install_done, slug)

        except Exception as exc:
            self._thread_status(f"Ошибка: {exc}", C_ERR)
            self.after(0, self._on_busy_done)

    def _on_install_done(self, slug: str) -> None:
        self.slug_entry.delete(0, "end")
        self._refresh_mod_list()
        self._render_catalog(self._catalog_items)
        self._on_busy_done()

    def _on_busy_done(self) -> None:
        self._busy = False
        self._set_buttons_state("normal")

    def _set_buttons_state(self, state: str) -> None:
        self.install_btn.configure(state=state)
        self.remove_btn.configure(state=state)

    def _remove_mod(self) -> None:
        if self._busy:
            return
        slug = self._selected_slug
        if not slug:
            self._set_status("Выберите мод в списке", C_ERR)
            return
        if not self.target_dir:
            return

        self._busy = True
        self._set_buttons_state("disabled")
        threading.Thread(target=self._do_remove, args=(slug,), daemon=True).start()

    def _do_remove(self, slug: str) -> None:
        try:
            ok = remove_mod(slug, self.target_dir, self.config, self.config_path)
            if ok:
                self._thread_status(f"✓ '{slug}' удалён", C_OK)
            else:
                self._thread_status(f"'{slug}' не найден", C_ERR)
            self.after(0, self._refresh_mod_list)
            self.after(0, self._render_catalog, self._catalog_items)
            self.after(0, self._on_busy_done)
        except Exception as exc:
            self._thread_status(f"Ошибка: {exc}", C_ERR)
            self.after(0, self._on_busy_done)

    def _dl_progress(self, downloaded: int, total: int) -> None:
        if not total:
            return
        pct = int(downloaded / total * 100)
        mb_d = downloaded / (1024 * 1024)
        mb_t = total / (1024 * 1024)
        self.after(0, self._set_status, f"Скачивание {pct}%  {mb_d:.1f}/{mb_t:.1f} MB", C_DIM)

    def _thread_status(self, text: str, color: str = C_DIM) -> None:
        self.after(0, self._set_status, text, color)

    def _set_status(self, text: str, color: str = C_DIM) -> None:
        self.status_var.set(text)
        self._status_lbl.configure(text_color=color)


# ─────────────────────────── Entry Point ──────────────────────────

def main() -> None:
    app = ZMPApp()
    app.mainloop()


if __name__ == "__main__":
    main()
