# Frame-aware multipath QUIC (CS6048 ACN, Team 7)

How much of two weak uplinks can an interactive live lecture use over Multipath
QUIC, and does placing whole video frames on paths (instead of single packets)
recover what packet-level schedulers waste?

- Design, hypotheses H1-H5, scenarios, metrics: `docs/proposal.md`
- What exists, what works, what failed, what is next: `docs/PROGRESS.md`
- Working rules for people and coding agents: `CLAUDE.md` (read it first; the
  hypotheses and the measurement definitions in it are fixed)

## Current status (11 Nov 2026; final demo 17 Nov)

Everything below builds and its tests pass (TQUIC 564 + 1, streamer 6,
analysis 15). Details and evidence: `docs/PROGRESS.md`.

Done
- Week 1: two-path netem testbed (`testbed/`), calibration report
  (`docs/calibration.md`), multipath transfers under MinRTT and round-robin,
  trace-collection guide (`docs/trace_collection.md`), clip encodes.
- Week 2 (part): TQUIC hooks a-c and ECF (S4) on the fork's `team7` branch;
  streamer; `scripts/run.sh` + `scripts/batch.sh`; playout and stats analysis.
- First batch: S0-S4 x 5 synthetic scenarios x 8 runs (200 runs, 2.6 Mbit/s).
  Summary table in `docs/PROGRESS.md` (2 Nov entry). Round-robin (S2) beats
  MinRTT (S1) by 3.5-14 pp of frames on time at D = 250 ms; ECF collapses
  under outages. Exploratory only: H1/H2 are not decided yet.

To do, in plan order (pick an item, say so in the team chat, work on a branch)
1. R1 ideal-link reference in the testbed (one path, rate = sum, RTT = lower).
   Needed for usable capacity, so H1/H2 depend on it.
2. Bitrate sweeps (S1, S4, R1, plus S2 for context) on rtt_asym; then report
   H1/H2 before building F1/F2 (week 2 decision point).
3. F1 and F2 in the streamer (finish-time estimate, split, rescue; formulas in
   `CLAUDE.md`), with unit tests for the estimator, split and reassembly.
4. A1 (F2 over two single-path connections) and R2 (F2 with true trace rates).
5. Real two-operator traces from 3 sites (`docs/trace_collection.md`); only a
   public calibration fixture is in `traces/` so far.
6. Full matrix, stress and content-control batches (~1,040 runs left, run
   overnight); then statistics, plots, report and slides.

Open questions: why ECF collapses under outage, and why round-robin beats
MinRTT (see the 2 Nov entry in `docs/PROGRESS.md`).

## Get the code

```bash
git clone --recurse-submodules https://github.com/knb2345/acn-mpquic.git
cd acn-mpquic
```

`third_party/tquic` is our TQUIC fork (https://github.com/knb2345/tquic, branch
`team7`: hooks a-c, ECF scheduler, stall fix, frame_path log, on top of
v1.6.0). If you already cloned without submodules: `git submodule update --init`.

## Requirements

Linux (we use WSL2 Ubuntu 24.04; keep the repo on the Linux filesystem, not
`/mnt/c`), with:

- Rust (cargo) and a C toolchain (for TQUIC's BoringSSL build: `cmake`,
  `clang` or `gcc`, `golang` may also be needed)
- `iproute2` with `tc`, kernel modules `sch_netem sch_tbf sch_htb`
- ffmpeg/ffprobe with libx264, iperf3
- Python 3.12 venv: `python3 -m venv analysis/.venv &&
  analysis/.venv/bin/pip install pandas matplotlib scipy`
- passwordless sudo for `ip`, `tc`, `modprobe` only (see `testbed/README.md`)

## Build and test

```bash
(cd third_party/tquic && cargo build --release --all && cargo test --release)
(cd streamer && cargo build --release && cargo test --release)
(cd analysis && .venv/bin/python -m unittest test_playout test_stats)
```

## Run

```bash
workload/download.sh stochastic             # videos are not in git (needs yt-dlp)
workload/encode.sh stochastic intra          # frame traces (.csv) are in git
testbed/up.sh rtt_asym                       # two emulated paths
scripts/run.sh rtt_asym S1 2600 intra stochastic 0
```

One run writes `results/<scenario>/<config>/<bitrate>_<encoding>_<clip>/<run_id>/`.
Batches: `scripts/batch.sh`. Raw qlogs and dumps are git-ignored; per-run
`frames.csv`, `paths.csv`, `meta.json` and summaries are tracked. Never edit or
delete results by hand; log failed runs in `docs/PROGRESS.md`.

## Contributing

Work on a branch, small commits, open a PR against `main`. TQUIC changes go to
the `team7` branch of the fork, only in `src/multipath_scheduler/` plus hooks
a-c, each with a unit test; then bump the submodule pointer here.
