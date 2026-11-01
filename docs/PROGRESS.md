# Progress log

Running log of what exists, what works, what failed and what is next. Newest
entry last. Design and hypotheses: `docs/proposal.md` (revised 1 Nov 2026).

## 2026-11-01: audit after the 1 Nov redesign

Context: the previous Claude Code session was lost. `CLAUDE.md` and
`docs/proposal.md` were replaced with the 1 Nov versions from the user's
Downloads folder (the previous working-tree copies are not in git; the
committed versions are in 5fc8f5a). Everything below was checked today, not
copied from the old `CLAUDE.md`.

### Git state
- One commit on branch `week1` (5fc8f5a, 28 Oct): TQUIC submodule at stock
  v1.6.0 (d87a9a0), testbed scripts, Week 1 transfer runs.
- Not committed (left as is, nothing deleted): work from the old design
  (28-31 Oct, deadline scheduler and ML predictor):
  - 787 staged renames `results/<scenario>/...` ->
    `results/week1_transfer/<scenario>/...`, plus edits to `testbed/up.sh`,
    `testbed/run_transfer.sh`, `testbed/README.md`, `.gitignore`;
  - untracked: `streamer/` (mpq_sender/mpq_receiver, ~690 lines),
    `analysis/{frames,compare,plots,report_numbers}.py`, `analysis/ml/`,
    `testbed/{replay,replay_spec,train_spec}.py`, `testbed/run_stream.sh`,
    `docs/report/`, `docs/slides/`, three status PDFs, 1.1 GB in `results/`
    (old-design matrices, ML training data);
  - TQUIC submodule checked out at branch `team7` (10b826e), 9 commits above
    v1.6.0: frame_path log hook, ECF, deadline/framepin/learned schedulers,
    ML model, and a fix for a `select_send_path` stall when a path being
    validated has a full cwnd (5a82889). The parent repo still records d87a9a0.
- None of the old results answer the new hypotheses (different scenarios,
  workload, encodings, metrics); they are not evidence for H1-H5.

### Environment (checked 1 Nov)
| Item | State |
| --- | --- |
| Kernel | 6.18.54.1-microsoft-standard-WSL2, Ubuntu 24.04.4 |
| sch_netem, sch_tbf, sch_htb | modules (`=m`); load with `modprobe -a ...`. Plain `modprobe sch_netem sch_tbf sch_htb` loads only netem (the rest are taken as module parameters); `testbed/up.sh` already uses `-a` |
| sudo | passwordless for `/usr/bin/ip`, `/usr/sbin/tc`, `/usr/sbin/modprobe` (works); `sudo -n true` needs a password (not needed) |
| Rust | cargo/rustc 1.99.1 |
| ffmpeg/ffprobe | 6.1.1 (libx264) |
| iperf3 | 3.16 |
| Python | 3.12.3; venv created at `analysis/.venv` with pandas 3.0.1, matplotlib 3.10.8, scipy 1.17.1 |

### Week 1 checklist (CLAUDE.md "Plan and gates")
| Item | Status | Evidence / gap |
| --- | --- | --- |
| TQUIC builds, tests pass | done for `team7` (10b826e) | `cargo build --release --all` ok; `cargo test --release`: 566 + 1 passed, 0 failed (1 Nov). Stock v1.6.0 passed 552/552 on 28 Oct (commit 5fc8f5a message) |
| `testbed/up.sh` / `down.sh` | works, old presets | up, rerun and down all clean; ping 40.1 ms min on both paths for a 40 ms preset. Presets are the old ones (4 Mbit/s, 100 ms queue); new scenarios (control, symmetric 1.6+1.6, rtt_asym 1.6+1.6 @30/150, bw_asym, outage) and the 200 ms buffer are missing |
| Calibration report | missing | `testbed/check.sh` reports mean rate (5 s TCP iperf3) and mean ping only; no 100 ms bins vs trace, no report |
| Multipath transfer, both paths, MinRTT and round-robin | done under old presets | `results/week1_transfer/`: symmetric and rtt_asym (4 Mbit/s paths), both paths 48-52% of bytes, 1 of 62 transfers stalled (rtt_asym/roundrobin). Not repeated on the new scenarios |
| `docs/trace_collection.md` | missing | `traces/collect/README.md` + `iperf3_to_csv.py` exist (old, downlink `-R`, 5 min, no ping, no VM setup) |
| Encode main clip, both modes | missing | No NPTEL clip chosen or downloaded; `workload/make_frame_trace.sh` does CRF + 2 s GOP only (no CBR, no intra-refresh) |
| First trace site | not started | needs phones and a cloud VM (teammates) |

### Next
Week 1 plan to be agreed with the user (see chat on 1 Nov).

## 2026-11-01: Gate A (TQUIC builds, tests pass): passed

Done
- Old-design work archived, nothing deleted:
  - code and docs: branch `archive/old-design` (6da75fb) in this repo;
  - results (1.1 GB), old binaries, old encodes and the old streamer build:
    moved to `~/acn-archive/` (outside the repo). `results/` in the repo is
    empty; the 28 Oct transfer runs remain in git history (5fc8f5a).
  - TQUIC: old branch renamed `team7-old` (10b826e).
- New TQUIC branch `team7`, base **d87a9a0** (tag v1.6.0, "Merge pull request
  #438 from Tencent/release/v1.6.0"), two commits:
  - 108bc38 stall fix in `select_send_path` + unit test;
  - c51c237 `tquic::frame_path` debug log of every sent STREAM frame with its
    path id (logging only; off unless that log target is enabled).
- CLAUDE.md: `modprobe -a` (approved by the user).

Evidence
- `cargo build --release --all`: ok. `cargo test --release` and `cargo test`
  (debug): 552 + 1 passed, 0 failed.
- New test `conn_multipath_probing_path_cwnd_full` on stock v1.6.0 code:
  **fails** (`assertion failed: !packets.is_empty()`: the client sends no
  packet at all); with the fix: passes.

The stall fix, and how it relates to hook b
- Bug (v1.6.0, connection.rs `select_send_path`, first block): once the
  connection is established, any path that needs PATH_CHALLENGE/RESPONSE is
  returned first, without checking its congestion window. `send_packet` checks
  the window before it writes validation frames, so if that path's window is
  full the packet is empty and `send()` returns Done. The next `send()` picks
  the same path again, so nothing (stream data, ACKs) leaves on any path until
  that path's window opens, which needs ACKs that are not being sent. Seen in
  the old design on trace replay with path B near 8 kbit/s during validation.
- Fix: such a path is skipped while `recovery.can_send()` is false; selection
  falls through to the normal multipath branch (scheduler, then ACK/PTO path,
  then active path). Validation frames go out as soon as the window opens (the
  test checks this too).
- Effect on schedulers: identical for all of them; it only matters during path
  validation, before the second path becomes active, so it cannot favour any
  scheduler. Without it, a transfer could stall for reasons unrelated to the
  scheduler under test.
- Hook b (declined-send flag, not built yet) acts in a different place: after
  `on_select` declines, the fallback to the ACK/PTO path or the active path must
  not carry stream data. The fix changes only the probing block that runs
  before `on_select`. The two cannot conflict: when the fix skips a probing
  path, control reaches `on_select`, and if that declines, hook b applies as
  designed. Hook b blocks stream data only, so PATH_CHALLENGE/RESPONSE on a
  fallback path stays allowed. Hook b's unit tests (week 2) will rerun
  `conn_multipath_probing_path_cwnd_full`.

Next: Gate B (scenario presets, 200 ms buffer, outage and trace replay).

## 2026-11-01: Gate B (scenario presets, replay): passed

Done
- `testbed/up.sh`: scenarios control, symmetric, rtt_asym, bw_asym, outage,
  real_pairs (proposal section 4), buffer 200 ms of each path's rate.
- `testbed/replay.py` (adapted from the archived one): outage schedule and
  trace replay; logs each device's starting rate and every change.
- `testbed/trace_site.py` + site format `traces/<site>/site.json` and csv
  `t_ms,mbps,capped,loaded_rtt_ms` (CLAUDE.md's layout line says `t_ms, mbps,
  rtt_ms`; the RTT is now split into unloaded (site.json, used as the replay
  delay) and loaded (csv, reference only), as the user specified on 1 Nov).
- `traces/public_mahimahi/`: two public Mahimahi uplink traces (AT&T LTE,
  T-Mobile UMTS) as a calibration fixture only; their RTTs (40/60 ms) are
  configured, not measured. Not evidence for any hypothesis.

Evidence
- Every scenario comes up; `tc` shows the configured netem delay (RTT/2) and
  tbf rate on each veth end. State file records scenario, site, rates, RTTs.
- Outage schedule computed over 64 s: drops start at 15 s (A), 30 s (B),
  45 s (A), 60 s (B), each lasting 2.0 s. A 3 s replay from offset 14.5 s set
  cA and sA to 8 kbit at t = 500 ms and back to 1800 kbit at t = 2500 ms.
- real_pairs replay from offset 60 s applied the trace bin by bin (cA:
  1560, 1200, ... kbit, matching rows 601-621 of the trace); cB went to
  8 kbit (a zero bin, clamped to the tbf minimum).

Interpretation choices (not hypotheses; flagged to the user)
- Outage "each path in turn at 0 for 2 s every 15 s": implemented as one
  outage every 15 s, alternating A, B, A, ... (each path once per 30 s), both
  directions, "0" = 8 kbit/s (tbf minimum; about one 1500-byte packet per
  1.5 s).
- real_pairs: traces shape the data direction (client -> server); the reverse
  direction (ACKs) stays at the trace mean; buffer bytes fixed at 200 ms of the
  trace mean.

Next: Gate C (calibration report).
