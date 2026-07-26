"""ZMP — CustomTkinter native UI."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import io
import math
import random
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import Any

import customtkinter as ctk
from PIL import Image, ImageDraw

from .api_client import MarketplaceAPI
from .installer import install_mod, remove_mod, load_config

# ── Theme ────────────────────────────────────────────────────

def _hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"

def _clamp(v: int) -> int:
    return max(0, min(255, v))

def _derive_accent(r: int, g: int, b: int) -> tuple[str, str, str]:
    hex_color = _hex(r, g, b)
    lr = _clamp(int(r + (255 - r) * 0.18))
    lg = _clamp(int(g + (255 - g) * 0.18))
    lb = _clamp(int(b + (255 - b) * 0.18))
    hover = _hex(lr, lg, lb)
    dr = _clamp(int(r * 0.22))
    dg = _clamp(int(g * 0.22))
    db = _clamp(int(b * 0.25 + 18))
    dim = _hex(dr, dg, db)
    return hex_color, hover, dim

def _get_system_accent() -> tuple[int, int, int]:
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent",
            )
            val, _ = winreg.QueryValueEx(key, "AccentColorMenu")
            winreg.CloseKey(key)
            val = int(val)
            r = val & 0xFF
            g = (val >> 8) & 0xFF
            b = (val >> 16) & 0xFF
            return r, g, b
        except Exception:
            return (0, 120, 215)
    else:
        try:
            import subprocess
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "accent-color"],
                capture_output=True, text=True, timeout=3,
            )
            raw = result.stdout.strip().strip("'")
            palette = {
                "blue":   (53, 132, 228),
                "teal":   (0, 167, 160),
                "green":  (87, 187, 138),
                "yellow": (229, 182, 0),
                "orange": (230, 125, 42),
                "red":    (224, 51, 51),
                "pink":   (214, 97, 156),
                "purple": (149, 97, 226),
                "slate":  (101, 115, 131),
            }
            if raw in palette:
                return palette[raw]
        except Exception:
            pass
        return (random.randint(40, 220), random.randint(40, 220), random.randint(40, 220))

_accent_r, _accent_g, _accent_b = _get_system_accent()
ACCENT, ACCENT_HOVER, ACCENT_DIM = _derive_accent(_accent_r, _accent_g, _accent_b)
BG = "#1e1e1e"
BG_ALT = "#252526"
SURFACE = "#2d2d2d"
SURFACE_HOVER = "#353535"
DIVIDER = "#3c3c3c"
TEXT = "#e0e0e0"
TEXT_SEC = "#858585"
SUCCESS = "#4ec9b0"
ERROR = "#f44747"

FONT_DIR = Path(__file__).parent / "fonts"
FONT_FILE_R = FONT_DIR / "JetBrainsMono-Regular.ttf"
FONT_FILE_B = FONT_DIR / "JetBrainsMono-Bold.ttf"
FONT_FILE_S = FONT_DIR / "JetBrainsMono-SemiBold.ttf"

FONT = "Segoe UI"
FONT_SIZE = 13

FRAMES_PER_SEC = 60
ANIM_SPEED = 0.08
ANIM_STEP_MS = int(1000 / FRAMES_PER_SEC)


def _load_font() -> None:
    global FONT
    try:
        gdi32 = ctypes.windll.gdi32
        for f in [FONT_FILE_R, FONT_FILE_B, FONT_FILE_S]:
            if f.exists():
                gdi32.AddFontResourceW(str(f.resolve()))
        root = tk._default_root or tk.Tk()
        families = set(root.tk.call("font", "families"))
        if "JetBrains Mono" in families:
            FONT = "JetBrains Mono"
    except Exception:
        pass


def _ease_out_cubic(t: float) -> float:
    return 1.0 - pow(1.0 - t, 3)


def _ease_out_quint(t: float) -> float:
    return 1.0 - pow(1.0 - t, 5)


def _placeholder_icon(size: int = 44) -> Image.Image:
    img = Image.new("RGBA", (size, size), (37, 37, 37, 255))
    draw = ImageDraw.Draw(img)
    s = size
    cx, cy = s // 2, s // 2
    r = s // 6
    draw.ellipse(
        [cx - r - 2, cy - r - 2, cx + r + 2, cy + r + 2],
        fill=(70, 70, 70, 255),
    )
    return img


def _dl_icon(url: str, size: int = 44) -> Image.Image | None:
    try:
        import requests as req
        r = req.get(url, timeout=8)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")
        img = img.resize((size * 2, size * 2), Image.Resampling.LANCZOS)
        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, img.size[0] - 1, img.size[1] - 1), fill=255)
        img.putalpha(mask)
        return img
    except Exception:
        return None


# ── Animated value helper ────────────────────────────────────

class Anim:
    def __init__(self, app: ctk.CTk, on_change):
        self._app = app
        self._on_change = on_change
        self._from = 0.0
        self._to = 0.0
        self._current = 0.0
        self._progress = 0.0
        self._running = False

    @property
    def value(self) -> float:
        return self._current

    def animate(self, target: float, duration_ms: int = 250) -> None:
        self._from = self._current
        self._to = target
        self._progress = 0.0
        total_steps = max(1, duration_ms // ANIM_STEP_MS)
        self._step_size = 1.0 / total_steps
        if not self._running:
            self._running = True
            self._tick()

    def _tick(self) -> None:
        if self._progress >= 1.0:
            self._current = self._to
            self._running = False
            self._on_change(self._current)
            return
        self._progress = min(1.0, self._progress + self._step_size)
        t = _ease_out_cubic(self._progress)
        self._current = self._from + (self._to - self._from) * t
        self._on_change(self._current)
        self._app.after(ANIM_STEP_MS, self._tick)


# ── Main App ─────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        _load_font()

        self.title("ZMP — Zapret Marketplace Patcher")
        self.geometry("1050x720")
        self.minsize(750, 520)
        self.configure(fg_color=BG)

        icon_png = Path(__file__).parent / "icon.png"
        icon_ico = Path(__file__).parent / "icon.ico"
        if icon_png.exists():
            pil_icon = Image.open(icon_png)
            self._tk_icon = ctk.CTkImage(light_image=pil_icon, dark_image=pil_icon, size=(32, 32))
            self.after(50, lambda: self.iconphoto(True, self._tk_icon._photo_image))
        elif icon_ico.exists():
            self.iconbitmap(str(icon_ico))

        self.api = MarketplaceAPI()
        self.target_dir: Path | None = None
        self.config_path: Path | None = None
        self.mods: list[dict[str, Any]] = []
        self.busy: str | None = None
        self.catalog_items: list[dict[str, Any]] = []
        self._icon_cache: dict[str, ctk.CTkImage] = {}

        self._setup_screen()
        self._check_saved_folder()

    def _f(self, size: int = FONT_SIZE, bold: bool = False) -> tuple:
        w = "bold" if bold else "normal"
        return (FONT, size, w)

    def _icon_path(self) -> str:
        p = Path(__file__).parent / "icon.png"
        if p.exists():
            return str(p)
        p = Path(__file__).parent / "icon.ico"
        return str(p) if p.exists() else ""

    # ── Welcome / Setup Screen ───────────────────────────────

    def _setup_screen(self) -> None:
        self._clear_window()

        center = ctk.CTkFrame(self, fg_color=BG)
        center.pack(expand=True, fill="both")

        card = ctk.CTkFrame(center, fg_color=SURFACE, corner_radius=16, border_width=1, border_color=DIVIDER)
        card.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.45, relheight=0.7)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(card, text="ZMP", font=self._f(28, True),
                      text_color=TEXT).grid(row=0, column=0, pady=(32, 8))
        ctk.CTkLabel(card, text="Marketplace Patcher", font=self._f(13),
                      text_color=TEXT_SEC).grid(row=1, column=0, pady=(0, 24))

        ctk.CTkFrame(card, height=1, fg_color=DIVIDER).grid(
            row=2, column=0, sticky="ew", padx=32, pady=(0, 24))

        ctk.CTkLabel(card, text="Укажите папку с zapret для начала работы",
                      font=self._f(12), text_color=TEXT_SEC
                      ).grid(row=3, column=0, pady=(0, 16))

        input_row = ctk.CTkFrame(card, fg_color="transparent")
        input_row.grid(row=4, column=0, sticky="ew", padx=32, pady=(0, 8))
        input_row.grid_columnconfigure(0, weight=1)

        self._setup_entry = ctk.CTkEntry(
            input_row, height=40, placeholder_text="C:\\zapret-discord-youtube",
            font=self._f(13), fg_color=BG_ALT, border_color=DIVIDER,
            text_color=TEXT, corner_radius=8,
        )
        self._setup_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._setup_entry.bind("<Return>", lambda e: self._setup_submit())

        ctk.CTkButton(
            input_row, text="\U0001F4C2", width=44, height=40,
            font=(FONT, 16), fg_color=BG_ALT, border_width=1,
            border_color=DIVIDER, hover_color=SURFACE_HOVER,
            corner_radius=8, command=self._setup_browse,
        ).grid(row=0, column=1)

        self._setup_error = ctk.CTkLabel(card, text="", font=self._f(11),
                                          text_color=ERROR)
        self._setup_error.grid(row=5, column=0, pady=(4, 0))

        ctk.CTkButton(
            card, text="Начать", height=42, width=200,
            font=self._f(14, True), fg_color=ACCENT, hover_color=ACCENT_HOVER,
            corner_radius=10, command=self._setup_submit,
        ).grid(row=6, column=0, pady=(20, 32))

    def _setup_browse(self) -> None:
        path = filedialog.askdirectory(title="Выберите папку zapret")
        if path:
            self._setup_entry.delete(0, "end")
            self._setup_entry.insert(0, path)

    def _setup_submit(self) -> None:
        path = self._setup_entry.get().strip()
        if not path:
            self._setup_error.configure(text="Введите путь к папке")
            return
        p = Path(path)
        if not p.is_dir():
            self._setup_error.configure(text=f"Папка не найдена: {path}")
            return
        self.target_dir = p
        self.config_path = p / "zmp.yml"
        self.mods = load_config(self.config_path)
        self._save_folder(str(p))
        self._show_main_ui()

    def _save_folder(self, path: str) -> None:
        try:
            save_file = Path.home() / ".zmp_folder"
            save_file.write_text(path, encoding="utf-8")
        except Exception:
            pass

    def _load_saved_folder(self) -> str | None:
        try:
            save_file = Path.home() / ".zmp_folder"
            if save_file.exists():
                p = save_file.read_text(encoding="utf-8").strip()
                if p and Path(p).is_dir():
                    return p
        except Exception:
            pass
        return None

    def _check_saved_folder(self) -> None:
        saved = self._load_saved_folder()
        if saved:
            self.target_dir = Path(saved)
            self.config_path = self.target_dir / "zmp.yml"
            self.mods = load_config(self.config_path)
            self._show_main_ui()

    # ── Main UI ──────────────────────────────────────────────

    def _show_main_ui(self) -> None:
        self._clear_window()
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_content()
        self.after(300, self._refresh)
        self._animate_in()

    def _animate_in(self) -> None:
        self.attributes("-alpha", 0.0)
        alpha = [0.0]

        def _step():
            alpha[0] = min(1.0, alpha[0] + 0.06)
            self.attributes("-alpha", alpha[0])
            if alpha[0] < 1.0:
                self.after(16, _step)
        _step()

    def _clear_window(self) -> None:
        for w in self.winfo_children():
            w.destroy()

    def _build_sidebar(self) -> None:
        sb = ctk.CTkFrame(self, width=250, fg_color=SURFACE, corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsw")
        sb.grid_propagate(False)

        brand = ctk.CTkFrame(sb, fg_color="transparent")
        brand.pack(fill="x", padx=20, pady=(24, 4))

        nf = ctk.CTkFrame(brand, fg_color="transparent")
        nf.pack(anchor="w")
        ctk.CTkLabel(nf, text="ZMP", font=self._f(18, True), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(nf, text="Marketplace Patcher", font=self._f(10), text_color=TEXT_SEC).pack(anchor="w")

        ctk.CTkFrame(sb, height=1, fg_color=DIVIDER).pack(fill="x", padx=16, pady=(12, 8))

        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for nav_id, icon, label in [
            ("installed", "\U0001F4E6", "Установленные"),
            ("catalog", "\U0001F50D", "Каталог"),
            ("manual", "\u2795", "По slug"),
        ]:
            btn = ctk.CTkButton(
                sb, text=f"  {icon}  {label}", anchor="w", height=38,
                font=self._f(13), fg_color="transparent", text_color=TEXT_SEC,
                hover_color=SURFACE_HOVER, corner_radius=8,
                command=lambda n=nav_id: self._set_tab(n),
            )
            btn.pack(fill="x", padx=8, pady=2)
            self.nav_buttons[nav_id] = btn

        ctk.CTkFrame(sb, height=1, fg_color=DIVIDER).pack(fill="x", padx=16, pady=(16, 0))

        ff = ctk.CTkFrame(sb, fg_color="transparent")
        ff.pack(fill="x", padx=20, pady=(14, 16), side="bottom")

        ctk.CTkLabel(ff, text="ПАПКА", font=self._f(9, True), text_color=TEXT_SEC).pack(anchor="w")
        self.folder_label = ctk.CTkLabel(
            ff, text=str(self.target_dir) if self.target_dir else "Не выбрана",
            font=self._f(11), text_color=TEXT, anchor="w", wraplength=210,
        )
        self.folder_label.pack(anchor="w", pady=(4, 0))
        ctk.CTkButton(
            ff, text="\U0001F4C2  Изменить папку", height=34, font=self._f(11),
            fg_color=BG_ALT, text_color=TEXT_SEC, border_width=1,
            border_color=DIVIDER, corner_radius=8, hover_color=SURFACE_HOVER,
            command=self._browse_folder,
        ).pack(fill="x", pady=(10, 0))

        self.current_tab = "installed"

    def _build_content(self) -> None:
        cf = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        cf.grid(row=0, column=1, sticky="nsew")
        cf.grid_columnconfigure(0, weight=1)
        cf.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(cf, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=32, pady=(28, 0))
        header.grid_columnconfigure(0, weight=1)

        self.page_title = ctk.CTkLabel(header, text="", font=self._f(22, True),
                                        text_color=TEXT, anchor="w")
        self.page_title.grid(row=0, column=0, sticky="w")
        self.page_sub = ctk.CTkLabel(header, text="", font=self._f(11),
                                      text_color=TEXT_SEC, anchor="w")
        self.page_sub.grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.search_frame = ctk.CTkFrame(header, fg_color="transparent")
        self.search_frame.grid(row=0, column=1, rowspan=2, sticky="e")
        self.search_entry = ctk.CTkEntry(
            self.search_frame, width=240, height=36, placeholder_text="Поиск модов...",
            font=self._f(13), fg_color=BG_ALT, border_color=DIVIDER,
            text_color=TEXT, corner_radius=8, placeholder_text_color=TEXT_SEC,
        )
        self.search_entry.pack(side="left", padx=(0, 8))
        self.search_entry.bind("<Return>", lambda e: self._do_search())
        ctk.CTkButton(
            self.search_frame, text="Найти", width=80, height=36,
            font=self._f(13), fg_color=ACCENT, hover_color=ACCENT_HOVER,
            corner_radius=8, command=self._do_search,
        ).pack(side="left")

        self.scroll = ctk.CTkScrollableFrame(
            cf, fg_color="transparent",
            scrollbar_button_color=DIVIDER, scrollbar_button_hover_color="#555",
        )
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=(16, 0))
        self.scroll.grid_columnconfigure(0, weight=1)

        self._set_tab("installed")

    # ── Tab switching with fade ──────────────────────────────

    def _set_tab(self, tab_id: str) -> None:
        self.current_tab = tab_id
        titles = {
            "installed": ("Установленные моды", "Управление модами"),
            "catalog": ("Каталог", "Моды из Zapret Marketplace"),
            "manual": ("Установка по slug", "Введите slug мода вручную"),
        }
        t = titles[tab_id]
        self.page_title.configure(text=t[0])
        self.page_sub.configure(text=t[1])

        for nid, btn in self.nav_buttons.items():
            if nid == tab_id:
                btn.configure(fg_color=ACCENT_DIM, text_color=ACCENT)
            else:
                btn.configure(fg_color="transparent", text_color=TEXT_SEC)

        if tab_id == "catalog":
            self.search_frame.grid()
            if not self.catalog_items:
                self.after(100, lambda: self._load_catalog(""))
        else:
            self.search_frame.grid_remove()

        self._fade_content()

    def _fade_content(self) -> None:
        self._clear()
        self.scroll.configure(fg_color="transparent")
        self.after(30, self._render_content)

    # ── Data ─────────────────────────────────────────────────

    def _refresh(self) -> None:
        if self.config_path and self.config_path.exists():
            self.mods = load_config(self.config_path)
        if self.target_dir:
            self.folder_label.configure(text=str(self.target_dir))
        self._render_content()

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(title="Выберите папку zapret")
        if not path:
            return
        p = Path(path)
        if not p.is_dir():
            return
        self.target_dir = p
        self.config_path = p / "zmp.yml"
        self.mods = load_config(self.config_path)
        self._save_folder(str(p))
        self.folder_label.configure(text=str(p))
        self._render_content()
        self._toast(f"Загружено модов: {len(self.mods)}", "ok")

    def _do_search(self) -> None:
        self._load_catalog(self.search_entry.get().strip())

    def _load_catalog(self, q: str) -> None:
        self.catalog_items = []
        self._render_content()

        def _work():
            try:
                items = self.api.list_projects(q=q or None)
                installed = {m["slug"] for m in self.mods}
                for it in items:
                    it["_installed"] = it["slug"] in installed
                self.after(0, lambda: self._set_catalog(items))
            except Exception as e:
                self.after(0, lambda: self._toast(str(e), "err"))

        threading.Thread(target=_work, daemon=True).start()

    def _set_catalog(self, items: list) -> None:
        self.catalog_items = items
        self._render_content()

    def _install_mod(self, slug: str) -> None:
        if not self.target_dir:
            self._toast("Сначала выберите папку zapret", "err")
            return
        if any(m["slug"] == slug for m in self.mods):
            self._toast(f"'{slug}' уже установлен", "err")
            return
        self.busy = slug
        self._render_content()

        def _work():
            try:
                project = self.api.get_project(slug)
                latest = project.get("latest_version") or {}
                ticket = self.api.create_ticket(slug, latest.get("id"))
                import tempfile
                zip_dest = Path(tempfile.gettempdir()) / f"zmp_{slug}.zip"
                self.api.download_zip(ticket, zip_dest)
                if not self.api.verify_zip(ticket, zip_dest):
                    zip_dest.unlink(missing_ok=True)
                    raise RuntimeError("SHA-256 проверка не пройдена")
                self.api.complete_ticket(ticket["ticket"], True, zip_dest.stat().st_size)
                entry = install_mod(zip_dest, self.target_dir, project, self.mods, self.config_path)
                self.mods = load_config(self.config_path)
                zip_dest.unlink(missing_ok=True)
                self.after(0, lambda: self._install_done(entry))
            except Exception as e:
                self.after(0, lambda: self._install_err(str(e)))

        threading.Thread(target=_work, daemon=True).start()

    def _install_done(self, entry: dict) -> None:
        self.busy = None
        self._toast(f"{entry['name']} v{entry['version']} установлен!", "ok")
        self._render_content()
        if self.current_tab == "catalog":
            self._load_catalog(self.search_entry.get().strip())

    def _install_err(self, msg: str) -> None:
        self.busy = None
        self._toast(msg, "err")
        self._render_content()

    def _remove_mod(self, slug: str) -> None:
        if not messagebox.askyesno("Удаление", f"Удалить мод {slug}?"):
            return
        self.busy = slug
        self._render_content()

        def _work():
            try:
                remove_mod(slug, self.target_dir, self.mods, self.config_path)
                self.mods = load_config(self.config_path)
                self.after(0, lambda: self._remove_done(slug))
            except Exception as e:
                self.after(0, lambda: self._install_err(str(e)))

        threading.Thread(target=_work, daemon=True).start()

    def _remove_done(self, slug: str) -> None:
        self.busy = None
        self._toast(f"'{slug}' удалён", "ok")
        self._render_content()

    # ── Icons ────────────────────────────────────────────────

    def _get_icon(self, url: str | None, size: int = 44) -> ctk.CTkImage | None:
        if not url:
            return None
        if url in self._icon_cache:
            return self._icon_cache[url]

        ph_pil = _placeholder_icon(size)
        placeholder = ctk.CTkImage(light_image=ph_pil, dark_image=ph_pil, size=(size, size))
        self._icon_cache[url] = placeholder

        def _load():
            pil = _dl_icon(url, size * 2)
            if pil:
                img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(size, size))
                self._icon_cache[url] = img
                self.after(0, self._render_content)

        threading.Thread(target=_load, daemon=True).start()
        return placeholder

    # ── Rendering ────────────────────────────────────────────

    def _clear(self) -> None:
        for w in self.scroll.winfo_children():
            w.destroy()

    def _render_content(self) -> None:
        self._clear()
        if self.current_tab == "installed":
            self._render_installed()
        elif self.current_tab == "catalog":
            self._render_catalog()
        elif self.current_tab == "manual":
            self._render_manual()

    def _empty(self, title: str, sub: str = "") -> None:
        f = ctk.CTkFrame(self.scroll, fg_color="transparent")
        f.grid(row=0, column=0, sticky="ew", padx=20, pady=80)
        ctk.CTkLabel(f, text=title, font=self._f(15), text_color=TEXT_SEC).pack()
        if sub:
            ctk.CTkLabel(f, text=sub, font=self._f(11), text_color=TEXT_SEC).pack(pady=(4, 0))

    def _render_installed(self) -> None:
        if not self.mods:
            self._empty("Модов пока нет", "Перейдите в каталог или установите по slug")
            return
        for i, m in enumerate(self.mods):
            self._card_mod(m, i)

    def _render_catalog(self) -> None:
        if not self.catalog_items:
            self._empty("Загрузка...", "Подождите...")
            return
        for i, p in enumerate(self.catalog_items):
            self._card_project(p, i)

    def _render_manual(self) -> None:
        f = ctk.CTkFrame(self.scroll, fg_color=SURFACE, corner_radius=10,
                          border_width=1, border_color=DIVIDER)
        f.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        f.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(f, text="Установка по slug", font=self._f(15, True),
                      text_color=TEXT, anchor="w").grid(
            row=0, column=0, sticky="w", padx=20, pady=(20, 2))
        ctk.CTkLabel(f, text="Введите краткое имя мода из Marketplace",
                      font=self._f(12), text_color=TEXT_SEC, anchor="w"
                      ).grid(row=1, column=0, sticky="w", padx=20)

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", padx=20, pady=(16, 20))
        row.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(
            row, placeholder_text="shizapret_mod", height=38,
            font=self._f(13), fg_color=BG_ALT, border_color=DIVIDER,
            text_color=TEXT, corner_radius=8,
        )
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        entry.bind("<Return>", lambda e: self._install_mod(entry.get().strip()))

        ctk.CTkButton(
            row, text="Установить", width=110, height=38,
            font=self._f(13), fg_color=ACCENT, hover_color=ACCENT_HOVER,
            corner_radius=8,
            command=lambda: self._install_mod(entry.get().strip()),
        ).grid(row=0, column=1)

        ctk.CTkLabel(
            f, text="Примеры:  shizapret_mod   ea_fix   fortnayt_anblok",
            font=self._f(10), text_color=TEXT_SEC, anchor="w",
        ).grid(row=3, column=0, sticky="w", padx=20, pady=(0, 20))

    # ── Cards ────────────────────────────────────────────────

    def _badge(self, parent, text: str) -> ctk.CTkLabel:
        color = SUCCESS if text == "zapret" else "#8764b8"
        return ctk.CTkLabel(
            parent, text=f" {text} ", font=(FONT, 9, "bold"),
            text_color="#fff", fg_color=color, corner_radius=4,
        )

    def _card(self, row: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self.scroll, fg_color=SURFACE, corner_radius=10,
                            border_width=1, border_color=DIVIDER)
        card.grid(row=row, column=0, sticky="ew", padx=8, pady=3)
        card.grid_columnconfigure(1, weight=1)
        return card

    def _card_icon(self, card, icon_url: str | None, row: int = 0) -> None:
        sz = 44
        icon_frame = ctk.CTkFrame(card, width=sz, height=sz, fg_color=SURFACE, corner_radius=sz // 2)
        icon_frame.grid(row=row, column=0, rowspan=2, padx=(14, 10), pady=14, sticky="ns")
        icon_frame.grid_propagate(False)

        if icon_url:
            img = self._get_icon(icon_url, sz)
            if img:
                ctk.CTkLabel(icon_frame, image=img, text="").place(
                    relx=0.5, rely=0.5, anchor="center")
                return
        ctk.CTkLabel(icon_frame, text="\U0001F4E6", font=(FONT, 18)).place(
            relx=0.5, rely=0.5, anchor="center")

    def _card_mod(self, m: dict, row: int) -> None:
        card = self._card(row)
        self._card_icon(card, None)

        tf = ctk.CTkFrame(card, fg_color="transparent")
        tf.grid(row=0, column=1, sticky="w", pady=(14, 0))
        ctk.CTkLabel(tf, text=m.get("name", m["slug"]),
                      font=self._f(13, True), text_color=TEXT).pack(side="left")
        self._badge(tf, m.get("compatibility", "zapret")).pack(side="left", padx=(8, 0))

        meta = [f"v{m.get('version', '?')}"]
        if m.get("author"):
            meta.append(m["author"])
        meta.append(m["slug"])
        ctk.CTkLabel(card, text="  \u00b7  ".join(meta),
                      font=self._f(11), text_color=TEXT_SEC, anchor="w"
                      ).grid(row=1, column=1, sticky="w", pady=(2, 14))

        busy = self.busy == m["slug"]
        ctk.CTkButton(
            card, text="Удалить", width=90, height=32,
            font=self._f(12), fg_color="transparent",
            text_color=ERROR, border_width=1, border_color="#5a2020",
            hover_color="#3a1a1a", corner_radius=8,
            state="disabled" if busy else "normal",
            command=lambda s=m["slug"]: self._remove_mod(s),
        ).grid(row=0, column=2, rowspan=2, padx=14, pady=14, sticky="e")

    def _card_project(self, p: dict, row: int) -> None:
        v = p.get("latest_version") or {}
        card = self._card(row)
        self._card_icon(card, p.get("icon_url"))

        tf = ctk.CTkFrame(card, fg_color="transparent")
        tf.grid(row=0, column=1, sticky="w", pady=(14, 0))
        ctk.CTkLabel(tf, text=p.get("title", p["slug"]),
                      font=self._f(13, True), text_color=TEXT).pack(side="left")
        self._badge(tf, p.get("compatibility", "zapret")).pack(side="left", padx=(8, 0))

        meta = [f"v{v.get('version', '?')}"]
        if v.get("file_size_label"):
            meta.append(v["file_size_label"])
        meta.append(f"{p.get('downloads_compact', '0')} загр.")
        if p.get("author"):
            meta.append(p["author"])
        ctk.CTkLabel(card, text="  \u00b7  ".join(meta),
                      font=self._f(11), text_color=TEXT_SEC, anchor="w"
                      ).grid(row=1, column=1, sticky="w", pady=(2, 4))

        if p.get("summary"):
            ctk.CTkLabel(card, text=p["summary"], font=self._f(11),
                          text_color=TEXT_SEC, anchor="w", wraplength=500,
                          justify="left"
                          ).grid(row=2, column=0, columnspan=2,
                                 sticky="w", padx=14, pady=(0, 14))

        busy = self.busy == p["slug"]
        if p.get("_installed"):
            ctk.CTkButton(
                card, text="\u2713 Установлено", width=110, height=32,
                font=self._f(12), fg_color="#1a3a1a",
                text_color=SUCCESS, border_width=1, border_color="#2a4a2a",
                corner_radius=8, state="disabled",
            ).grid(row=0, column=2, rowspan=2, padx=14, pady=14, sticky="e")
        else:
            ctk.CTkButton(
                card, text="Установить", width=110, height=32,
                font=self._f(12), fg_color=ACCENT, hover_color=ACCENT_HOVER,
                corner_radius=8, state="disabled" if busy else "normal",
                command=lambda s=p["slug"]: self._install_mod(s),
            ).grid(row=0, column=2, rowspan=2, padx=14, pady=14, sticky="e")

    # ── Toasts ───────────────────────────────────────────────

    def _toast(self, msg: str, kind: str = "info") -> None:
        colors = {"ok": SUCCESS, "err": ERROR, "info": TEXT_SEC}
        bgs = {"ok": "#1a2e2a", "err": "#2e1a1a", "info": SURFACE}
        color = colors.get(kind, TEXT_SEC)
        bg = bgs.get(kind, SURFACE)

        t = ctk.CTkToplevel(self)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        t.configure(fg_color=bg)

        w = max(260, min(420, len(msg) * 9 + 48))
        x = self.winfo_rootx() + self.winfo_width() - w - 24
        y = self.winfo_rooty() + self.winfo_height() - 52
        t.geometry(f"{w}x38+{x}+{y}")

        t.attributes("-alpha", 0.0)
        ctk.CTkLabel(t, text=f"  {msg}", font=self._f(12), text_color=color,
                      fg_color="transparent", anchor="w").pack(fill="both", expand=True)

        alpha = [0.0]

        def _fade_in():
            alpha[0] = min(1.0, alpha[0] + 0.12)
            t.attributes("-alpha", alpha[0])
            if alpha[0] < 1.0:
                t.after(16, _fade_in)
            else:
                t.after(3000, _fade_out)

        def _fade_out():
            alpha[0] -= 0.1
            if alpha[0] <= 0:
                t.destroy()
                return
            t.attributes("-alpha", alpha[0])
            t.after(16, _fade_out)

        _fade_in()
