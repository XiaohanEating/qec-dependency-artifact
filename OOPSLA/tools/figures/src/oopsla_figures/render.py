"""Four figures at the acmsmall single-column print width."""

from __future__ import annotations

import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

from .style import (
    BLUE, GRAY, GREEN, PALE_BLUE, PINK, PINK_EDGE, PURPLE, WHITE_BOX,
    axes_mm, comparison_legend, figure, rate_bar, legend, panel, text_mm,
)

DIMENSION_LABELS = ["Code", "Extraction", "Architecture", "Noise", "Decoder"]
STRATEGY_LABELS = ["Configuration differences", "Experiment log", "Visible dependencies",
                   "Complete dependencies", "Checker", "Full rerun"]


def figure2(data: dict):
    fig = figure(86)
    columns = ["Code\nmatrices", "Layout", "Noise\nobject", "Stim\ncircuit", "Detector\nerror model",
               "Logical\nobservables", "Decoder\npredictions"]
    titles = ["Node impact from source-derived dependencies",
              "Coordinate impact from source-derived dependencies",
              "Node impact from conservative dependencies"]
    left = 29
    column_widths = np.array([14, 10, 13, 13, 18, 19, 19], dtype=float)
    edges = np.concatenate(([0], np.cumsum(column_widths)))
    centers = (edges[:-1] + edges[1:]) / 2
    width = edges[-1]
    for i, title in enumerate(titles):
        bottom = 55.5 - 22.5 * i
        ax = axes_mm(fig, left, bottom, width, 16.5)
        panel(fig, 4, bottom + 17.3, "abc"[i], title)
        ax.set_xlim(0, width)
        ax.set_ylim(4.5, -0.5)
        ax.set_xticks([])
        ax.set_yticks(range(5), DIMENSION_LABELS)
        ax.tick_params(axis="y", length=0, pad=4)
        for spine in ax.spines.values():
            spine.set_visible(False)
        for row_index, row in enumerate(data["figure2"][i]["rows"]):
            for col_index, cell in enumerate(row["cells"]):
                missed = cell["changed"] and not cell["predicted"]
                center = centers[col_index]
                ax.add_patch(Rectangle((edges[col_index], row_index - 0.5), column_widths[col_index], 1,
                                       facecolor=PALE_BLUE if cell["predicted"] else "#FAFAFA",
                                       edgecolor=PINK_EDGE if missed else "#CCD2D8",
                                       linewidth=1.4 if missed else 0.45, zorder=1))
                ax.add_patch(Rectangle((center - 1.5, row_index - 0.25), 3, 0.5,
                                       facecolor="white", edgecolor="none", alpha=0.85, zorder=2))
                ax.plot(center, row_index, marker="o" if cell["changed"] else "s", markersize=3.3,
                        color=GRAY, markerfacecolor=GRAY if cell["changed"] else "white",
                        markeredgewidth=0.8, linestyle="none", zorder=3)
        ax.get_yticklabels()[3].set_color(BLUE)
    for i, name in enumerate(columns):
        text_mm(fig, left + centers[i], 80.9, name, fontsize=8, ha="center", va="center")
    handles = [Line2D([], [], marker="o", color=GRAY, linestyle="none", markersize=3.8),
               Line2D([], [], marker="s", color=GRAY, markerfacecolor="white", linestyle="none", markersize=3.8),
               Patch(facecolor=PALE_BLUE, edgecolor="#CCD2D8"),
               Patch(facecolor="white", edgecolor=PINK_EDGE, linewidth=1.4)]
    legend(fig, handles, ["Measured change", "Measured equality", "Predicted impact", "Missed change"],
           77, 4.8, ncols=2, fontsize=8)
    return fig


def figure3(data: dict):
    fig = figure(112)
    rows = data["figure3"]["strategies"]
    axa = axes_mm(fig, 39, 79, 40, 26)
    axb = axes_mm(fig, 88, 79, 45, 26)
    panel(fig, 4, 106, "a", "Missed changes")
    panel(fig, 88, 106, "b", "Artifact builds")
    for ax in (axa, axb):
        ax.set_ylim(5.6, -0.6)
        ax.set_yticks(range(6))
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", color="#E7E7E7", linewidth=0.5, zorder=0)
        ax.spines["left"].set_visible(False)
    axa.set_yticklabels(STRATEGY_LABELS, fontsize=8)
    axb.set_yticklabels([])
    axa.set_xlim(0, 68)
    axa.set_xticks([0, 20, 40, 60])
    axa.set_xlabel("Missed changes (%)", labelpad=3, fontsize=8.5)
    axb.set_xlim(0, 82)
    axb.set_xticks([0, 20, 40, 60, 80])
    axb.set_xlabel("Number of builds", labelpad=3, fontsize=8.5)
    for i, row in enumerate(rows):
        color = BLUE if row["key"] == "checker" else ("#4F807A" if row["key"] == "declarative_omniscient" else GRAY)
        axa.plot(row["miss_rate"] * 100, i, "o", markersize=4, color=color, clip_on=False, zorder=5)
        label = f"{row['missed']}/43  ({100 * row['miss_rate']:.2f}%)" if row["missed"] else "0/43  (0%)"
        if row["missed"]:
            axa.text(3, i, label, ha="left", va="center", fontsize=7.8, bbox=WHITE_BOX.copy())
        else:
            axa.text(7, i, label, ha="left", va="center", fontsize=7.8, color=color, bbox=WHITE_BOX.copy())
        axb.barh(i, row["changed_rebuilt"], height=0.55, color=GREEN, edgecolor="#6E9691", linewidth=0.45)
        axb.barh(i, row["over_rebuilds"], left=row["changed_rebuilt"], height=0.55,
                 color=PURPLE, edgecolor="#8F789F", hatch="///", linewidth=0.45)
        axb.text(row["builds"] + 2, i, str(row["builds"]), va="center", ha="left", fontsize=8, bbox=WHITE_BOX.copy())
    for index, color in ((3, "#4F807A"), (4, BLUE)):
        axa.get_yticklabels()[index].set_color(color)
    legend(fig, [Patch(facecolor=GREEN, edgecolor="#6E9691"),
                 Patch(facecolor=PURPLE, edgecolor="#8F789F", hatch="///")],
           ["Changed and rebuilt", "Equal and rebuilt"], 80, 64.5, fontsize=8)
    panel(fig, 4, 55.5, "c", "Missed artifacts after each modification")
    axc = axes_mm(fig, 39, 28, 94, 23)
    matrix = np.array([row["step_misses"][1:] for row in rows], dtype=int)
    axc.imshow(matrix, vmin=-0.5, vmax=4.5, cmap=ListedColormap(["#F8F8F8", "#EBDCEB", "#D7BDD7", "#C39BC3", "#AA75AA"]),
               interpolation="nearest", aspect="auto")
    axc.set_yticks(range(6), STRATEGY_LABELS, fontsize=8)
    step_labels = []
    for step in data["figure3"]["sequence"][1:]:
        dims = step["changed_dimensions"]
        change = {"noise": "Noise", "decoder": "Decoder", "extractor": "Extraction", "arch": "Architecture"}.get(
            dims[0], "Code + extraction")
        step_labels.append(f"{step['step']}  {change}")
    axc.set_xticks(range(11), step_labels, rotation=42, ha="right", rotation_mode="anchor", fontsize=8)
    axc.tick_params(length=0, pad=4)
    axc.set_xticks(np.arange(-0.5, 11, 1), minor=True)
    axc.set_yticks(np.arange(-0.5, 6, 1), minor=True)
    axc.grid(which="minor", color="white", linewidth=0.75)
    axc.tick_params(which="minor", length=0)
    for spine in axc.spines.values():
        spine.set_visible(False)
    for (i, j), value in np.ndenumerate(matrix):
        axc.text(j, i, str(value), ha="center", va="center", fontsize=8, bbox=WHITE_BOX.copy())
    for i, color in ((3, "#4F807A"), (4, BLUE)):
        axc.get_yticklabels()[i].set_color(color)
    for label, step in zip(axc.get_xticklabels(), data["figure3"]["sequence"][1:]):
        if step["changed_dimensions"] == ["noise"]:
            label.set_bbox({**WHITE_BOX, "edgecolor": BLUE, "linewidth": 0.5})
    text_mm(fig, 83, 2.5, "Sequence step and changed coordinate(s)", fontsize=8.2, ha="center", va="bottom")
    return fig


def physical_labels():
    return ["Extraction\nzxcoloration → custom", "Architecture label\ntransversal → toric",
            "Noise\nSD6 → SI1000", "Decoder\nBP-OSD → BP-LSD"]


def figure4(data: dict):
    fig = figure(122)
    comparison_legend(fig, 118)
    for index, (bottom, title, ylabel, limits, ticks) in enumerate([
        (67, "Any observable is predicted to flip", "Any predicted flip\nfrequency (%)", (0, 55), [0, 10, 20, 30, 40, 50]),
        (10.5, "Mean predicted flip frequency", "Mean predicted flip\nfrequency (%)", (0, 17), [0, 4, 8, 12, 16]),
    ]):
        ax = axes_mm(fig, 16, bottom, 117, 37.5 if index == 0 else 35)
        panel(fig, 4, bottom + (42.5 if index == 0 else 39.5), "ab"[index], title)
        ax.set_xlim(-0.5, 3.5)
        ax.set_xticks(range(4), physical_labels(), fontsize=8)
        ax.tick_params(axis="x", length=0, pad=5)
        ax.set_ylim(*limits)
        ax.set_yticks(ticks)
        ax.set_ylabel(ylabel, labelpad=5, fontsize=9)
        ax.grid(axis="y", color="#E9E9E9", linewidth=0.45, zorder=0)
        for group, record in enumerate(data["figure4"]):
            base, alt = record["rates"]["base"], record["rates"]["alt"]
            key = "any_observable_rate" if index == 0 else "rate"
            for role, rate, x in (("base", base, group - 0.19), ("alt", alt, group + 0.19)):
                interval = rate["any_interval"] if index == 0 else (rate["wilson95_low"], rate["wilson95_high"])
                rate_bar(ax, x, rate[key], interval, role=role, approximate=index == 1)
                ax.annotate(f"{100 * rate[key]:.2f}%", (x, 100 * interval[1]), xytext=(0, 3.5),
                            textcoords="offset points", ha="center", va="bottom", fontsize=8,
                            bbox=WHITE_BOX.copy())
    return fig


CACHE_LABELS = [
    "DEM: extraction mismatch\nzxcoloration ← custom",
    "DEM: noise mismatch\nSI1000 ← SD6",
    "DEM: noise-scale mismatch\nSD6 (30×) ← SD6 (0.1×)",
    "DEM: extraction mismatch\n5 rounds; zxcoloration ← custom",
    "Circuit: round-count mismatch\n5 rounds ← cached 2 rounds",
    "Prediction cache omits noise\nSI1000 ← cached SD6",
]


def figure5(data: dict):
    fig = figure(132)
    comparison_legend(fig, 128, labels=("Current specification", "Stale artifact"))
    panel(fig, 4, 121.5, "a", "Predicted flip frequency under cache mismatch")
    axa = axes_mm(fig, 52, 65.5, 81, 50)
    axa.set_ylim(5.6, -0.6)
    axa.set_yticks(range(6), CACHE_LABELS, fontsize=8)
    axa.tick_params(axis="y", length=0, pad=6)
    axa.set_xlim(0, 60)
    axa.set_xticks([0, 10, 20, 30, 40, 50, 60])
    axa.set_xlabel("Mean predicted flip frequency (%)", fontsize=9, labelpad=4)
    axa.spines["left"].set_visible(False)
    axa.grid(axis="x", color="#E9E9E9", linewidth=0.45)
    axa.axhline(3.5, color="#BBBBBB", linestyle=(0, (2, 2)), linewidth=0.7)
    for row, record in enumerate(data["figure5"]):
        fresh, stale = record["fresh"], record["stale"]
        for role, rate, y in (("base", fresh, row - 0.22), ("alt", stale, row + 0.22)):
            interval = (rate["wilson95_low"], rate["wilson95_high"])
            rate_bar(axa, y, rate["rate"], interval, role=role,
                     horizontal=True, approximate=True, width=0.34)
            axa.text(100 * interval[1] + 0.8, y, f"{100 * rate['rate']:.3f}%",
                     ha="left", va="center", fontsize=8, bbox=WHITE_BOX.copy())
    text_mm(fig, 70, 51, "Two recorded calls: 49.87% of bits differ; aggregate frequencies remain close",
            fontsize=8.1, ha="center", va="center")
    panel(fig, 4, 45, "b", "Prediction bits differing between calls")
    axb = axes_mm(fig, 52, 10.5, 81, 30.5)
    axb.set_ylim(3.6, -0.6)
    axb.set_yticks(range(4), CACHE_LABELS[:4], fontsize=8)
    axb.tick_params(axis="y", length=0, pad=6)
    axb.set_xscale("log")
    axb.set_xlim(0.001, 100)
    axb.set_xticks([0.001, 0.01, 0.1, 1, 10, 100], ["0.001", "0.01", "0.1", "1", "10", "100"])
    axb.set_xlabel("Different prediction bits (%, log scale)", fontsize=9, labelpad=3)
    axb.spines["left"].set_visible(False)
    axb.grid(axis="x", which="major", color="#E9E9E9", linewidth=0.45)
    axb.tick_params(axis="x", which="minor", bottom=False)
    for row, record in enumerate(data["figure5"][:4]):
        value = record["percent_different"]
        # A logarithmic axis has no zero; every bar starts at the visible 0.001% bound.
        axb.barh(row, value - 0.001, left=0.001, height=0.44, color=BLUE,
                 edgecolor=BLUE, linewidth=0.65, zorder=3)
        message = f"{value:.5g}%\n{record['different']:,}/{record['total']:,}"
        axb.annotate(message, (value, row), xytext=(-6, 0) if row == 2 else (6, 0),
                     textcoords="offset points", ha="right" if row == 2 else "left",
                     va="center", fontsize=8, color=BLUE, bbox=WHITE_BOX.copy())
    return fig


RENDERERS = {2: figure2, 3: figure3, 4: figure4, 5: figure5}
