"""Where an experiment writes its artifacts (``--out DIR``), and how the
drift check compares them.

Every experiment script has two behaviours that must stay separable:

* **publishing** — ``main()`` with no ``--out`` writes ``<name>.json`` /
  ``<name>.md`` *next to the script*, i.e. into the checked-in artifact
  directory that ``.github/workflows/ci.yml``'s drift check compares against
  the repository;
* **self-testing** — the pytest suite calls the very same ``main()`` to verify
  that the script still runs end to end.

Before this module existed, the two were the same call and running the suite
*overwrote the published artifacts* with quick-mode output
(``SUBMISSION_READINESS.md`` §3.4-D): ``stim_circuit_gate`` and
``dynamic_impact`` took a ``--quick`` flag, ``cone_table`` a ``--configs 24``
flag, and in each case the quick-mode run produced a *different object* (fewer
rows, fewer probes, and — because ``quant_evidence._import_pinned_quits``
leaked the pinned tree onto ``sys.path`` — a different ``metadata.quits_file``)
under the same filename.  The tests now pass ``--out <tmpdir>`` so that

1. the published artifacts can only be produced by an explicit full-mode run,
   and the CI drift check compares like with like;
2. no test can silently "publish" a number the paper does not claim.

Usage::

    def main(argv: list[str] | None = None) -> int:
        argv = list(sys.argv[1:] if argv is None else argv)
        out = outdir.resolve_out(argv, HERE)
        ...
        (out / "cone_table.json").write_text(...)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

#: the flag every experiment ``main()`` understands
FLAG = "--out"


def resolve_out(argv: list[str] | None, default: Path) -> Path:
    """The directory this run writes into.

    ``argv`` defaults to the process arguments, so a plain
    ``python experiments/<script>.py`` publishes to ``default`` (the script's
    own directory) while ``--out /tmp/scratch`` publishes elsewhere.  The
    directory is created if missing, so callers can pass a fresh
    ``tmp_path`` fixture without setting it up.
    """
    argv = list(sys.argv[1:] if argv is None else argv)
    if FLAG in argv:
        i = argv.index(FLAG)
        if i + 1 >= len(argv):
            raise SystemExit(f"{FLAG} requires a directory argument")
        out = Path(argv[i + 1])
    else:
        out = default
    out.mkdir(parents=True, exist_ok=True)
    return out


# ---------------------------------------------------------------------------
# drift comparison
# ---------------------------------------------------------------------------
#
# A checked-in artifact is compared byte-for-byte against a fresh run.  Two
# classes of difference are *not* drift and must be normalised away, or CI is
# red for reasons that have nothing to do with the artifact:
#
# 1. **machine-dependent absolute paths.**  Three outputs record where the
#    pinned QUITS tree lives (`metadata.quits_src` / `metadata.quits_file`,
#    and the same string in the Markdown header).  That path is a property of
#    the checkout, not of the result (README §6).
# 2. **the generation date.**  Five of the seven scripts stamp
#    ``date.today().isoformat()`` into both the JSON metadata and the Markdown
#    header.  Comparing those literally means the drift check turns red at
#    midnight on any run that was not made on the day the artifact was
#    committed — a false positive that recurs every single day.  Measured on
#    2026-10-10: all eight ``*.json`` / ``*.md`` files of four of the
#    experiments differed from their regenerated copies *in the date line
#    only*.
#
# Everything else is compared literally.  In particular a changed number, a
# changed modelling provenance string or a changed verdict is still drift.

#: ``"date": "2026-10-09"`` in the JSON metadata blocks
_JSON_DATE_RE = re.compile(r'("date"\s*:\s*)"\d{4}-\d{2}-\d{2}"')
#: ``Generated: 2026-10-09  `` in the Markdown headers
_MD_DATE_RE = re.compile(r'(Generated:\s*)\d{4}-\d{2}-\d{2}')

#: what a normalised volatile field looks like
_PLACEHOLDER = "<VOLATILE>"


def normalise_for_drift(text: str, repo_root: Path | str | None = None) -> str:
    """Make one artifact comparable with another (see the notes above).

    ``repo_root`` defaults to the artifact root (``<repo>/OOPSLA``'s parent).
    Both separator spellings are blanked, because the JSON escapes backslashes
    while the Markdown does not.
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]
    root = str(repo_root)
    for spelling in {root,
                     root.replace("\\", "/"),
                     root.replace("/", "\\"),
                     # JSON escapes the backslash, so `"C:\\work\\repo"` never
                     # contains the raw `C:\work\repo`; blank that spelling too
                     # or the check silently keeps the path on Windows.
                     root.replace("\\", "\\\\")}:
        if spelling:
            text = text.replace(spelling, "<REPO>")
    text = _JSON_DATE_RE.sub(rf'\1"{_PLACEHOLDER}"', text)
    text = _MD_DATE_RE.sub(rf"\g<1>{_PLACEHOLDER}", text)
    return text


def drift_report(committed_dir: Path, regenerated_dir: Path,
                 repo_root: Path | str | None = None) -> list[str]:
    """Names of the regenerated files that differ from the committed ones.

    Shared by ``.github/workflows/ci.yml`` and
    ``experiments/test_artifact_hygiene.py`` so the CI gate and the local
    regression test can never drift apart.  Returns ``[]`` when everything
    matches; files that only exist on one side are ignored (a *new* output is
    a review question, not a stale-artifact failure).
    """
    stale: list[str] = []
    for new in sorted(Path(regenerated_dir).glob("*")):
        if not new.is_file() or new.suffix not in (".json", ".md"):
            continue
        old = Path(committed_dir) / new.name
        if not old.is_file():
            continue
        if normalise_for_drift(old.read_text(encoding="utf-8"), repo_root) != \
                normalise_for_drift(new.read_text(encoding="utf-8"), repo_root):
            stale.append(new.name)
    return stale
