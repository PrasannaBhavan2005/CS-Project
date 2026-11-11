# Frame-aware multipath QUIC (CS6048 ACN, Team 7)

How much of two weak uplinks can an interactive live lecture use over Multipath
QUIC, and does placing whole video frames on paths (instead of single packets)
recover what packet-level schedulers waste?

- Design, hypotheses H1-H5, scenarios, metrics: `docs/proposal.md`
- What exists, what works, what failed, what is next: `docs/PROGRESS.md`
- Working rules for people and coding agents: `CLAUDE.md` (read it first; the
  hypotheses and the measurement definitions in it are fixed)

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
