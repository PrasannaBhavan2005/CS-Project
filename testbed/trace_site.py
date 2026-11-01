"""Read a trace site: traces/<site>/site.json plus one csv per path.

  trace_site.py env <site>      print shell assignments for testbed/up.sh real_pairs
  trace_site.py stats <site>    print per-path rate statistics

site.json: {"paths": {"A": {"trace": "<file>.csv", "unloaded_rtt_ms": N,
"operator": ...}, "B": {...}}, ...}. Trace csv: t_ms,mbps,capped,loaded_rtt_ms,
one row per 100 ms bin (docs/trace_collection.md). The replay delay is the
unloaded RTT (ping before and after the iperf3 run), never the loaded RTT,
which already contains the phone's uplink queue.
"""

import csv
import json
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN_MS = 100


def load(site):
    d = REPO / "traces" / site
    meta = json.loads((d / "site.json").read_text())
    paths = {}
    for p, info in meta["paths"].items():
        with open(d / info["trace"]) as f:
            rows = list(csv.DictReader(f))
        t = [int(r["t_ms"]) for r in rows]
        if t != list(range(0, BIN_MS * len(t), BIN_MS)):
            sys.exit(f"trace_site.py: {info['trace']}: t_ms must be 0, {BIN_MS}, {2 * BIN_MS}, ...")
        paths[p] = {
            "kbit": [round(float(r["mbps"]) * 1000) for r in rows],
            "capped": [r["capped"] == "1" for r in rows],
            "rtt_ms": round(float(info["unloaded_rtt_ms"])),
        }
    return meta, paths


def main():
    cmd, site = sys.argv[1:3]
    meta, paths = load(site)
    if cmd == "env":
        for p, v in paths.items():
            mean = round(statistics.fmean(v["kbit"]))
            print(f"{p.lower()}_rate={mean} {p.lower()}_rtt={v['rtt_ms']}")
    elif cmd == "stats":
        for p, v in paths.items():
            k = sorted(v["kbit"])
            q = lambda x: k[int(x * (len(k) - 1))] / 1000
            print(f"{p}: {len(k)} bins, mean {statistics.fmean(k) / 1000:.2f} Mbit/s, "
                  f"p10 {q(0.1):.2f}, p50 {q(0.5):.2f}, p90 {q(0.9):.2f}, "
                  f"zero {sum(x == 0 for x in k) / len(k):.1%}, "
                  f"capped {sum(v['capped']) / len(k):.1%}, unloaded RTT {v['rtt_ms']} ms")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
