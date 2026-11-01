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
