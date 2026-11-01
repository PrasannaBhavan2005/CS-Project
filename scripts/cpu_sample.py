"""Sample the CPU use of the streamer processes (for the 80% rule).

  cpu_sample.py <out.csv> <process name> ...

Every 0.5 s, for each running process whose name (/proc/<pid>/comm) is one of
the given names: CPU time used since the last sample as a percentage of one
core. Network namespaces do not isolate PIDs, so this runs in the root
namespace. Stops on SIGTERM. Output: ts_us,name,pid,cpu_pct (ts_us is
CLOCK_MONOTONIC).
"""

import os
import signal
import sys
import time

INTERVAL = 0.5
TICK = os.sysconf("SC_CLK_TCK")


def cpu_ticks(pid):
    with open(f"/proc/{pid}/stat") as f:
        fields = f.read().rsplit(")", 1)[1].split()
    return int(fields[11]) + int(fields[12])  # utime + stime


def find(names):
    out = {}
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/comm") as f:
                name = f.read().strip()
        except OSError:
            continue
        if name in names:
            out[int(pid)] = name
    return out


def main():
    path, names = sys.argv[1], set(sys.argv[2:])
    stop = False

    def on_term(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    last = {}
    with open(path, "w") as out:
        out.write("ts_us,name,pid,cpu_pct\n")
        while not stop:
            now = time.monotonic()
            for pid, name in find(names).items():
                try:
                    t = cpu_ticks(pid)
                except OSError:
                    continue
                if pid in last:
                    t0, n0 = last[pid]
                    pct = 100 * (t - n0) / TICK / (now - t0)
                    out.write(f"{round(now * 1e6)},{name},{pid},{pct:.1f}\n")
                last[pid] = (now, t)
            out.flush()
            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
