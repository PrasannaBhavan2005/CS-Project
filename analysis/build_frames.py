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
    raw_sent = list(csv.DictReader(open(run / "send.csv")))
    recv = {r["frame_id"]: r for r in csv.DictReader(open(run / "recv.csv"))}

    stream_frame = {}
    frames_ordered = []
    frame_meta = {}
    for r in raw_sent:
        fid = r["frame_id"]
        stream_frame[r["stream_id"]] = fid
        rescued = int(r.get("rescued", 0))
        if fid not in frame_meta:
            frames_ordered.append(fid)
            frame_meta[fid] = {
                "frame_id": fid,
                "frame_type": r["frame_type"],
                "size_bytes": r["size_bytes"],
                "capture_ts_us": r["capture_ts_us"],
                "send_start_us": r["send_start_us"],
                "rescued": rescued,
            }
        else:
            frame_meta[fid]["send_start_us"] = str(min(int(frame_meta[fid]["send_start_us"]), int(r["send_start_us"])))
            frame_meta[fid]["rescued"] += rescued

    by_frame = {}
    totals = {"A": 0, "B": 0, "other": 0}
    bad = 0
    for r in csv.DictReader(open(run / "frame_path.csv")):
        if r.get("local") is None or not r["len"].isdigit():
            bad += 1
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
        for fid in frames_ordered:
            s = frame_meta[fid]
            r = recv.get(fid, {})
            complete = r.get("complete_ts_us", "")
            done += complete != ""
            b = by_frame.get(fid, {"A": 0, "B": 0})
            w.writerow([s["frame_id"], s["frame_type"], s["size_bytes"], s["capture_ts_us"],
                        s["send_start_us"], complete, b["A"], b["B"], s["rescued"], meta["config"],
                        meta["scenario"], meta["bitrate_kbps"], meta["encoding"], meta["clip"],
                        meta["run_id"]])
    print(f"frames: {len(frames_ordered)} sent, {done} complete; stream bytes A={totals['A']} "
          f"B={totals['B']} other={totals['other']}; malformed frame_path lines: {bad}")
    print(json.dumps({"frames_sent": len(frames_ordered), "frames_complete": done,
                      "stream_bytes_a": totals["A"], "stream_bytes_b": totals["B"],
                      "stream_bytes_other": totals["other"], "frame_path_malformed": bad}))


if __name__ == "__main__":
    main()