"""Layout management: preview, save, list and delete product coordinate references.

A *layout* is one coordinate file in ``coordinates/`` plus a registry entry in
``coordinates/layouts.json`` that names the layout and lists the design /
product names it serves (several designs often share one layout; only the
probe thickness differs). Files that predate the registry keep working: they
appear as implicit layouts named by their file stem.

Nothing here changes how a layout is parsed - ``parse_reference`` is the
original code - this module only decides what gets stored where.
"""
from __future__ import annotations

import io
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .reference import (
    DEFAULT_REF_DIR,
    KIND_DIE,
    KIND_SPRING,
    REFERENCE_SUFFIXES,
    REGISTRY_FILE,
    ReferenceError,
    _reference_files,
    gang_bounds,
    implicit_product,
    layout_kind,
    parse_reference,
    read_registry,
)

WAFER_RADIUS_MM = 100.0
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,79}$")


class LayoutError(ValueError):
    """A layout cannot be saved / deleted. ``str(err)`` is the user-facing message."""


@dataclass
class LayoutSummary:
    """What the preview and the list show for one layout."""

    springs: int
    gangs: int
    springs_per_gang_min: int
    springs_per_gang_max: int
    center_x: float
    center_y: float
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    max_radius_mm: float
    kind: str = KIND_SPRING
    units: str = "mm"
    pitch_x_mm: float | None = None
    pitch_y_mm: float | None = None
    warnings: list[str] = field(default_factory=list)


def summarize_reference(ref: pd.DataFrame, center: tuple[float, float]) -> LayoutSummary:
    """Descriptive numbers for a parsed layout plus sanity warnings (never errors)."""
    per_gang = ref.groupby("Die_Num").size()
    radius = float(np.hypot(ref.x, ref.y).max())
    kind = layout_kind(ref)
    units = str(ref.attrs.get("units", "mm"))
    pitch = ref.attrs.get("pitch_mm") if kind == KIND_DIE else None
    warnings: list[str] = []
    if units == "um->mm":
        warnings.append("Coordinates were read as micrometres (values beyond 1,000) and converted to millimetres.")
    if radius > WAFER_RADIUS_MM:
        outside = int((np.hypot(ref.x, ref.y) > WAFER_RADIUS_MM).sum())
        warnings.append(f"{outside} springs fall outside the 200 mm wafer outline after centering (max radius {radius:.1f} mm). Check units (mm expected) and the coordinate origin.")
    if per_gang.min() != per_gang.max():
        warnings.append(f"Gangs do not all have the same spring count ({int(per_gang.min())} to {int(per_gang.max())}). Gang yield uses each gang's own count.")
    first_spring = ref.groupby("Die_Num").Spring_Num.min()
    if kind == KIND_SPRING and (first_spring != 1).any():
        warnings.append(f"{int((first_spring != 1).sum())} gangs do not start at Spring_Num 1.")
    if ref.Die_Num.min() != 1 or ref.Die_Num.nunique() != ref.Die_Num.max():
        warnings.append(f"Die numbers are not contiguous from 1 ({int(ref.Die_Num.min())} to {int(ref.Die_Num.max())}, {int(ref.Die_Num.nunique())} gangs).")
    return LayoutSummary(
        springs=int(len(ref)), gangs=int(ref.Die_Num.nunique()),
        springs_per_gang_min=int(per_gang.min()), springs_per_gang_max=int(per_gang.max()),
        center_x=float(center[0]), center_y=float(center[1]),
        x_min=float(ref.X.min()), x_max=float(ref.X.max()), y_min=float(ref.Y.min()), y_max=float(ref.Y.max()),
        max_radius_mm=radius, kind=kind, units=units,
        pitch_x_mm=(None if not pitch else pitch[0]), pitch_y_mm=(None if not pitch else pitch[1]),
        warnings=warnings,
    )


def _suffix_of(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in REFERENCE_SUFFIXES:
        raise LayoutError(f"{filename}: layouts must be .csv or .xlsx files.")
    return ext


def preview_layout(filename: str, payload: bytes) -> tuple[pd.DataFrame, tuple[float, float], LayoutSummary]:
    """Parse an uploaded file without storing anything. Raises ReferenceError / LayoutError."""
    ext = _suffix_of(filename)
    ref, center = parse_reference(io.BytesIO(payload), suffix=ext)
    return ref, center, summarize_reference(ref, center)


def normalize_name(name: str) -> str:
    name = (name or "").strip()
    if not NAME_PATTERN.match(name):
        raise LayoutError("Layout name must be 1-80 characters: letters, digits, spaces, '.', '_' or '-' (and start with a letter or digit).")
    return name


def normalize_products(products: list[str] | None, name: str) -> list[str]:
    seen: list[str] = []
    for raw in products or []:
        p = str(raw).strip()
        if p and p not in seen:
            if not NAME_PATTERN.match(p):
                raise LayoutError(f"Design / product name {p!r} may only contain letters, digits, spaces, '.', '_' or '-'.")
            seen.append(p)
    return seen or [name]


def _entries(ref_dir: Path) -> list[dict]:
    """Registry entries plus implicit entries for unregistered files."""
    registry = read_registry(ref_dir)
    entries = [dict(e) for e in registry["layouts"] if (ref_dir / e["file"]).is_file()]
    registered = {e["file"] for e in entries} | {e["file"] for e in registry["layouts"]}
    for p in sorted(_reference_files(ref_dir)):
        if p.name not in registered:
            entries.append({"name": p.stem, "file": p.name, "products": [implicit_product(p)], "implicit": True})
    return entries


def list_layouts(ref_dir: Path | str = DEFAULT_REF_DIR, *, with_summary: bool = True) -> list[dict]:
    """Every layout (registered and implicit), newest first, with its summary and file size."""
    ref_dir = Path(ref_dir)
    if not ref_dir.is_dir():
        return []
    out = []
    for e in _entries(ref_dir):
        path = ref_dir / e["file"]
        item = {
            "name": e["name"], "file": e["file"], "products": [str(p) for p in e.get("products") or [e["name"]]],
            "implicit": bool(e.get("implicit", False)), "saved_at": e.get("saved_at"), "source_filename": e.get("source_filename"),
            "size_bytes": path.stat().st_size, "summary": None, "error": None,
        }
        if with_summary:
            try:
                ref, center = parse_reference(path)
                item["summary"] = asdict(summarize_reference(ref, center))
            except (ReferenceError, OSError, ValueError) as exc:
                item["error"] = str(exc)
        out.append(item)
    out.sort(key=lambda i: (i["saved_at"] or ""), reverse=True)
    return out


def _write_registry(ref_dir: Path, entries: list[dict]) -> None:
    payload = {"layouts": [{k: v for k, v in e.items() if k != "implicit"} for e in entries]}
    tmp = ref_dir / f".{REGISTRY_FILE}.tmp"
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, ref_dir / REGISTRY_FILE)


def save_layout(
    ref_dir: Path | str,
    *,
    name: str,
    products: list[str] | None,
    filename: str,
    payload: bytes,
    replace: bool = False,
) -> dict:
    """Validate, store the file as ``<name>.<ext>`` and register it. Returns the list entry.

    * Parsing errors are raised as ``ReferenceError`` before anything is written.
    * An existing layout with the same name (registered or implicit) is only
      overwritten when ``replace`` is true; its old file is removed if the
      extension changes.
    * A design / product name already served by *another* layout is rejected.
    """
    ref_dir = Path(ref_dir)
    ref_dir.mkdir(parents=True, exist_ok=True)
    name = normalize_name(name)
    products = normalize_products(products, name)
    ext = _suffix_of(filename)
    ref, center = parse_reference(io.BytesIO(payload), suffix=ext)
    summary = summarize_reference(ref, center)

    entries = _entries(ref_dir)
    existing = next((e for e in entries if e["name"].lower() == name.lower()), None)
    if existing is not None and not replace:
        raise LayoutError(f"A layout named {existing['name']!r} already exists ({existing['file']}). Tick 'Replace existing layout' to overwrite it.")
    for e in entries:
        if existing is not None and e is existing:
            continue
        taken = [p for p in products if p in [str(x) for x in e.get("products") or [e["name"]]]]
        if taken:
            raise LayoutError(f"Design / product name(s) {taken} already belong to layout {e['name']!r}. Remove them there first or choose other names.")

    target = ref_dir / f"{name}{ext}"
    tmp = ref_dir / f".{name}{ext}.tmp"
    tmp.write_bytes(payload)
    os.replace(tmp, target)
    if existing is not None and existing["file"] != target.name:
        old = ref_dir / existing["file"]
        if old.is_file():
            old.unlink()

    entry = {
        "name": name, "file": target.name, "products": products,
        "source_filename": Path(filename).name, "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "springs": summary.springs, "gangs": summary.gangs, "center": [summary.center_x, summary.center_y], "kind": summary.kind,
    }
    entries = [e for e in entries if existing is None or e is not existing]
    entries.append(entry)
    _write_registry(ref_dir, entries)
    item = {**entry, "implicit": False, "size_bytes": target.stat().st_size, "summary": asdict(summary), "error": None}
    item.pop("springs", None); item.pop("gangs", None); item.pop("center", None); item.pop("kind", None)
    return item


def delete_layout(ref_dir: Path | str, name: str) -> dict:
    """Remove a layout's file and registry entry. Implicit layouts are deleted by file stem."""
    ref_dir = Path(ref_dir)
    entries = _entries(ref_dir) if ref_dir.is_dir() else []
    existing = next((e for e in entries if e["name"].lower() == name.strip().lower()), None)
    if existing is None:
        raise LayoutError(f"No layout named {name!r}.")
    path = ref_dir / existing["file"]
    if path.is_file():
        path.unlink()
    _write_registry(ref_dir, [e for e in entries if e is not existing])
    return {"name": existing["name"], "file": existing["file"], "products": [str(p) for p in existing.get("products") or [existing["name"]]]}


def reference_payload(ref: pd.DataFrame) -> dict:
    """Spring coordinates + gang bounds (+ kind / pitch) in the shape the wafer figure builder draws."""
    bounds = gang_bounds(ref)
    pitch = ref.attrs.get("pitch_mm") if layout_kind(ref) == KIND_DIE else None
    return {
        "kind": layout_kind(ref),
        "pitch": ({"x": pitch[0], "y": pitch[1]} if pitch and pitch[0] is not None and pitch[1] is not None else None),
        "die": ref.Die_Num.astype(int).tolist(),
        "spring": ref.Spring_Num.astype(int).tolist(),
        "x": [float(v) for v in ref.x.tolist()],
        "y": [float(v) for v in ref.y.tolist()],
        "gangs": [{"die": int(d), "xmin": float(b.xmin), "xmax": float(b.xmax), "ymin": float(b.ymin), "ymax": float(b.ymax)} for d, b in bounds.iterrows()],
    }
