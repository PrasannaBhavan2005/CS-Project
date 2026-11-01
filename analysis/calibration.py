"""Summarise emulator calibration runs (testbed/calibrate.sh).

  calibration.py <run_dir> ...        one markdown block per run
  calibration.py --csv out.csv <run_dir> ...   also write per-bin data

Per path:
- RTT: unloaded ping (10 Hz, 10 s) vs configured RTT.
- Rate: iperf3 server-side 100 ms bins of UDP payload, converted to wire bytes
  (payload + 42 B: UDP 8 + IPv4 20 + Ethernet 14; tbf counts the Ethernet
  header, see tc_cli.txt), vs the rate configured for that bin. For outage and
  real_pairs the configured rate comes from replay.csv, averaged over each bin;
  the iperf3 clock is aligned to the replay clock by the shift (searched over
  -1..+1 s in 10 ms steps) that minimises the mean absolute error. The shift is
  reported. The first 1 s (queue filling) and the last bin are left out.
"""

import argparse
import csv
import json
import re
import statistics
from pathlib import Path

HDR = 42
SKIP_S = 1.0


def env(path):
    return dict(l.split("=", 1) for l in path.read_text().splitlines() if "=" in l)


def ping_stats(path):
    rtts = [float(m) for m in re.findall(r"time=([\d.]+) ms", path.read_text())]
    rtts.sort()
    q = lambda x: rtts[round(x * (len(rtts) - 1))]
    return len(rtts), rtts[0], q(0.5), q(0.95)


def iperf_bins(path, payload):
    """[(start_s, end_s, wire_kbit)] from the iperf3 server report."""
    d = json.loads(path.read_text())
    out = []
    for iv in d["intervals"]:
        s = iv["sum"]
        secs = s["end"] - s["start"]
        if secs <= 0:
            continue
        pkts = s["bytes"] / payload
        out.append((s["start"], s["end"], (s["bytes"] + pkts * HDR) * 8 / secs / 1000))
    return out


def replay_steps(path, dev):
    """[(t_s, kbit)] for one device, times relative to replay t0 (monotonic)."""
    rows = list(csv.DictReader(open(path)))
    t0 = int(rows[0]["mono_us"])
    return [((int(r["mono_us"]) - t0) / 1e6, int(r["kbit"])) for r in rows if r["dev"] == dev]


def rate_over(steps, a, b):
    """Time-weighted configured rate over [a, b) from a step function."""
    total = 0.0
    for i, (t, k) in enumerate(steps):
        t_next = steps[i + 1][0] if i + 1 < len(steps) else float("inf")
        lo, hi = max(a, t), min(b, t_next)
        if hi > lo:
            total += k * (hi - lo)
    return total / (b - a)


def pct(xs, q):
    xs = sorted(xs)
    return xs[round(q * (len(xs) - 1))]


def analyse(run):
    m = env(run / "meta.env")
    payload = int(m["PAYLOAD_BYTES"])
    timed = (run / "replay.csv").exists()
    res = {"run": run, "meta": m, "paths": {}}
    if timed:
        rp_t0 = int(next(csv.DictReader(open(run / "replay.csv")))["mono_us"])
        base_shift = (int(m["IPERF_START_MONO_US"]) - rp_t0) / 1e6
    for p in "AB":
        n, mn, med, p95 = ping_stats(run / f"ping_{p}.txt")
        bins = [b for b in iperf_bins(run / f"iperf_{p}.json", payload)][:-1]
        bins = [b for b in bins if b[0] >= SKIP_S]
        if timed:
            steps = replay_steps(run / "replay.csv", f"c{p}")
            best = None
            for k in range(-100, 101):
                sh = base_shift + k / 100
                exp = [rate_over(steps, s + sh, e + sh) for s, e, _ in bins]
                err = statistics.fmean(abs(w - x) for (_, _, w), x in zip(bins, exp))
                if best is None or err < best[0]:
                    best = (err, sh, exp)
            _, shift, exp = best
        else:
            shift = None
            exp = [float(m[f"{p}_RATE_KBIT"])] * len(bins)
        meas = [w for _, _, w in bins]
        rel = [(w - x) / x for w, x in zip(meas, exp) if x > 100]
        # 1 s windows: 10 consecutive bins
        sec = [(sum(meas[i:i + 10]), sum(exp[i:i + 10])) for i in range(0, len(meas) - 9, 10)]
        rel1 = [(a - b) / b for a, b in sec if b > 1000]
        res["paths"][p] = dict(
            rtt_cfg=float(m[f"{p}_RTT_MS"]), ping_n=n, rtt_min=mn, rtt_med=med, rtt_p95=p95,
            offered=int(m[f"OFFERED_{p}_KBIT"]), bins=len(bins), shift=shift,
            meas_mean=statistics.fmean(meas), exp_mean=statistics.fmean(exp),
            rel_med=pct(rel, 0.5), rel_p5=pct(rel, 0.05), rel_p95=pct(rel, 0.95),
            rel1_med=pct(rel1, 0.5) if rel1 else None,
            rel1_p5=pct(rel1, 0.05) if rel1 else None,
            rel1_p95=pct(rel1, 0.95) if rel1 else None,
            low_bins=[(round(s, 1), round(w), round(x)) for (s, _, w), x in zip(bins, exp) if x <= 100],
            series=list(zip([b[0] for b in bins], meas, exp)),
        )
    return res


def fmt(r):
    m = r["meta"]
    name = f"{m['SCENARIO']}{'_' + m['SITE'] if m.get('SITE') else ''}/{m.get('RUN_ID', r['run'].name)}"
    lines = [f"### {name}", "",
             "| path | RTT cfg | ping min / med / p95 | rate cfg (mean) | measured mean | 100 ms bins: error p5 / med / p95 | 1 s: error p5 / med / p95 | clock shift |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for p, v in r["paths"].items():
        one = (f"{v['rel1_p5']:+.1%} / {v['rel1_med']:+.1%} / {v['rel1_p95']:+.1%}"
               if v["rel1_med"] is not None else "n/a")
        sh = f"{v['shift'] * 1000:+.0f} ms" if v["shift"] is not None else "n/a"
        lines.append(
            f"| {p} | {v['rtt_cfg']:.0f} ms | {v['rtt_min']:.1f} / {v['rtt_med']:.1f} / {v['rtt_p95']:.1f} ms "
            f"| {v['exp_mean']:.0f} kbit/s | {v['meas_mean']:.0f} kbit/s "
            f"| {v['rel_p5']:+.1%} / {v['rel_med']:+.1%} / {v['rel_p95']:+.1%} | {one} | {sh} |")
    for p, v in r["paths"].items():
        if v["low_bins"]:
            ms = [w for _, w, _ in v["low_bins"]]
            lines.append(f"\nPath {p}, {len(ms)} bins configured at <= 100 kbit/s: measured "
                         f"median {statistics.median(ms):.0f}, max {max(ms):.0f} kbit/s.")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--csv", type=Path)
    a = ap.parse_args()
    results = [analyse(r) for r in a.runs]
    for r in results:
        print(fmt(r))
    if a.csv:
        with open(a.csv, "w") as f:
            f.write("run,path,t_s,measured_kbit,configured_kbit\n")
            for r in results:
                for p, v in r["paths"].items():
                    for t, w, x in v["series"]:
                        f.write(f"{r['run']},{p},{t:.2f},{w:.1f},{x:.1f}\n")


if __name__ == "__main__":
    main()
