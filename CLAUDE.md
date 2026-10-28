# Team 7 ACN project: frame-aware multipath QUIC

## Goal
Stream a pre-encoded lecture video frame by frame over multipath QUIC with two
emulated cellular paths. Measure how often transport-only schedulers make frames
miss their playback deadline, then build a deadline-aware frame scheduler that
does better. Full proposal: `docs/proposal.md` (scheduler design, scenarios,
metrics, weekly plan).

## Environment
- WSL2 (Ubuntu 24.04) on a Windows laptop. The repo lives at `~/acn-mpquic` on
  the Linux filesystem; never work under `/mnt/c` (slow, breaks permissions).
- netem is a kernel module in WSL2 (kernel 6.6+): `sch_netem`, `sch_tbf` and
  `sch_htb` must be loaded after every WSL restart; `testbed/up.sh` does this.
- Root is needed only for `ip`, `tc` and `modprobe`. If a sudo command asks for
  a password, stop and give the user the exact command to run; never try to
  change sudoers yourself.
- `/etc/sudoers.d/acn-mpquic` allows passwordless `/usr/bin/ip`, `/usr/sbin/tc`
  and `/usr/sbin/modprobe`. Call ip as `sudo /usr/bin/ip`: plain `sudo ip`
  resolves to the `/usr/sbin/ip` symlink, which the rule does not match.
- WSL may restart and wipe namespaces; `testbed/up.sh` must be safe to rerun.

## Stack
- QUIC: TQUIC (Rust), https://github.com/Tencent/tquic, vendored as a git submodule
  under `third_party/tquic`, pinned to tag v1.6.0 (`d87a9a0`); our commits go
  on its local branch `team7` (pushing needs a fork). Default congestion
  control is BBR. Fallback if multipath is broken: picoquic (C).
- Emulation: Linux network namespaces + veth pairs + `tc netem`/`tbf` (see
  Environment for loading the modules in WSL2).
- Workload: ffmpeg/ffprobe to get per-frame sizes and timestamps.
- Analysis: Python (pandas, matplotlib).

## Where the scheduler plugs into TQUIC
- `src/multipath_scheduler/multipath_scheduler.rs` defines
  `trait MultipathScheduler { on_select(paths, spaces, streams) -> Result<usize>;
  on_sent(...); on_path_updated(...) }`.
- Existing schedulers: `scheduler_minrtt.rs`, `scheduler_rr.rs`,
  `scheduler_redundant.rs` (about 100 lines each). `on_select` returns the path
  index for the next packet; `path.recovery.rtt.smoothed_rtt()` and
  `path.recovery.can_send()` are what MinRTT uses.
- To add a scheduler: new file, new variant in `enum MultipathAlgorithm`, its
  name in `FromStr`, a match arm in `build_multipath_scheduler`, and
  `buffer_required`.
- `tools/src/bin/tquic_client.rs` opens one path per local address. Flags:
  client `-c <addr:port> --local-addresses <a>,<b> --enable-multipath
  --multipath-algor minrtt|roundrobin|redundant`; server `-l <addr:port>
  --enable-multipath --multipath-algor ... --cert --key --root <dir>`. Each end
  schedules its own packets, so for a download the server's algorithm decides
  the data split.
- Per-path accounting: TQUIC's qlog events carry no path id. Use the veth
  counters (as `testbed/run_transfer.sh` does), the per-path `PathStats` in
  `src/lib.rs` (not printed by the tools), or trace logs, where the connection
  id ends in `-<path id>`.

## Repo layout (proposed)
```
third_party/tquic/        # submodule, our scheduler commits on a branch
streamer/                 # Rust sender/receiver: one QUIC stream per frame
testbed/                  # namespace + tc scripts, trace replay
traces/                   # cellular traces (csv: t_ms, mbps)
workload/                 # frame trace of the lecture (csv)
analysis/                 # notebooks and plot scripts
results/                  # raw per-run logs, never edited by hand
```

## Per-frame log (receiver, one CSV row per frame)
`frame_id, frame_type, size_bytes, send_ts_us, complete_ts_us, deadline_us,
bytes_path0, bytes_path1, scheduler, scenario, run_id`

## Week 1 (Oct 29 to Nov 4): done when all three pass (all passed 28 Oct)
1. TQUIC builds; its own test suite passes.
2. `testbed/up.sh` creates client and server namespaces joined by two veth pairs,
   each with its own netem delay and rate; `testbed/down.sh` removes them.
3. A file transfer with multipath enabled uses both paths (per-path bytes from
   the veth counters) under MinRTT and round-robin.

Commands and results: `testbed/README.md`. Known issue: 1 of 26 round-robin
runs on rtt_asym stalled (sender almost idle after early losses, likely BBR);
not reproduced since. Experiment scripts must flag stalled runs, not average
them in.

## Rules
- Change TQUIC only inside `src/multipath_scheduler/` plus minimal hooks; keep
  each change small and commented.
- Every experiment runs from one script with the scenario name as argument and
  writes to `results/<scenario>/<scheduler>/<run_id>/`.
- Fixed random seeds; at least 5 runs per scheduler and scenario.
