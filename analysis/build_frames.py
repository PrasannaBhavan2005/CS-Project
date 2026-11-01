"""Build a run's frames.csv from the streamer logs (called by scripts/run.sh).

  build_frames.py <run_dir> <path A local ip> <path B local ip>

Reads send.csv (sender), recv.csv (receiver) and frame_path.csv (TQUIC's
per-STREAM-frame log) and meta.json (run parameters). Writes frames.csv, one
row per frame in send order, on one clock (CLOCK_MONOTONIC, us):

  frame_id, frame_type, size_bytes, capture_ts_us, send_start_us,
  complete_ts_us (empty if the frame never completed), bytes_path0 (A),
  bytes_path1 (B), rescued, config, scenario, bitrate_kbps, encoding, clip,
  run_id

bytes_path0/1: stream bytes the sender put on each path for the frame's
streams, including retransmissions and the 16-byte part header. rescued:
number of rescue parts (0 until F2/A1 exist). Prints a one-line summary and
the per-path byte totals.
"""

import csv
import json
import sys
from pathlib import Path

COLS = ["frame_id", "frame_type", "size_bytes", "capture_ts_us", "send_start_us",
        "complete_ts_us", "bytes_path0", "bytes_path1", "rescued", "config", "scenario",
        "bitrate_kbps", "encoding", "clip", "run_id"]


def main():
    run = Path(sys.argv[1])
    ip_a, ip_b = sys.argv[2], sys.argv[3]
    meta = json.loads((run / "meta.json").read_text())
    sent = list(csv.DictReader(open(run / "send.csv")))
    recv = {r["frame_id"]: r for r in csv.DictReader(open(run / "recv.csv"))}

    stream_frame = {r["stream_id"]: r["frame_id"] for r in sent}
    by_frame = {}
    totals = {"A": 0, "B": 0, "other": 0}
    bad = 0
    for r in csv.DictReader(open(run / "frame_path.csv")):
        if r.get("local") is None or not r["len"].isdigit():
            bad += 1  # a line cut short when the sender died; reported below
            continue
        ip = r["local"].rsplit(":", 1)[0]
        p = "A" if ip == ip_a else "B" if ip == ip_b else "other"
        n = int(r["len"])
        totals[p] += n
        fid = stream_frame.get(r["stream_id"])
        if fid is not None:
            d = by_frame.setdefault(fid, {"A": 0, "B": 0, "other": 0})
            d[p] += n

    with open(run / "frames.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLS)
        done = 0
        for s in sent:
            r = recv.get(s["frame_id"], {})
            complete = r.get("complete_ts_us", "")
            done += complete != ""
            b = by_frame.get(s["frame_id"], {"A": 0, "B": 0})
            w.writerow([s["frame_id"], s["frame_type"], s["size_bytes"], s["capture_ts_us"],
                        s["send_start_us"], complete, b["A"], b["B"], 0, meta["config"],
                        meta["scenario"], meta["bitrate_kbps"], meta["encoding"], meta["clip"],
                        meta["run_id"]])
    print(f"frames: {len(sent)} sent, {done} complete; stream bytes A={totals['A']} "
          f"B={totals['B']} other={totals['other']}; malformed frame_path lines: {bad}")
    print(json.dumps({"frames_sent": len(sent), "frames_complete": done,
                      "stream_bytes_a": totals["A"], "stream_bytes_b": totals["B"],
                      "stream_bytes_other": totals["other"], "frame_path_malformed": bad}))


if __name__ == "__main__":
    main()
