# Team 7: Frame-Aware Multipath QUIC for Live Lecture Streaming

Working copy of the proposal for the codebase. The shared, editable version is
at https://claude.ai/artifact/U6rybbTYZj9VDtioWnHGix (as of 28 Oct 2026).

## 1. Problem

Transport-only multipath schedulers (MinRTT, round-robin) see only bytes. When
two paths differ in RTT and bandwidth, they split one video frame across both,
so the frame completes only when its slowest packet arrives, and large I-frames
delay every P-frame queued behind them. Recent frame-aware work (MoMQ, 2026)
targets Starlink + WiFi; two low-bandwidth cellular paths of similar cost, the
common case for online classes in India, are unstudied.

We measure how often transport-only schedulers cause playback-deadline misses
in this setting, then design and evaluate a deadline-aware frame scheduler.

## 2. Approach

Setting: a sender streams a pre-encoded lecture (fixed GOP: one I-frame, then
P-frames) frame by frame over one multipath QUIC connection with two paths.
Each frame travels on its own QUIC stream. The receiver plays frames on a fixed
schedule; a frame completing after its slot is a deadline miss.

Scheduler, per frame:
1. Estimate the frame's finish time on each path p:
   `T_p = (Q_p + S_frame) / B_p + sRTT_p / 2`, where Q_p = bytes queued or in
   flight on p, S_frame = frame size, B_p = estimated delivery rate.
2. If at least one path meets the deadline, send the whole frame on the path
   that finishes earliest.
3. If no single path meets it (usually a large I-frame), split it so both parts
   finish at the same time.
4. While an I-frame occupies one path for several RTTs, let following P-frames
   use the other path instead of queueing behind it.

Baselines: single-path QUIC on the better path; TQUIC's built-in MinRTT,
round-robin and redundant; ECF (we implement it); a frame-pinning variant
without the deadline check (ablation).

Research extension: replace B_p and sRTT_p estimates with a small model trained
on cellular traces that predicts each path's next-second throughput.

## 3. Tools

- Multipath QUIC: TQUIC (Rust). Fallback: picoquic (C).
- Emulation: network namespaces, veth pairs, tc netem and tbf; a script updates
  each path's rate every 100 ms from a cellular trace.
- Traces: our own dual-SIM traces from Chennai (two phones, two carriers,
  iperf3 to a server); public 4G/5G traces as backup.
- Workload: ffmpeg (x264) and ffprobe for per-frame sizes and timestamps;
  playback is simulated from frame timing, no player.
- Measurement: qlog/qvis, per-frame CSV logs, Python (pandas, matplotlib).

## 4. Evaluation

Scenarios:

| Scenario | Path A | Path B | Tests |
| --- | --- | --- | --- |
| symmetric | 4 Mbps, 40 ms RTT | 4 Mbps, 40 ms RTT | sanity; schedulers should tie |
| rtt_asym | 4 Mbps, 30 ms | 4 Mbps, 150 ms | reordering, frame splitting |
| low_bw | 1.5 Mbps, 60 ms | 1 Mbps, 120 ms | lecture needs both paths |
| trace | carrier 1 trace | carrier 2 trace | real variability |
| outage | stable | 0 Mbps for 2 s every 30 s | recovery after coverage hole |

Metrics: frame completion time (median, P95, P99); deadline-miss rate (%);
stall count and total stall time; end-to-end lag (ms); peak receiver reorder
buffer (KB); share of bytes per path (%).

## 5. Plan (assumes final demo week of Nov 23)

| Week | Dates | Work | Gate |
| --- | --- | --- | --- |
| 1 | Oct 29 to Nov 4 | Build TQUIC; two paths over namespaces + tc; start trace collection | two paths carry traffic over emulated links |
| 2 | Nov 5 to Nov 11 | Frame sender/receiver; run MinRTT, RR, redundant; add ECF | baseline deadline misses measured |
| 3 | Nov 12 to Nov 18 | Deadline-aware scheduler + ablation; trace replay | all schedulers run end to end |
| 4 | Nov 19 to Nov 25 | 5 scenarios x 6 schedulers, plots, report, slides | |

If two-path transfer is not working by Nov 4, switch to picoquic before writing
scheduler code.

## 6. Key papers (2024-2026)

- MoMQ: Media-over-Multipath-QUIC for Realtime Video Applications (arXiv 2608.10741, 2026) - closest work, uses TQUIC
- COMPACT (MMSys 2025) and Tile-Level Multipath Content-aware Live Video Streaming (TOMM 2026) - Prof. Maity's group
- Chorus (MobiCom 2024), STORM (USENIX ATC 2025), AUGUR (NSDI 2024)
- MARS (TOMM 2024), QC-MAB (TMC 2024), FQ-SAT (ComCom 2024), MERL learned BLP scheduler (ICC-W 2025)
- QCON (NSDI 2026), NeuralMDC multi-carrier 5G video (arXiv 2608.22891, 2026)
- draft-ietf-quic-multipath-21 (IESG-approved March 2026; RFC Editor final review)
