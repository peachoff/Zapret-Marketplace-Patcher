"""ZMP — Flask server and web UI."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, List, Optional

from flask import Flask, jsonify, request

from .api_client import MarketplaceAPI
from .installer import install_mod, remove_mod, load_config


def create_app() -> Flask:
    flask_app = Flask(__name__)
    api = MarketplaceAPI()

    state: dict[str, Any] = {
        "target_dir": None,
        "config_path": None,
        "mods": [],
    }

    def _ensure_folder() -> Optional[str]:
        if state["target_dir"] and state["target_dir"].is_dir():
            return None
        return "Папка zapret не выбрана"

    @flask_app.route("/favicon.ico")
    def favicon():
        icon_path = Path(__file__).parent / "icon.ico"
        if icon_path.exists():
            from flask import send_file
            return send_file(icon_path, mimetype="image/x-icon")
        return "", 204

    @flask_app.route("/")
    def index():
        return HTML

    @flask_app.route("/api/status")
    def api_status():
        td = state["target_dir"]
        return jsonify({
            "folder": str(td) if td else None,
            "mods": state["mods"],
        })

    @flask_app.route("/api/set_folder", methods=["POST"])
    def api_set_folder():
        path = request.json.get("path", "")
        p = Path(path)
        if not p.is_dir():
            return jsonify({"error": f"Папка не найдена: {path}"}), 400
        state["target_dir"] = p
        state["config_path"] = p / "zmp.yml"
        state["mods"] = load_config(state["config_path"])
        return jsonify({"ok": True, "path": str(p), "count": len(state["mods"])})

    @flask_app.route("/api/catalog")
    def api_catalog():
        q = request.args.get("q")
        try:
            projects = api.list_projects(q=q)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        installed_slugs = {m["slug"] for m in state["mods"]}
        for p in projects:
            p["_installed"] = p["slug"] in installed_slugs
        return jsonify(projects)

    @flask_app.route("/api/project/<slug>")
    def api_project(slug):
        try:
            return jsonify(api.get_project(slug))
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/api/install", methods=["POST"])
    def api_install():
        slug = request.json.get("slug", "").strip()
        if not slug:
            return jsonify({"error": "Slug не указан"}), 400
        err = _ensure_folder()
        if err:
            return jsonify({"error": err}), 400
        if any(m["slug"] == slug for m in state["mods"]):
            return jsonify({"error": f"'{slug}' уже установлен"}), 400

        try:
            project = api.get_project(slug)
            latest = project.get("latest_version") or {}
            ticket = api.create_ticket(slug, latest.get("id"))
            zip_dest = Path(tempfile.gettempdir()) / f"zmp_{slug}.zip"
            api.download_zip(ticket, zip_dest)
            if not api.verify_zip(ticket, zip_dest):
                zip_dest.unlink(missing_ok=True)
                return jsonify({"error": "SHA-256 проверка не пройдена"}), 500
            api.complete_ticket(ticket["ticket"], True, zip_dest.stat().st_size)
            entry = install_mod(zip_dest, state["target_dir"], project, state["mods"], state["config_path"])
            state["mods"] = load_config(state["config_path"])
            zip_dest.unlink(missing_ok=True)
            return jsonify({"ok": True, "name": entry["name"], "version": entry["version"]})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @flask_app.route("/api/browse_folder")
    def api_browse_folder():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Выберите папку zapret")
        root.destroy()
        if not path:
            return jsonify({"cancelled": True})
        return jsonify({"path": path})

    @flask_app.route("/api/remove", methods=["POST"])
    def api_remove():
        slug = request.json.get("slug", "").strip()
        if not slug:
            return jsonify({"error": "Slug не указан"}), 400
        err = _ensure_folder()
        if err:
            return jsonify({"error": err}), 400
        ok = remove_mod(slug, state["target_dir"], state["mods"], state["config_path"])
        if ok:
            state["mods"] = load_config(state["config_path"])
            return jsonify({"ok": True})
        return jsonify({"error": "Мод не найден"}), 404

    return flask_app


HTML = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ZMP</title>
<link rel="icon" href="/favicon.ico" type="image/x-icon">
<style>
@font-face{font-family:'Segoe UI Variable';src:local('Segoe UI Variable Display'),local('Segoe UI Variable'),local('Segoe UI'),local('system-ui');font-weight:100 900}
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --mica:#202020;--surface:#2c2c2c;--surface-hover:#353535;--surface-active:#404040;
  --layer:#1c1c1c;--layer-alt:#242424;--divider:rgba(255,255,255,0.06);
  --text:#ffffff;--text-sec:#9e9e9e;--text-disabled:rgba(255,255,255,0.36);
  --accent:#0078d4;--accent-hover:#1a86d9;--accent-pressed:#005a9e;--accent-bg:rgba(0,120,212,0.08);
  --success:#0f7b0f;--success-bg:rgba(15,123,15,0.08);--error:#c42b1c;--error-bg:rgba(196,43,28,0.08);
  --card-bg:#2c2c2c;--card-border:rgba(255,255,255,0.04);
  --radius:8px;--radius-sm:4px;--radius-lg:12px;
  --shadow:0 2px 4px rgba(0,0,0,0.14),0 0 2px rgba(0,0,0,0.12);
  --shadow-lg:0 8px 16px rgba(0,0,0,0.26),0 0 2px rgba(0,0,0,0.12);
  --font:'Segoe UI Variable','Segoe UI',system-ui,-apple-system,sans-serif;
}
html,body,#app{height:100%;overflow:hidden}
body{background:var(--mica);color:var(--text);font-family:var(--font);font-size:14px;-webkit-font-smoothing:antialiased}
::-webkit-scrollbar{width:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.08);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,0.14)}

.app{display:grid;grid-template-columns:280px 1fr;height:100vh}

.nav-view{background:var(--layer);border-right:1px solid var(--divider);display:flex;flex-direction:column;overflow:hidden}
.nav-header{padding:20px 16px 12px}
.nav-brand{display:flex;align-items:center;gap:12px;margin-bottom:16px}
.nav-brand img{width:28px;height:28px;border-radius:var(--radius-sm)}
.nav-brand-text{display:flex;flex-direction:column}
.nav-brand-name{font-size:14px;font-weight:600;letter-spacing:0.2px}
.nav-brand-sub{font-size:11px;color:var(--text-sec)}

.search-box{position:relative;margin:0 12px 8px}
.search-box input{width:100%;background:var(--surface);border:1px solid var(--divider);border-radius:var(--radius);padding:8px 12px 8px 36px;color:var(--text);font-size:13px;font-family:var(--font);outline:none;transition:border-color 0.15s}
.search-box input:focus{border-color:var(--accent)}
.search-box input::placeholder{color:var(--text-sec)}
.search-box svg{position:absolute;left:10px;top:50%;transform:translateY(-50%);width:16px;height:16px;color:var(--text-sec)}

.nav-items{flex:1;padding:4px 4px;overflow-y:auto}
.nav-item{display:flex;align-items:center;gap:12px;padding:9px 12px;border-radius:var(--radius);color:var(--text-sec);cursor:pointer;font-size:13px;font-weight:400;transition:all 0.12s;user-select:none;margin-bottom:1px}
.nav-item:hover{background:var(--surface-hover);color:var(--text)}
.nav-item.active{background:var(--accent-bg);color:var(--accent);font-weight:500}
.nav-item svg{width:16px;height:16px;flex-shrink:0;stroke-width:1.5}

.nav-footer{padding:12px;border-top:1px solid var(--divider)}
.nav-footer-label{font-size:10px;color:var(--text-sec);text-transform:uppercase;letter-spacing:0.6px;font-weight:600;margin-bottom:6px;padding:0 4px}
.nav-footer-path{font-size:12px;color:var(--text);line-height:1.3;word-break:break-all;min-height:16px;max-height:36px;overflow:hidden;padding:0 4px}
.nav-footer-btn{width:100%;margin-top:8px;padding:7px 12px;border:1px solid var(--divider);border-radius:var(--radius);background:transparent;color:var(--text-sec);font-size:12px;font-family:var(--font);cursor:pointer;transition:all 0.12s;text-align:center}
.nav-footer-btn:hover{background:var(--surface-hover);color:var(--text);border-color:rgba(255,255,255,0.1)}

.page{display:flex;flex-direction:column;overflow:hidden;background:var(--mica)}
.page-header{padding:24px 32px 16px;flex-shrink:0}
.page-header h1{font-size:22px;font-weight:600;letter-spacing:-0.2px;margin-bottom:2px}
.page-header p{font-size:12px;color:var(--text-sec)}
.page-body{flex:1;overflow-y:auto;padding:0 32px 32px}

.empty{text-align:center;padding:64px 20px;color:var(--text-sec)}
.empty svg{width:48px;height:48px;margin-bottom:16px;opacity:0.3;stroke:var(--text-sec)}
.empty p{font-size:14px;line-height:1.6}
.empty .sub{font-size:12px;margin-top:4px}

.card{background:var(--card-bg);border:1px solid var(--card-border);border-radius:var(--radius);padding:14px 16px;margin-bottom:6px;display:flex;gap:14px;transition:background 0.12s}
.card:hover{background:var(--surface-hover)}
.card-img{width:48px;height:48px;border-radius:var(--radius-sm);background:var(--layer);flex-shrink:0;overflow:hidden;display:flex;align-items:center;justify-content:center;font-size:20px}
.card-img img{width:100%;height:100%;object-fit:cover}
.card-body{flex:1;min-width:0}
.card-title{font-size:14px;font-weight:600;margin-bottom:2px;display:flex;align-items:center;gap:8px}
.card-title .badge{font-size:10px;font-weight:600;padding:1px 6px;border-radius:var(--radius-sm);color:#fff;letter-spacing:0.3px}
.badge.zapret{background:#0f7b0f}
.badge.zapret2{background:#8764b8}
.card-meta{font-size:11px;color:var(--text-sec);display:flex;gap:10px;flex-wrap:wrap}
.card-desc{font-size:12px;color:var(--text-sec);line-height:1.4;margin-top:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card-actions{display:flex;align-items:center;flex-shrink:0}

.btn{padding:6px 16px;border-radius:var(--radius);border:none;font-size:12px;font-weight:500;font-family:var(--font);cursor:pointer;transition:all 0.12s;white-space:nowrap}
.btn:active{transform:scale(0.97)}
.btn:disabled{opacity:0.4;cursor:not-allowed;pointer-events:none}
.btn-accent{background:var(--accent);color:#fff}
.btn-accent:hover{background:var(--accent-hover)}
.btn-accent:active{background:var(--accent-pressed)}
.btn-subtle{background:transparent;color:var(--text-sec);border:1px solid var(--divider)}
.btn-subtle:hover{background:var(--surface-hover);color:var(--text)}
.btn-danger{background:transparent;color:var(--error);border:1px solid rgba(196,43,28,0.3)}
.btn-danger:hover{background:var(--error-bg);border-color:var(--error)}
.btn-success{background:var(--success-bg);color:#6ccb5f;border:1px solid rgba(15,123,15,0.2);cursor:default}

.input-group{display:flex;gap:8px;max-width:400px;margin:16px auto 0}
.input-group input{flex:1;background:var(--surface);border:1px solid var(--divider);border-radius:var(--radius);padding:8px 14px;color:var(--text);font-size:13px;font-family:var(--font);outline:none;transition:border-color 0.15s}
.input-group input:focus{border-color:var(--accent)}
.hint{max-width:400px;margin:12px auto 0;font-size:12px;color:var(--text-sec);line-height:1.6;text-align:center}
.hint code{color:var(--accent);background:var(--accent-bg);padding:1px 6px;border-radius:var(--radius-sm);font-size:11px}

.toast-wrap{position:fixed;bottom:16px;right:16px;z-index:9999;display:flex;flex-direction:column;gap:6px}
.toast{padding:10px 16px;border-radius:var(--radius);font-size:13px;font-weight:400;font-family:var(--font);animation:flyIn 0.25s ease;max-width:380px;pointer-events:none;box-shadow:var(--shadow)}
.toast-ok{background:#1a3a1a;border:1px solid rgba(15,123,15,0.3);color:#6ccb5f}
.toast-err{background:#3a1a1a;border:1px solid rgba(196,43,28,0.3);color:#ff6b6b}
.toast-info{background:var(--surface);border:1px solid var(--divider);color:var(--text)}
@keyframes flyIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}

.spinner{display:inline-block;width:14px;height:14px;border:2px solid var(--divider);border-top-color:var(--accent);border-radius:50%;animation:spin 0.6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<div id="app"></div>
<script>
"use strict";

const $ = s => document.querySelector(s);
function h(tag, attrs) {
  const el = document.createElement(tag);
  if (attrs) Object.entries(attrs).forEach(([k, v]) => {
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (v != null) el.setAttribute(k, v);
  });
  for (let i = 2; i < arguments.length; i++) {
    const c = arguments[i];
    if (c == null || c === false) continue;
    if (Array.isArray(c)) c.forEach(n => { if (n) el.appendChild(n); });
    else el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(c) : c);
  }
  return el;
}

const ICO = {
  downloads: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M6 20h12M12 4v12m0 0l-4-4m4 4l4-4"/></svg>`,
  catalog: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>`,
  plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M12 5v14m-7-7h14"/></svg>`,
  empty: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/></svg>`,
  search: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.35-4.35"/></svg>`,
};

let S = {
  tab: "installed",
  folder: null,
  mods: [],
  toasts: [],
  busy: null,
  items: [],
  loading: false,
  q: "",
  sq: "",
};

async function api(path, opts) {
  const r = await fetch(path, opts);
  const d = await r.json();
  if (d.error) throw new Error(d.error);
  return d;
}

function toast(msg, type) {
  type = type || "info";
  const id = Date.now();
  S.toasts.push({id, msg, type});
  renderToasts();
  setTimeout(() => { S.toasts = S.toasts.filter(t => t.id !== id); renderToasts(); }, 4000);
}

async function refresh() {
  try {
    const d = await api("/api/status");
    S.folder = d.folder;
    S.mods = d.mods;
    render();
  } catch(e) {}
}

async function loadCatalog(q) {
  S.loading = true;
  render();
  try {
    S.items = await api("/api/catalog" + (q ? "?q=" + encodeURIComponent(q) : ""));
  } catch(e) { toast(e.message, "err"); }
  S.loading = false;
  render();
}

async function browseFolder() {
  try {
    const d = await api("/api/browse_folder");
    if (d.cancelled) return;
    const r = await api("/api/set_folder", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({path: d.path}),
    });
    S.folder = r.path;
    refresh();
    toast("Загружено модов: " + r.count, "ok");
  } catch(e) { toast(e.message, "err"); }
}

async function installMod(slug) {
  if (!S.folder) { toast("Сначала выберите папку zapret", "err"); return; }
  S.busy = slug;
  render();
  try {
    const d = await api("/api/install", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({slug}),
    });
    toast(d.name + " v" + d.version + " установлен!", "ok");
    refresh();
    loadCatalog(S.sq);
  } catch(e) { toast(e.message, "err"); }
  S.busy = null;
  render();
}

async function removeMod(slug) {
  if (!confirm("Удалить мод " + slug + "?")) return;
  S.busy = slug;
  render();
  try {
    await api("/api/remove", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({slug}),
    });
    toast("'" + slug + "' удалён", "ok");
    refresh();
  } catch(e) { toast(e.message, "err"); }
  S.busy = null;
  render();
}

function setTab(id) {
  S.tab = id;
  if (id === "catalog") { S.sq = S.q; loadCatalog(S.sq); }
  render();
}

function render() {
  const root = $("#app");
  root.innerHTML = "";

  const app = h("div", {class: "app"});

  // === NAV VIEW ===
  const nav = h("div", {class: "nav-view"});

  // Brand
  nav.appendChild(h("div", {class: "nav-header"},
    h("div", {class: "nav-brand"},
      h("img", {src: "/favicon.ico"}),
      h("div", {class: "nav-brand-text"},
        h("div", {class: "nav-brand-name"}, "ZMP"),
        h("div", {class: "nav-brand-sub"}, "Marketplace Patcher")
      )
    )
  ));

  // Search (always visible for catalog quick-search)
  const searchBox = h("div", {class: "search-box"});
  searchBox.innerHTML = ICO.search;
  const searchInput = h("input", {placeholder: "Поиск в каталоге\u2026"});
  searchInput.value = S.q;
  searchInput.addEventListener("input", e => { S.q = e.target.value; });
  searchInput.addEventListener("keydown", e => { if (e.key === "Enter") { S.sq = S.q; loadCatalog(S.sq); }});
  searchBox.appendChild(searchInput);
  nav.appendChild(searchBox);

  // Nav items
  const items = h("div", {class: "nav-items"});
  [["installed", ICO.downloads, "Установленные"], ["catalog", ICO.catalog, "Каталог"], ["manual", ICO.plus, "По slug"]].forEach(([id, icon, label]) => {
    const active = S.tab === id;
    const item = h("div", {
      class: "nav-item" + (active ? " active" : ""),
      onClick: () => setTab(id),
    });
    item.innerHTML = icon;
    item.appendChild(document.createTextNode(" " + label));
    items.appendChild(item);
  });
  nav.appendChild(items);

  // Folder footer
  const footer = h("div", {class: "nav-footer"});
  footer.appendChild(h("div", {class: "nav-footer-label"}, "Папка zapret"));
  footer.appendChild(h("div", {class: "nav-footer-path", id: "fp"}, S.folder || "Не выбрана"));
  const fbtn = h("button", {class: "nav-footer-btn", onClick: browseFolder}, "Выбрать папку");
  footer.appendChild(fbtn);
  nav.appendChild(footer);
  app.appendChild(nav);

  // === PAGE ===
  const page = h("div", {class: "page"});

  // Header
  const titles = {installed: ["Установленные моды", "Управление установленными модами"], catalog: ["Каталог", "Моды из Zapret Marketplace"], manual: ["Установка по slug", "Введите slug мода вручную"]};
  const [title, sub] = titles[S.tab];
  page.appendChild(h("div", {class: "page-header"}, h("h1", null, title), h("p", null, sub)));

  // Body
  const body = h("div", {class: "page-body"});

  if (S.tab === "installed") {
    if (!S.mods.length) {
      body.appendChild(h("div", {class: "empty"},
        h("div", {html: ICO.empty}),
        h("p", null, "Модов пока нет"),
        h("p", {class: "sub"}, "Перейдите в каталог или установите по slug")
      ));
    } else {
      S.mods.forEach(m => {
        const busy = S.busy === m.slug;
        const card = h("div", {class: "card"});
        card.appendChild(h("div", {class: "card-img"}, "\uD83D\uDCE6"));
        const body2 = h("div", {class: "card-body"},
          h("div", {class: "card-title"},
            m.name || m.slug,
            h("span", {class: "badge " + (m.compatibility || "zapret")}, m.compatibility || "?")
          ),
          h("div", {class: "card-meta"},
            h("span", null, "v" + m.version),
            m.author ? h("span", null, m.author) : null,
            h("span", null, m.slug)
          )
        );
        if (m.description) body2.appendChild(h("div", {class: "card-desc"}, m.description));
        card.appendChild(body2);
        card.appendChild(h("div", {class: "card-actions"},
          h("button", {class: "btn btn-danger", onClick: () => removeMod(m.slug), disabled: busy || null},
            busy ? h("span", {class: "spinner"}) : "Удалить"
          )
        ));
        body.appendChild(card);
      });
    }
  }

  else if (S.tab === "catalog") {
    if (S.loading) {
      body.appendChild(h("div", {class: "empty"},
        h("span", {class: "spinner", style: {width: "28px", height: "28px", borderWidth: "3px"}}),
        h("p", {style: {marginTop: "12px"}}, "Загрузка\u2026")
      ));
    } else if (!S.items.length) {
      body.appendChild(h("div", {class: "empty"},
        h("div", {html: ICO.empty}),
        h("p", null, "Ничего не найдено")
      ));
    } else {
      S.items.forEach(p => {
        const v = p.latest_version || {};
        const busy = S.busy === p.slug;
        const card = h("div", {class: "card"});
        if (p.icon_url) {
          const img = h("img", {src: p.icon_url, alt: "", style: {width: "100%", height: "100%", objectFit: "cover"}, onError: function() { this.parentNode.textContent = "\uD83D\uDCE6"; }});
          card.appendChild(h("div", {class: "card-img"}, img));
        } else {
          card.appendChild(h("div", {class: "card-img"}, "\uD83D\uDCE6"));
        }
        const body2 = h("div", {class: "card-body"},
          h("div", {class: "card-title"},
            p.title,
            h("span", {class: "badge " + (p.compatibility || "zapret")}, p.compatibility || "?")
          ),
          h("div", {class: "card-meta"},
            h("span", null, "v" + (v.version || "?")),
            v.file_size_label ? h("span", null, v.file_size_label) : null,
            h("span", null, (p.downloads_compact || "0") + " загр."),
            h("span", null, p.author)
          )
        );
        if (p.summary) body2.appendChild(h("div", {class: "card-desc"}, p.summary));
        card.appendChild(body2);
        if (p._installed) {
          card.appendChild(h("div", {class: "card-actions"}, h("button", {class: "btn btn-success"}, "Установлено")));
        } else {
          card.appendChild(h("div", {class: "card-actions"},
            h("button", {class: "btn btn-accent", onClick: () => installMod(p.slug), disabled: busy || null},
              busy ? h("span", {class: "spinner"}) : "Установить"
            )
          ));
        }
        body.appendChild(card);
      });
    }
  }

  else if (S.tab === "manual") {
    const input = h("input", {placeholder: "shizapret_mod"});
    const btn = h("button", {class: "btn btn-accent"}, "Установить");
    input.addEventListener("keydown", e => { if (e.key === "Enter" && input.value.trim()) installMod(input.value.trim()); });
    btn.addEventListener("click", () => { if (input.value.trim()) installMod(input.value.trim()); });
    body.appendChild(h("div", {class: "input-group"}, input, btn));
    body.appendChild(h("div", {class: "hint"},
      "Примеры: ", h("code", null, "shizapret_mod"), " ",
      h("code", null, "ea_fix"), " ",
      h("code", null, "fortnayt_anblok")
    ));
  }

  page.appendChild(body);
  app.appendChild(page);
  root.appendChild(app);

  // Toasts
  const tw = h("div", {class: "toast-wrap"});
  S.toasts.forEach(t => tw.appendChild(h("div", {class: "toast toast-" + t.type}, t.msg)));
  root.appendChild(tw);
}

refresh();
loadCatalog("");
</script>
</body>
</html>"""
