"""Shared final-size layout, white text backgrounds, and vector export."""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt
from matplotlib.patches import Patch
from matplotlib.text import Text

BLUE = "#3775BA"
PINK = "#D0A3A3"
PINK_EDGE = "#A4676C"
GREEN = "#A8C6C2"
PURPLE = "#D7C4E2"
GRAY = "#555555"
PALE_BLUE = "#DCE9F5"
WHITE_BOX = {"facecolor": "white", "alpha": 0.85, "edgecolor": "none", "pad": 0.55}
WIDTH_MM = 139.0


def configure() -> dict:
    # Arial is the installed sans-serif option permitted by the repository style.
    font_path = font_manager.findfont("Arial", fallback_to_default=False)
    plt.rcParams.update({
        "font.family": "Arial", "font.size": 8.2, "axes.labelsize": 9,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "axes.linewidth": 0.8,
        "axes.spines.right": False, "axes.spines.top": False,
        "text.color": GRAY, "axes.labelcolor": GRAY, "xtick.color": GRAY, "ytick.color": GRAY,
        "savefig.dpi": 300, "figure.facecolor": "white", "axes.facecolor": "white",
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "hatch.linewidth": 0.45, "axes.unicode_minus": False,
    })
    warnings.filterwarnings("error", message="Glyph .* missing from font")
    return {"family": "Arial", "path": font_path}


def figure(height_mm: float):
    fig = plt.figure(figsize=(WIDTH_MM / 25.4, height_mm / 25.4), dpi=150)
    fig._height_mm = height_mm
    return fig


def axes_mm(fig, left: float, bottom: float, width: float, height: float):
    return fig.add_axes([left / WIDTH_MM, bottom / fig._height_mm,
                         width / WIDTH_MM, height / fig._height_mm])


def text_mm(fig, x: float, y: float, message: str, **kwargs):
    return fig.text(x / WIDTH_MM, y / fig._height_mm, message, bbox=WHITE_BOX.copy(),
                    color=kwargs.pop("color", GRAY), **kwargs)


def panel(fig, x: float, y: float, letter: str, title: str):
    text_mm(fig, x, y, f"({letter})", fontsize=10, fontweight="bold", va="bottom")
    text_mm(fig, x + 8, y + 0.2, title, fontsize=9, va="bottom")


def legend(fig, handles, labels, x_mm: float, y_mm: float, *, ncols=2, fontsize=8):
    obj = fig.legend(handles, labels, loc="center", bbox_to_anchor=(x_mm / WIDTH_MM, y_mm / fig._height_mm),
                     bbox_transform=fig.transFigure, ncols=ncols, fontsize=fontsize,
                     frameon=True, facecolor="white", edgecolor="none", framealpha=0.85,
                     handlelength=1.5, columnspacing=1.4, handletextpad=0.6,
                     borderpad=0.35, labelspacing=0.45)
    return obj


def comparison_legend(fig, y_mm: float, labels=("Baseline", "Modified")):
    handles = [Patch(facecolor=BLUE, edgecolor=BLUE),
               Patch(facecolor=PINK, edgecolor=PINK_EDGE, hatch="///")]
    return legend(fig, handles, labels, 86, y_mm)


def rate_bar(ax, position: float, rate: float, interval, *, role: str,
             horizontal=False, approximate=False, width=0.32):
    """Draw a rate from zero and an interval from its registered endpoints."""
    color = BLUE if role == "base" else PINK
    edge = BLUE if role == "base" else PINK_EDGE
    low, high = 100 * interval[0], 100 * interval[1]
    options = {"color": color, "edgecolor": edge, "hatch": None if role == "base" else "///",
               "linewidth": 0.6, "zorder": 3}
    line = {"color": GRAY, "linewidth": 0.9, "zorder": 4}
    dash = (0, (1.1, 0.7)) if approximate else "solid"
    if horizontal:
        ax.barh(position, 100 * rate, height=width, **options)
        ax.hlines(position, low, high, linestyle=dash, **line)
        ax.vlines([low, high], position - 0.065, position + 0.065, **line)
    else:
        ax.bar(position, 100 * rate, width=width, **options)
        ax.vlines(position, low, high, linestyle=dash, **line)
        ax.hlines([low, high], position - 0.065, position + 0.065, **line)


def white_text_boxes(fig) -> list[Text]:
    fig.canvas.draw()
    texts = [obj for obj in fig.findobj(Text) if obj.get_visible() and obj.get_text()]
    for obj in texts:
        existing = obj.get_bbox_patch()
        if existing is None:
            obj.set_bbox(WHITE_BOX.copy())
        obj.set_zorder(20)
    fig.canvas.draw()
    return texts


def inspect_layout(fig) -> dict:
    texts = white_text_boxes(fig)
    renderer = fig.canvas.get_renderer()
    canvas = fig.bbox
    outside = []
    no_white_box = []
    text_geometry = []
    polygons = []
    for obj in texts:
        patch = obj.get_bbox_patch()
        box = patch.get_window_extent(renderer)
        if box.x0 < -0.5 or box.y0 < -0.5 or box.x1 > canvas.x1 + 0.5 or box.y1 > canvas.y1 + 0.5:
            outside.append(obj.get_text())
        rgb = patch.get_facecolor()
        if tuple(round(c, 5) for c in rgb[:3]) != (1.0, 1.0, 1.0) or not 0 < rgb[3] < 1:
            no_white_box.append(obj.get_text())
        text_geometry.append({"text": obj.get_text(), "font_pt": obj.get_fontsize(),
                              "bounds_mm": [float(x) / fig.dpi * 25.4 for x in box.bounds]})
        polygons.append(patch.get_path().transformed(patch.get_transform()).vertices)
    overlaps = []
    # Project the rotated white boxes onto their own axes. Axis-aligned bounds
    # falsely report collisions between adjacent diagonal sequence labels.
    tolerance_px = 0.1 / 25.4 * fig.dpi
    for i, first in enumerate(texts):
        for j in range(i + 1, len(texts)):
            separated = False
            for angle in (first.get_rotation(), texts[j].get_rotation()):
                angle = np.deg2rad(angle)
                for direction in ((np.cos(angle), np.sin(angle)), (-np.sin(angle), np.cos(angle))):
                    a = polygons[i] @ direction
                    b = polygons[j] @ direction
                    if min(a.max(), b.max()) - max(a.min(), b.min()) <= tolerance_px:
                        separated = True
                        break
                if separated:
                    break
            if not separated:
                overlaps.append([first.get_text(), texts[j].get_text()])
    return {"width_mm": WIDTH_MM, "height_mm": fig._height_mm,
            "text_count": len(texts), "outside_canvas": outside,
            "text_without_translucent_white_box": no_white_box,
            "overlapping_text_boxes": overlaps, "text_geometry": text_geometry}


def export(fig, path: Path) -> dict:
    layout = inspect_layout(fig)
    if layout["outside_canvas"] or layout["text_without_translucent_white_box"] or layout["overlapping_text_boxes"]:
        raise ValueError(f"Figure layout check failed: {path.name}: "
                         f"outside={layout['outside_canvas']}; overlaps={layout['overlapping_text_boxes']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    for extension in ("pdf", "png", "svg"):
        metadata = {"Title": path.name} if extension == "pdf" else None
        # Preserve the exact page size. Tight cropping would change print scale.
        fig.savefig(path.with_suffix(f".{extension}"), dpi=300, facecolor="white", metadata=metadata)
    return layout
