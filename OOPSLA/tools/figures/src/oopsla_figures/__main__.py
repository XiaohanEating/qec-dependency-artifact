"""One command renders requested figures and records source/output fingerprints."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
import numpy as np
from matplotlib import pyplot as plt

from .data import FIGURE_ROOT, load_data, sha256, write_json
from .render import RENDERERS
from .style import configure, export


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--figures", nargs="+", type=int, choices=tuple(RENDERERS), default=list(RENDERERS))
    args = parser.parse_args()
    font = configure()
    data = load_data()
    write_json(FIGURE_ROOT / "data/display-data.json", data)
    report_path = FIGURE_ROOT / "provenance/render-verification.json"
    previous = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    outputs = [item for item in previous.get("outputs", []) if item["figure"] not in args.figures]
    for item in outputs:
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"Retained figure differs from its registered output: {item['path']}")
    retained = sorted({item["figure"] for item in outputs})
    layouts = {key: value for key, value in previous.get("layouts", {}).items() if int(key) in retained}
    for number in args.figures:
        fig = RENDERERS[number](data)
        layouts[str(number)] = export(fig, FIGURE_ROOT / "outputs" / f"figure{number}")
        for extension in ("pdf", "png", "svg"):
            path = FIGURE_ROOT / "outputs" / f"figure{number}.{extension}"
            outputs.append({"figure": number, "path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size})
        plt.close(fig)
    for item in data["sources"].values():
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError("Experiment input changed while rendering")
    source_paths = sorted((FIGURE_ROOT / "src/oopsla_figures").glob("*.py"))
    current_time = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    source_records = [{"path": str(p), "sha256": sha256(p)} for p in source_paths]
    runs = previous.get("render_runs", [])
    if previous and not runs:
        runs = [{"time": previous["time"], "figures": sorted(previous["layouts"]),
                 "sources": previous["sources"]}]
    runs.append({"time": current_time, "figures": args.figures, "sources": source_records})
    report = {"time": current_time, "python": sys.version,
              "executable": sys.executable, "platform": platform.platform(), "matplotlib": matplotlib.__version__,
              "numpy": np.__version__, "font": font, "experiment_sources": data["sources"],
              "sources": source_records, "render_runs": runs,
              "rendered_figures_this_run": args.figures, "retained_figures": retained,
              "outputs": sorted(outputs, key=lambda item: (item["figure"], item["path"])),
              "layouts": layouts, "new_experiments": False,
              "data_verified": True, "visual_review": "pending"}
    write_json(report_path, report)
    print(f"Rendered figures {args.figures}; {3 * len(args.figures)} new files; "
          f"{len(outputs)} recorded files; data and text backgrounds checked.")


if __name__ == "__main__":
    main()
