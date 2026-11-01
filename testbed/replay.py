"""Change path rates over time for the outage and real_pairs scenarios.

  replay.py <log.csv> [--offset-ms N] [--duration-s S]

Run after testbed/up.sh outage|real_pairs. Every 100 ms, sets the htb class rate of
each scheduled veth end through one long-running `tc -batch` per namespace (one
sudo per namespace, not per change). Logs the starting rate of every device and
then every change to log.csv (mono_us, t_ms, dev, kbit; mono_us is
CLOCK_MONOTONIC), so the log alone gives each path's capacity at any time.
Runs until --duration-s or SIGTERM.

outage:     every 15 s one path drops to MIN_KBIT for 2 s in both directions,
            in turn: A at 15 s, B at 30 s, A at 45 s, ... (t counted from
            --offset-ms).
real_pairs: the data direction (client ends cA, cB) follows the site's traces
            from --offset-ms, looping; the reverse direction (ACKs) keeps the
            trace mean set by up.sh. Buffers stay at QUEUE_MS of the mean rate
            (a fixed number of bytes, like a real device buffer).
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trace_site  # noqa: E402

TICK_MS = 100
# A rate of 0 is not possible; at 8 kbit a full-size packet waits 1.5 s, so almost
# nothing gets through and arriving packets queue or drop, as in a coverage hole.
MIN_KBIT = 8
DEVS = {"cA": "mpq-cli", "cB": "mpq-cli", "sA": "mpq-srv", "sB": "mpq-srv"}
OUTAGE_EVERY_MS = 15000
OUTAGE_LEN_MS = 2000


def outage_down(path, t_ms):
    """True while `path` ("A"/"B") is in an outage at time t_ms."""
    n, into = divmod(t_ms, OUTAGE_EVERY_MS)
    return n >= 1 and into < OUTAGE_LEN_MS and path == ("A" if n % 2 else "B")


def schedules(state):
    """dev -> function(t_ms) -> kbit/s"""
    base = {"A": int(state["A_RATE_KBIT"]), "B": int(state["B_RATE_KBIT"])}
    if state["SCENARIO"] == "outage":
        return {dev: (lambda t, p=dev[1]: MIN_KBIT if outage_down(p, t) else base[p])
                for dev in DEVS}
    if state["SCENARIO"] == "real_pairs":
        _, paths = trace_site.load(state["SITE"])
        return {f"c{p}": (lambda t, k=v["kbit"]: k[(t // TICK_MS) % len(k)])
                for p, v in paths.items()}
    sys.exit(f"replay.py: scenario {state['SCENARIO']} has no rate schedule")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--offset-ms", type=int, default=0)
    ap.add_argument("--duration-s", type=float, default=float("inf"))
    a = ap.parse_args()

    state_file = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "mpq-testbed.env"
    state = dict(l.split("=", 1) if "=" in l else (l, "")
                 for l in state_file.read_text().splitlines())
    base = {"A": int(state["A_RATE_KBIT"]), "B": int(state["B_RATE_KBIT"])}

    sched = schedules(state)
    tc = {ns: subprocess.Popen(["sudo", "/usr/sbin/tc", "-n", ns, "-batch", "-"],
                               stdin=subprocess.PIPE, text=True)
          for ns in sorted({DEVS[d] for d in sched})}
    stop = False

    def on_term(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)

    t0 = time.monotonic()
    last = {dev: base[dev[1]] for dev in DEVS}  # as set by up.sh
    with open(a.log, "w") as log:
        log.write("mono_us,t_ms,dev,kbit\n")
        for dev, kbit in last.items():
            log.write(f"{round(t0 * 1e6)},0,{dev},{kbit}\n")
        k = 0
        while not stop and k * TICK_MS < a.duration_s * 1000:
            for dev, f in sched.items():
                kbit = max(f(a.offset_ms + k * TICK_MS), MIN_KBIT)
                if last[dev] == kbit:
                    continue
                # Same burst rule as up.sh. The bfifo under the class keeps
                # its limit (QUEUE_MS of the base rate). Changing an htb class
                # keeps its tokens (tbf would refill them on every change).
                burst = max(kbit * 1000 // 8 // 250, 3028)
                tc[DEVS[dev]].stdin.write(
                    f"class change dev {dev} parent 10: classid 10:1 htb rate {kbit}kbit "
                    f"ceil {kbit}kbit burst {burst} cburst {burst} quantum 1514\n")
                last[dev] = kbit
                now = time.monotonic()
                log.write(f"{round(now * 1e6)},{round((now - t0) * 1000)},{dev},{kbit}\n")
            for p in tc.values():
                p.stdin.flush()
            k += 1
            time.sleep(max(0.0, t0 + k * TICK_MS / 1000 - time.monotonic()))
    for p in tc.values():
        p.stdin.close()
        p.wait()


if __name__ == "__main__":
    main()
