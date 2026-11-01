"""Turn one site's raw recordings into a trace site for testbed/up.sh real_pairs.

  make_site.py <site> --a-json F --a-first F --a-ping-before F --a-ping-during F
               --a-ping-after F --a-operator NAME   (same six for --b-...)
               --offered-mbps 15 [--note TEXT]

Inputs (docs/trace_collection.md): the VM's iperf3 server log (100 ms
receiver-side bins) and first-packet time (vm_server.sh), and the phone's three
ping logs (`ping -D`). Writes traces/<site>/a.csv, b.csv and site.json.

- mbps: IP-level rate per 100 ms bin = (UDP payload + 28 bytes per datagram)
  received by the VM.
- capped = 1 when the bin's payload rate is within 5% of the offered rate: the
  link may have had more capacity than we offered.
- loaded_rtt_ms: median RTT of the during-test pings sent in that bin
  (reference only; contains the phone's uplink queue). Empty if none.
- unloaded_rtt_ms (site.json): median of the before and after pings; this is
  the replay delay.
- Both paths are cut to the time both were running (VM clock), starting at 0.
"""

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BIN = 0.1
UDP_IP_HDR = 28
CAP_FRAC = 0.95


def server_bins(json_path, first_path):
    d = json.loads(Path(json_path).read_text())
    if "error" in d:
        sys.exit(f"{json_path}: iperf3 error: {d['error']}")
    payload = d["start"]["test_start"]["blksize"]
    first = float(Path(first_path).read_text().split()[0])
    out = []
    for iv in d["intervals"]:
        s = iv["sum"]
        if s["end"] - s["start"] < BIN / 2:
            continue  # final partial interval
        pkts = s["bytes"] / payload
        secs = s["end"] - s["start"]
        out.append((first + s["start"],
                    (s["bytes"] + pkts * UDP_IP_HDR) * 8 / secs / 1e6,
                    s["bytes"] * 8 / secs / 1e6))
    return out, payload


def pings(path):
    """[(unix time, rtt ms)] from `ping -D` output."""
    rows = re.findall(r"^\[(\d+\.\d+)\].*time=([\d.]+) ms", Path(path).read_text(), re.M)
    return [(float(t), float(r)) for t, r in rows]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("site")
    for p in "ab":
        for k in ("json", "first", "ping-before", "ping-during", "ping-after", "operator"):
            ap.add_argument(f"--{p}-{k}", required=True)
    ap.add_argument("--offered-mbps", type=float, required=True)
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    v = vars(a)

    data = {}
    for p in "ab":
        bins, payload = server_bins(v[f"{p}_json"], v[f"{p}_first"])
        unloaded = [r for _, r in pings(v[f"{p}_ping_before"]) + pings(v[f"{p}_ping_after"])]
        if not unloaded:
            sys.exit(f"path {p}: no unloaded pings")
        data[p] = dict(bins=bins, payload=payload, during=pings(v[f"{p}_ping_during"]),
                       unloaded=unloaded)

    start = max(data[p]["bins"][0][0] for p in "ab")
    end = min(data[p]["bins"][-1][0] for p in "ab")
    out = REPO / "traces" / a.site
    if out.exists():
        sys.exit(f"{out} exists; traces are never overwritten")
    out.mkdir(parents=True)
    meta = {"site": a.site, "kind": "measured (own two-operator recording)",
            "offered_mbps": a.offered_mbps, "bin_ms": 100, "note": a.note, "paths": {}}
    for p in "ab":
        d = data[p]
        rows = [b for b in d["bins"] if start - BIN / 2 <= b[0] <= end + BIN / 2]
        # Loaded pings by bin. Phone clock vs VM clock: aligned on the first
        # bin, so loaded RTT is approximate in time (reference only).
        ph0 = d["during"][0][0] if d["during"] else 0
        by_bin = {}
        for t, r in d["during"]:
            by_bin.setdefault(int((t - ph0) / BIN), []).append(r)
        lines = ["t_ms,mbps,capped,loaded_rtt_ms"]
        capped = 0
        for i, (_, ip_mbps, pay_mbps) in enumerate(rows):
            c = int(pay_mbps >= CAP_FRAC * a.offered_mbps)
            capped += c
            lr = by_bin.get(i)
            lines.append(f"{i * 100},{ip_mbps:.3f},{c},{statistics.median(lr):.1f}" if lr
                         else f"{i * 100},{ip_mbps:.3f},{c},")
        name = f"{p}.csv"
        (out / name).write_text("\n".join(lines) + "\n")
        meta["paths"][p.upper()] = {
            "operator": v[f"{p}_operator"], "trace": name,
            "unloaded_rtt_ms": round(statistics.median(d["unloaded"]), 1),
            "unloaded_pings": len(d["unloaded"]),
            "payload_bytes": d["payload"], "bins": len(rows),
            "capped_share": round(capped / len(rows), 4),
            "sources": {k: Path(v[f"{p}_{k.replace('-', '_')}"]).name
                        for k in ("json", "first", "ping-before", "ping-during", "ping-after")},
        }
    (out / "site.json").write_text(json.dumps(meta, indent=2) + "\n")
    for p, m in meta["paths"].items():
        print(f"{p}: {m['operator']}, {m['bins']} bins, capped {m['capped_share']:.1%}, "
              f"unloaded RTT {m['unloaded_rtt_ms']} ms")


if __name__ == "__main__":
    main()
