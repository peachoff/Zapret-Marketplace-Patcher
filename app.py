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
from typing import Any, Dict, List, Optional

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
    """Клиент Zapret Marketplace API."""

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
        progress_cb: Optional[callable] = None,
    ) -> Path:
        urls = [ticket.direct_url]
        if ticket.fallback_url:
            urls.append(ticket.fallback_url)
        last_err: Optional[Exception] = None
        for url in urls:
            try:
                with self.session.get(
                    url, headers=self._headers(), stream=True, timeout=self.timeout
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
    compatibility: str  # "zapret" | "zapret2"
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

ALLOWED_EXTENSIONS_ZAPRET = {".bat", ".txt", ".ps1", ".bin", ".lua"}
ALLOWED_EXTENSIONS_ZAPRET2 = {".txt", ".lua"}
BLOCKED_EXTENSIONS = {".exe", ".dll", ".msi", ".cmd", ".com", ".scr", ".vbs", ".js"}


def _is_list_file(name: str, rel: str) -> bool:
    lower = name.lower()
    if rel.startswith("lists/") or rel.startswith("lists\\"):
        return True
    return any(
        lower.startswith(p) for p in ("list-", "ipset", "hosts", "exclude")
    )


def _is_bin_file(name: str, rel: str) -> bool:
    return rel.startswith("bin/") or rel.startswith("bin\\")


def _is_util_file(name: str, rel: str) -> bool:
    lower = name.lower()
    return lower.endswith(".ps1") or rel.startswith("utils/") or rel.startswith("utils\\")


def _validate_bat(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return False
    if "<html" in text or "<!doctype" in text:
        return False
    if "winws.exe" in text and "--filter" in text:
        return True
    return False


def _validate_lua(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return False
    return "function" in text or "require" in text or "os.execute" in text or len(text.strip()) > 10


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

    if compatibility == "zapret2":
        mods_dir = target_dir / "mods_zapret2"
    else:
        mods_dir = target_dir / "mods"

    mod_dir = mods_dir / slug

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_path)

        entries = list(tmp_path.rglob("*"))
        if not entries:
            raise RuntimeError("ZIP-архив пуст")

        has_root_dir = False
        root_dirs = set()
        for e in entries:
            rel = e.relative_to(tmp_path)
            if rel.parts and rel.parts[0] != ".":
                root_dirs.add(rel.parts[0])
        if len(root_dirs) == 1 and all(e.is_dir() for e in entries if e.relative_to(tmp_path).parts[0] in root_dirs):
            only_dir = list(root_dirs)[0]
            inner = tmp_path / only_dir
            if inner.is_dir():
                has_root_dir = True

        if has_root_dir:
            extract_root = tmp_path / list(root_dirs)[0]
        else:
            extract_root = tmp_path

        all_files = [f for f in extract_root.rglob("*") if f.is_file()]
        if not all_files:
            raise RuntimeError("В архиве нет файлов")

        blocked = [
            f.name
            for f in all_files
            if f.suffix.lower() in BLOCKED_EXTENSIONS
        ]
        if blocked:
            raise RuntimeError(
                f"Архив содержит заблокированные файлы: {', '.join(blocked)}"
            )

        valid_exts = ALLOWED_EXTENSIONS_ZAPRET2 if compatibility == "zapret2" else ALLOWED_EXTENSIONS_ZAPRET
        valid_files = [
            f for f in all_files
            if f.suffix.lower() in valid_exts
            or _is_list_file(f.name, str(f.relative_to(extract_root)))
            or _is_bin_file(f.name, str(f.relative_to(extract_root)))
            or _is_util_file(f.name, str(f.relative_to(extract_root)))
        ]

        if not valid_files:
            raise RuntimeError("Не найдено подходящих файлов мода")

        if mod_dir.exists():
            shutil.rmtree(mod_dir)
        mod_dir.mkdir(parents=True, exist_ok=True)

        for f in valid_files:
            rel = f.relative_to(extract_root)
            dest = mod_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dest)

        meta_path = mod_dir / "zmp-meta.json"
        meta_path.write_text(
            json.dumps(
                {
                    "slug": slug,
                    "name": title,
                    "version": version,
                    "compatibility": compatibility,
                    "author": author,
                    "installed_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
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
    if mod.compatibility == "zapret2":
        mod_dir = target_dir / "mods_zapret2" / slug
    else:
        mod_dir = target_dir / "mods" / slug
    if mod_dir.exists():
        shutil.rmtree(mod_dir, ignore_errors=True)
    config.save(config_path)
    return True


def detect_zapret_type(target_dir: Path) -> str:
    if (target_dir / "zapret2").is_dir() or (target_dir / "configs" / "zapret2").is_dir():
        return "zapret2"
    if (target_dir / "winws.exe").exists():
        return "zapret"
    bat_files = list(target_dir.glob("*.bat"))
    if bat_files:
        return "zapret"
    return "unknown"


# ─────────────────────────── GUI ──────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLOR_BG = "#1a1a2e"
COLOR_BG2 = "#16213e"
COLOR_BG3 = "#0f3460"
COLOR_ACCENT = "#e94560"
COLOR_ACCENT_HOVER = "#ff6b81"
COLOR_TEXT = "#eaeaea"
COLOR_TEXT_DIM = "#8899aa"
COLOR_SUCCESS = "#2ecc71"
COLOR_ERROR = "#e74c3c"
COLOR_CARD = "#1e2a4a"
COLOR_INPUT = "#253356"
COLOR_BORDER = "#2a3a5c"

FONT_FAMILY = "Segoe UI"
FONT_SIZE = 13
FONT_SIZE_SM = 11
FONT_SIZE_LG = 16
FONT_SIZE_XL = 22
FONT_SIZE_TITLE = 28


class ZMPApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("ZMP — Zapret Marketplace Patcher")
        self.geometry("720x860")
        self.minsize(640, 700)
        self.configure(fg_color=COLOR_BG)

        self.api = MarketplaceAPI()
        self.target_dir: Optional[Path] = None
        self.config = ZmpConfig()
        self.config_path = Path()
        self._busy = False
        self._selected_slug: Optional[str] = None
        self._mod_cards: Dict[str, ctk.CTkFrame] = {}

        self._build_ui()

    # ── UI Construction ──────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self._build_header()
        self._build_folder_picker()
        self._build_slug_input()
        self._build_mod_list()
        self._build_status_bar()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 4))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="ZMP",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE_TITLE, weight="bold"),
            text_color=COLOR_ACCENT,
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle = ctk.CTkLabel(
            header,
            text="Zapret Marketplace Patcher",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE_SM),
            text_color=COLOR_TEXT_DIM,
        )
        subtitle.grid(row=1, column=0, sticky="w")

    def _build_folder_picker(self) -> None:
        frame = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=12)
        frame.grid(row=1, column=0, sticky="ew", padx=24, pady=(12, 8))
        frame.grid_columnconfigure(1, weight=1)

        lbl = ctk.CTkLabel(
            frame,
            text="Папка Zapret",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE, weight="bold"),
            text_color=COLOR_TEXT,
        )
        lbl.grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(10, 2))

        self.folder_var = ctk.StringVar(value="Не выбрана")
        self.folder_label = ctk.CTkLabel(
            frame,
            textvariable=self.folder_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE_SM),
            text_color=COLOR_TEXT_DIM,
            anchor="w",
        )
        self.folder_label.grid(row=1, column=1, sticky="ew", padx=(0, 8))

        browse_btn = ctk.CTkButton(
            frame,
            text="Обзор…",
            width=100,
            height=32,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE_SM, weight="bold"),
            fg_color=COLOR_BG3,
            hover_color=COLOR_ACCENT,
            text_color=COLOR_TEXT,
            corner_radius=8,
            command=self._browse_folder,
        )
        browse_btn.grid(row=1, column=2, padx=(0, 10), pady=(0, 10))

        self.type_badge = ctk.CTkLabel(
            frame,
            text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE_SM),
            text_color=COLOR_SUCCESS,
        )
        self.type_badge.grid(row=2, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 10))

    def _build_slug_input(self) -> None:
        frame = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=12)
        frame.grid(row=2, column=0, sticky="ew", padx=24, pady=(4, 8))
        frame.grid_columnconfigure(1, weight=1)

        lbl = ctk.CTkLabel(
            frame,
            text="Slug мода",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE, weight="bold"),
            text_color=COLOR_TEXT,
        )
        lbl.grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(10, 2))

        hint = ctk.CTkLabel(
            frame,
            text="Краткое имя мода из Marketplace (например: shizapret_mod)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE_SM),
            text_color=COLOR_TEXT_DIM,
        )
        hint.grid(row=1, column=0, columnspan=3, sticky="w", padx=14, pady=(0, 4))

        self.slug_entry = ctk.CTkEntry(
            frame,
            placeholder_text="Введите slug…",
            height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE),
            fg_color=COLOR_INPUT,
            border_color=COLOR_BORDER,
            text_color=COLOR_TEXT,
            corner_radius=8,
        )
        self.slug_entry.grid(row=2, column=1, sticky="ew", padx=(14, 8), pady=(0, 4))
        self.slug_entry.bind("<Return>", lambda e: self._install_mod())

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=14, pady=(4, 12))
        btn_frame.grid_columnconfigure(0, weight=1)
        btn_frame.grid_columnconfigure(1, weight=1)

        self.install_btn = ctk.CTkButton(
            btn_frame,
            text="Установить",
            height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE, weight="bold"),
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            text_color="white",
            corner_radius=8,
            command=self._install_mod,
        )
        self.install_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.remove_btn = ctk.CTkButton(
            btn_frame,
            text="Удалить выбранный",
            height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE, weight="bold"),
            fg_color="#555555",
            hover_color=COLOR_ERROR,
            text_color="white",
            corner_radius=8,
            command=self._remove_mod,
        )
        self.remove_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _build_mod_list(self) -> None:
        frame = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=12)
        frame.grid(row=4, column=0, sticky="nsew", padx=24, pady=(4, 8))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        lbl = ctk.CTkLabel(
            frame,
            text="Установленные моды",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE, weight="bold"),
            text_color=COLOR_TEXT,
            anchor="w",
        )
        lbl.grid(row=0, column=0, sticky="w", padx=14, pady=(10, 4))

        self.mod_list_frame = ctk.CTkScrollableFrame(
            frame,
            fg_color="transparent",
            scrollbar_button_color=COLOR_BORDER,
            scrollbar_button_hover_color=COLOR_BG3,
        )
        self.mod_list_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 8))
        self.mod_list_frame.grid_columnconfigure(0, weight=1)

        self._refresh_mod_list()

    def _build_status_bar(self) -> None:
        self.status_var = ctk.StringVar(value="Готово")
        self._status_label = ctk.CTkLabel(
            self,
            textvariable=self.status_var,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE_SM),
            text_color=COLOR_TEXT_DIM,
            anchor="w",
        )
        self._status_label.grid(row=5, column=0, sticky="ew", padx=24, pady=(0, 14))

    # ── Mod List ─────────────────────────────────────────────────

    def _refresh_mod_list(self) -> None:
        for w in self.mod_list_frame.winfo_children():
            w.destroy()

        if not self.config.mods:
            empty = ctk.CTkLabel(
                self.mod_list_frame,
                text="Модов пока нет",
                font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE_SM),
                text_color=COLOR_TEXT_DIM,
            )
            empty.grid(row=0, column=0, pady=20)
            return

        self._selected_slug = None
        self._mod_cards = {}

        for i, mod in enumerate(self.config.mods):
            card = self._make_mod_card(mod, i)
            self._mod_cards[mod.slug] = card

    def _make_mod_card(self, mod: InstalledMod, row: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self.mod_list_frame,
            fg_color=COLOR_BG2,
            corner_radius=10,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        card.grid(row=row, column=0, sticky="ew", padx=4, pady=3)
        card.grid_columnconfigure(1, weight=1)
        card.grid_rowconfigure(0, weight=1)

        compat_color = COLOR_SUCCESS if mod.compatibility == "zapret" else "#9b59b6"
        badge = ctk.CTkLabel(
            card,
            text=mod.compatibility.upper(),
            font=ctk.CTkFont(family=FONT_FAMILY, size=9, weight="bold"),
            text_color="white",
            fg_color=compat_color,
            corner_radius=4,
            width=60,
            height=20,
        )
        badge.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=8)

        name_lbl = ctk.CTkLabel(
            card,
            text=mod.name or mod.slug,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE, weight="bold"),
            text_color=COLOR_TEXT,
            anchor="w",
        )
        name_lbl.grid(row=0, column=1, sticky="sw", padx=4, pady=(8, 0))

        info = f"v{mod.version}  •  {mod.slug}"
        if mod.author:
            info += f"  •  {mod.author}"
        info_lbl = ctk.CTkLabel(
            card,
            text=info,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FONT_SIZE_SM),
            text_color=COLOR_TEXT_DIM,
            anchor="w",
        )
        info_lbl.grid(row=1, column=1, sticky="nw", padx=4, pady=(0, 8))

        for widget in (card, badge, name_lbl, info_lbl):
            widget.bind(
                "<Button-1>",
                lambda e, s=mod.slug: self._select_mod(s),
            )

        return card

    def _select_mod(self, slug: str) -> None:
        self._selected_slug = slug
        for s, card in self._mod_cards.items():
            if s == slug:
                card.configure(border_color=COLOR_ACCENT, border_width=2)
            else:
                card.configure(border_color=COLOR_BORDER, border_width=1)

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

        ztype = detect_zapret_type(p)
        if ztype == "zapret":
            self.type_badge.configure(text="✓ Zapret (legacy) обнаружен", text_color=COLOR_SUCCESS)
        elif ztype == "zapret2":
            self.type_badge.configure(text="✓ Zapret2 обнаружен", text_color="#9b59b6")
        else:
            self.type_badge.configure(
                text="⚠ Тип не определён (моды будут установлены как zapret)",
                text_color="#f39c12",
            )

    def _install_mod(self) -> None:
        if self._busy:
            return
        slug = self.slug_entry.get().strip()
        if not slug:
            self._set_status("Введите slug мода", COLOR_ERROR)
            return
        if not self.target_dir or not self.target_dir.is_dir():
            self._set_status("Сначала выберите папку zapret", COLOR_ERROR)
            return
        if self.config.has(slug):
            self._set_status(f"Мод '{slug}' уже установлен", COLOR_ERROR)
            return

        self._busy = True
        self.install_btn.configure(state="disabled")
        self.remove_btn.configure(state="disabled")
        self._set_status(f"Получение информации о '{slug}'…", COLOR_TEXT_DIM)
        threading.Thread(target=self._do_install, args=(slug,), daemon=True).start()

    def _do_install(self, slug: str) -> None:
        try:
            info = self.api.get_project(slug)
            project = info.get("project", info)
            title = project.get("title", slug)
            latest = project.get("latest_version")
            version_id = latest["id"] if latest else None
            version = latest.get("version", "?") if latest else "?"

            self._thread_status(f"Создание тикета для '{title}' v{version}…")
            ticket = self.api.create_download_ticket(slug, version_id)

            zip_dest = Path(tempfile.gettempdir()) / f"zmp_{slug}.zip"
            self._thread_status(f"Скачивание '{title}'…")
            self.api.download_zip(ticket, zip_dest, progress_cb=self._dl_progress)

            self._thread_status("Проверка целостности…")
            if not self.api.verify_zip(ticket, zip_dest):
                raise RuntimeError("Проверка SHA-256 не пройдена")
            self.api.complete_download(ticket.ticket, True, zip_dest.stat().st_size)

            self._thread_status("Установка мода…")
            installed = install_mod_from_zip(
                zip_dest, self.target_dir, project, self.config, self.config_path
            )

            try:
                zip_dest.unlink(missing_ok=True)
            except Exception:
                pass

            self._thread_status(
                f"✓ '{installed.name}' v{installed.version} установлен!",
                COLOR_SUCCESS,
            )
            self.after(0, self._on_install_done, slug)

        except Exception as exc:
            self._thread_status(f"Ошибка: {exc}", COLOR_ERROR)
            self.after(0, self._on_busy_done)

    def _on_install_done(self, slug: str) -> None:
        self.slug_entry.delete(0, "end")
        self._refresh_mod_list()
        self._on_busy_done()

    def _on_busy_done(self) -> None:
        self._busy = False
        self.install_btn.configure(state="normal")
        self.remove_btn.configure(state="normal")

    def _remove_mod(self) -> None:
        if self._busy:
            return
        slug = self._selected_slug
        if not slug:
            self._set_status("Выберите мод для удаления", COLOR_ERROR)
            return
        if not self.target_dir:
            return

        self._busy = True
        self.install_btn.configure(state="disabled")
        self.remove_btn.configure(state="disabled")
        threading.Thread(target=self._do_remove, args=(slug,), daemon=True).start()

    def _do_remove(self, slug: str) -> None:
        try:
            ok = remove_mod(slug, self.target_dir, self.config, self.config_path)
            if ok:
                self._thread_status(f"✓ Мод '{slug}' удалён", COLOR_SUCCESS)
            else:
                self._thread_status(f"Мод '{slug}' не найден", COLOR_ERROR)
            self.after(0, self._refresh_mod_list)
            self.after(0, self._on_busy_done)
        except Exception as exc:
            self._thread_status(f"Ошибка удаления: {exc}", COLOR_ERROR)
            self.after(0, self._on_busy_done)

    def _dl_progress(self, downloaded: int, total: int) -> None:
        pct = int(downloaded / total * 100) if total else 0
        mb_d = downloaded / (1024 * 1024)
        mb_t = total / (1024 * 1024)
        self.after(
            0,
            self._set_status,
            f"Скачивание: {pct}%  ({mb_d:.1f}/{mb_t:.1f} MB)",
            COLOR_TEXT_DIM,
        )

    def _thread_status(self, text: str, color: str = COLOR_TEXT_DIM) -> None:
        self.after(0, self._set_status, text, color)

    def _set_status(self, text: str, color: str = COLOR_TEXT_DIM) -> None:
        self.status_var.set(text)
        self._status_label.configure(text_color=color)


# ─────────────────────────── Entry Point ──────────────────────────

def main() -> None:
    app = ZMPApp()
    app.mainloop()


if __name__ == "__main__":
    main()
