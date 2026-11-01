"""Per-run metrics for every streaming run under results/.

  summarize.py [--out runs.csv] [results dir, default results]

A run is any directory with frames.csv and meta.json
(results/<scenario>/<config>/<bitrate>_<encoding>_<clip>/<run_id>/). One row
per run: identifiers, flags (stalled, cpu_over_80: reported, never averaged
in), playout metrics at D = 150 / 250 / 400 ms (analysis/playout.py), the
required playout delay, the share of frame bytes per path and the bytes sent
beyond each frame's size (retransmissions, redundancy, headers).
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import playout  # noqa: E402

ID_COLS = ["scenario", "site", "config", "bitrate_kbps", "encoding", "clip", "run_id"]


def load_frames(path):
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        r["capture_ts_us"] = int(r["capture_ts_us"])
        r["complete_ts_us"] = int(r["complete_ts_us"]) if r["complete_ts_us"] else None
        for k in ("size_bytes", "bytes_path0", "bytes_path1"):
            r[k] = int(r[k])
    return rows


def summarize(run):
    meta = json.loads((run / "meta.json").read_text())
    frames = load_frames(run / "frames.csv")
    row = {k: meta.get(k, "") for k in ID_COLS}
    row.update(stalled=meta.get("stalled", ""), cpu_over_80=meta.get("cpu_over_80", ""),
               clip_offset_frames=meta["clip_offset_frames"], trace_offset_ms=meta["trace_offset_ms"])
    if not frames:
        row["frames"] = 0
        return row
    m, _ = playout.run_metrics(frames, meta["encoding"])
    row.update(m)
    a = sum(f["bytes_path0"] for f in frames)
    b = sum(f["bytes_path1"] for f in frames)
    size = sum(f["size_bytes"] for f in frames)
    row.update(share_a=a / (a + b) if a + b else math.nan, bytes_a=a, bytes_b=b,
               extra_bytes_frac=(a + b - size) / size)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="?", default="results", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    rows = [summarize(p.parent) for p in sorted(a.results.glob("**/frames.csv"))]
    if not rows:
        sys.exit("no runs found")
    cols = list(dict.fromkeys(k for r in rows for k in r))
    w = csv.DictWriter(open(a.out, "w", newline="") if a.out else sys.stdout, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)


if __name__ == "__main__":
    main()
