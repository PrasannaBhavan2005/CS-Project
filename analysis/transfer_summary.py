"""Per-path byte accounting for testbed/run_transfer.sh.

  transfer_summary.py run <run_dir>        write <run_dir>/summary.csv, print it
  transfer_summary.py table <scenario_dir> print all runs of a scenario

Bytes per path come from the kernel veth counters (snapshots before and after
the transfer); drops are from the tbf bottleneck queue on the server side.
"""

import csv
import json
import sys
from pathlib import Path

NS_CLI, NS_SRV = "mpq-cli", "mpq-srv"
PATHS = {"a": ("cA", "sA"), "b": ("cB", "sB")}
FIELDS = [
    "scenario", "scheduler", "run_id", "file_ok", "transfer_s", "goodput_mbps",
    "down_bytes_a", "down_bytes_b", "share_a_pct", "share_b_pct",
    "up_bytes_a", "up_bytes_b", "drops_a", "drops_b",
]


def load(run_dir, tag, ns, kind):
    return json.loads((run_dir / f"{tag}.{ns}.{kind}.json").read_text())


def link_bytes(run_dir, ns, dev, direction):
    """Bytes counted on dev during the transfer (after - before)."""
    def get(tag):
        for link in load(run_dir, tag, ns, "link"):
            if link["ifname"] == dev:
                return link["stats64"][direction]["bytes"]
        raise KeyError(dev)
    return get("after") - get("before")


def tbf_drops(run_dir, ns, dev):
    def get(tag):
        return sum(q["drops"] for q in load(run_dir, tag, ns, "qdisc")
                   if q["dev"] == dev and q["kind"] == "tbf")
    return get("after") - get("before")


def summarize_run(run_dir):
    meta = dict(line.split("=", 1) for line in
                (run_dir / "meta.env").read_text().splitlines() if "=" in line)
    row = {"scenario": meta["SCENARIO"], "scheduler": meta["SCHEDULER"],
           "run_id": meta["RUN_ID"], "file_ok": meta["FILE_OK"],
           "transfer_s": round(float(meta["TRANSFER_S"]), 3)}
    for p, (cli_dev, srv_dev) in PATHS.items():
        # Download direction (server -> client) is what the scheduler splits.
        row[f"down_bytes_{p}"] = link_bytes(run_dir, NS_CLI, cli_dev, "rx")
        row[f"up_bytes_{p}"] = link_bytes(run_dir, NS_CLI, cli_dev, "tx")
        row[f"drops_{p}"] = tbf_drops(run_dir, NS_SRV, srv_dev)
    total = row["down_bytes_a"] + row["down_bytes_b"]
    for p in PATHS:
        row[f"share_{p}_pct"] = round(100 * row[f"down_bytes_{p}"] / total, 1) if total else 0.0
    row["goodput_mbps"] = round(int(meta["FILE_BYTES"]) * 8 / row["transfer_s"] / 1e6, 2)
    with open(run_dir / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerow(row)
    return row


def print_rows(rows):
    cols = ["scheduler", "run_id", "file_ok", "transfer_s", "goodput_mbps",
            "share_a_pct", "share_b_pct", "down_bytes_a", "down_bytes_b", "drops_a", "drops_b"]
    print("  ".join(f"{c:>12}" for c in cols))
    for r in rows:
        print("  ".join(f"{str(r[c]):>12}" for c in cols))


def main():
    mode, path = sys.argv[1], Path(sys.argv[2])
    if mode == "run":
        row = summarize_run(path)
        print(f"{row['scheduler']} run {row['run_id']}: file_ok={row['file_ok']} "
              f"{row['transfer_s']}s  A={row['share_a_pct']}%  B={row['share_b_pct']}%")
    elif mode == "table":
        rows = []
        for f in sorted(path.glob("*/*/summary.csv")):
            with open(f) as fh:
                rows.extend(csv.DictReader(fh))
        rows.sort(key=lambda r: (r["scheduler"], int(r["run_id"])))
        print_rows(rows)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
