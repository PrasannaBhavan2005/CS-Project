"""Frame-size summary of one or more frame traces (workload/encode.sh).

  frame_stats.py <trace.csv> ...

Per trace: frames, frame rate, mean bitrate, I-frame count and sizes, P-frame
median / p95 / max, the largest frame relative to the mean frame, and the
highest bitrate over any 1 s window (sum of frame sizes, by frame count).
"""

import csv
import statistics
import sys


def pct(xs, q):
    xs = sorted(xs)
    return xs[round(q * (len(xs) - 1))]


def stats(path):
    rows = list(csv.DictReader(open(path)))
    sizes = [int(r["size_bytes"]) for r in rows]
    types = [r["frame_type"] for r in rows]
    pts = [int(r["pts_ms"]) for r in rows]
    n = len(rows)
    fps = round((n - 1) * 1000 / (pts[-1] - pts[0]))
    dur_s = n / fps
    i_sz = [s for s, t in zip(sizes, types) if t == "I"]
    p_sz = [s for s, t in zip(sizes, types) if t != "I"]
    win = max(sum(sizes[k:k + fps]) for k in range(n - fps + 1))
    mean = statistics.fmean(sizes)
    return (f"{path}: {n} frames at {fps} fps ({dur_s:.1f} s), "
            f"mean {sum(sizes) * 8 / dur_s / 1000:.0f} kbit/s, mean frame {mean / 1000:.1f} KB; "
            f"I: {len(i_sz)} (median {statistics.median(i_sz) / 1000:.1f} KB, max {max(i_sz) / 1000:.1f} KB); "
            f"P: median {statistics.median(p_sz) / 1000:.1f} KB, p95 {pct(p_sz, 0.95) / 1000:.1f} KB, "
            f"max {max(p_sz) / 1000:.1f} KB; largest frame {max(sizes) / mean:.1f}x mean; "
            f"max 1 s window {win * 8 / 1000:.0f} kbit/s")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(stats(p))
