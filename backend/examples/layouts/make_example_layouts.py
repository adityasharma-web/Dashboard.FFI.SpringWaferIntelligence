"""Generate SYNTHETIC example layout files for demonstrating the Layouts page.

These are made-up designs, not customer data. They use the same schema as a
real coordinate reference (``Die_Num (gang_number), Spring_Num (spring_number),
feature, X, Y``; mm) so they can be uploaded on the Layouts page as-is.

    EXAMPLE-LAYOUT-A.csv       valid: 128 gangs x 160 springs (20,480) in a staggered circular grid
    EXAMPLE-LAYOUT-B.csv       valid: 56 gangs x 96 springs (5,376), a smaller 4-column design
    EXAMPLE-LAYOUT-INVALID.csv rejected: duplicate spring key (shows the validation path)

Run from this folder: ``python make_example_layouts.py``
"""
from __future__ import annotations

import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent
WAFER_RADIUS = 100.0


def build(
    *,
    columns: int,
    rows: int,
    column_pitch: float,
    row_pitch: float,
    gang_pitch_x: float,
    gang_pitch_y: float,
    keep_radius: float,
    origin: tuple[float, float],
) -> list[tuple[int, int, str, float, float]]:
    """Gangs on a rectangular grid, kept when the whole gang fits inside ``keep_radius``.

    Springs inside a gang are numbered column-major (down each column, then the
    next column), like the bundled reference. Source coordinates are offset by
    ``origin`` so the inferred-center caveat shows something non-zero.
    """
    gang_w = (columns - 1) * column_pitch
    gang_h = (rows - 1) * row_pitch
    out: list[tuple[int, int, str, float, float]] = []
    die = 0
    ny = int(keep_radius * 2 // gang_pitch_y) + 2
    nx = int(keep_radius * 2 // gang_pitch_x) + 2
    for iy in range(ny):
        cy = keep_radius - gang_h / 2 - iy * gang_pitch_y
        for ix in range(nx):
            cx = -keep_radius + gang_w / 2 + ix * gang_pitch_x + (gang_pitch_x / 2 if iy % 2 else 0)
            corners = [(cx - gang_w / 2 - 2, cy - gang_h / 2), (cx + gang_w / 2 + 2, cy - gang_h / 2), (cx - gang_w / 2 - 2, cy + gang_h / 2), (cx + gang_w / 2 + 2, cy + gang_h / 2)]
            if any((x * x + y * y) ** 0.5 > keep_radius for x, y in corners):
                continue
            die += 1
            spring = 0
            for c in range(columns):
                for r in range(rows):
                    spring += 1
                    x = cx - gang_w / 2 + c * column_pitch + origin[0]
                    y = cy + gang_h / 2 - r * row_pitch + origin[1]
                    out.append((die, spring, "A", round(x, 3), round(y, 3)))
    return out


def write(name: str, rows: list[tuple[int, int, str, float, float]]) -> None:
    path = HERE / name
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Die_Num (gang_number)", "Spring_Num (spring_number)", "feature", "X", "Y"])
        w.writerows(rows)
    gangs = len({r[0] for r in rows})
    print(f"{name}: {len(rows)} springs, {gangs} gangs")


def main() -> None:
    a = build(columns=5, rows=32, column_pitch=4.6, row_pitch=0.18, gang_pitch_x=22.0, gang_pitch_y=8.0, keep_radius=94.0, origin=(120.0, 85.0))
    write("EXAMPLE-LAYOUT-A.csv", a)
    b = build(columns=4, rows=24, column_pitch=4.8, row_pitch=0.2, gang_pitch_x=26.0, gang_pitch_y=11.0, keep_radius=80.0, origin=(0.0, 0.0))
    write("EXAMPLE-LAYOUT-B.csv", b)
    bad = list(b[:400])
    bad.append(bad[10])  # duplicate (die, spring) key -> rejected by the preview
    write("EXAMPLE-LAYOUT-INVALID.csv", bad)


if __name__ == "__main__":
    main()
