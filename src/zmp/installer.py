"""ZMP — Mod installation and removal logic."""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

BLOCKED_EXT = {".exe", ".dll", ".msi", ".cmd", ".com", ".scr", ".vbs", ".js"}


def _merge_list_file(target: Path, source: Path) -> int:
    existing: set[str] = set()
    if target.exists():
        existing = {l.rstrip("\r\n") for l in target.read_text(encoding="utf-8", errors="ignore").splitlines()}
    new_lines: list[str] = []
    for line in source.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.rstrip("\r\n")
        if s and s not in existing:
            new_lines.append(s)
            existing.add(s)
    if new_lines:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "a", encoding="utf-8") as f:
            for l in new_lines:
                f.write(l + "\n")
    return len(new_lines)


def _unmerge_list_file(target: Path, lines_to_remove: set[str]) -> None:
    if not target.exists():
        return
    current = target.read_text(encoding="utf-8", errors="ignore").splitlines()
    kept = [l for l in current if l.rstrip("\r\n") not in lines_to_remove]
    target.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def install_mod(
    zip_path: Path,
    target_dir: Path,
    project: Dict[str, Any],
    mods: List[Dict[str, Any]],
    config_path: Path,
) -> Dict[str, Any]:
    slug = project["slug"]
    title = project.get("title", slug)
    author = project.get("author", "")
    desc = project.get("summary", "")
    latest = project.get("latest_version") or {}
    version = latest.get("version", "0.0.0")
    compat = project.get("compatibility", "zapret")
    mod_dir = target_dir / "mods" / slug

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp_path)

        all_files = [f for f in tmp_path.rglob("*") if f.is_file()]
        if not all_files:
            raise RuntimeError("ZIP-архив пуст")

        blocked = [f.name for f in all_files if f.suffix.lower() in BLOCKED_EXT]
        if blocked:
            raise RuntimeError(f"Заблокированные файлы: {', '.join(blocked)}")

        if mod_dir.exists():
            shutil.rmtree(mod_dir)
        mod_dir.mkdir(parents=True, exist_ok=True)

        copied_bats: list[str] = []
        merged_lists: Dict[str, List[str]] = {}

        for f in all_files:
            rel = f.relative_to(tmp_path)
            suffix = rel.suffix.lower()
            if suffix == ".bat":
                shutil.copy2(f, target_dir / rel.name)
                copied_bats.append(rel.name)
            elif suffix == ".txt":
                dest = target_dir / rel
                count = _merge_list_file(dest, f)
                if count > 0:
                    merged_lists[str(rel)] = [
                        l.rstrip("\r\n")
                        for l in f.read_text(encoding="utf-8", errors="ignore").splitlines()
                        if l.strip()
                    ]
            else:
                dest = mod_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)

        (mod_dir / "zmp-meta.json").write_text(json.dumps({
            "slug": slug, "name": title, "version": version,
            "bat_files": copied_bats, "merged_lists": merged_lists,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    entry = {
        "slug": slug, "name": title, "version": version,
        "compatibility": compat, "author": author, "description": desc,
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    mods = [m for m in mods if m["slug"] != slug]
    mods.append(entry)
    _save_config(config_path, mods)
    return entry


def remove_mod(
    slug: str, target_dir: Path, mods: List[Dict[str, Any]], config_path: Path,
) -> bool:
    mod = next((m for m in mods if m["slug"] == slug), None)
    if mod is None:
        return False

    meta_path = target_dir / "mods" / slug / "zmp-meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            for bat in meta.get("bat_files", []):
                bf = target_dir / bat
                if bf.exists():
                    bf.unlink()
            for list_rel, lines in meta.get("merged_lists", {}).items():
                _unmerge_list_file(target_dir / list_rel, set(lines))
        except Exception:
            pass

    mod_dir = target_dir / "mods" / slug
    if mod_dir.exists():
        shutil.rmtree(mod_dir, ignore_errors=True)

    mods = [m for m in mods if m["slug"] != slug]
    _save_config(config_path, mods)
    return True


def load_config(config_path: Path) -> List[Dict[str, Any]]:
    if not config_path.exists():
        return []
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("mods", [])


def _save_config(config_path: Path, mods: List[Dict[str, Any]]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump({"mods": mods}, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
