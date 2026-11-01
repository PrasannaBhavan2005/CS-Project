# Team 7: Frame-Aware Multipath QUIC for Live Lecture Streaming

Repo copy of the proposal (revised 1 Nov 2026 after an internal review). The
shared, editable version is https://claude.ai/artifact/U6rybbTYZj9VDtioWnHGix

We will measure how much of two weak uplinks an interactive live lecture can
actually use over Multipath QUIC, and test whether placing whole video frames on
paths, instead of single packets, recovers the capacity that packet-level
schedulers waste.

Every claim is stated as a hypothesis with a test and a planned response if it
fails, so the project yields a defensible answer whichever way the data goes.
Scope: one testbed, real two-operator traces recorded in Chennai, eight
schedulers plus two reference points, standard video-quality metrics. No ML.

## 1. Why this is needed

| Evidence | What it shows |
| --- | --- |
| Opensignal, Feb 2026 (data Oct-Dec 2025): average upload 8.4 Mbps Airtel, 8.0 Jio, 5.9 Vi, 2.5 BSNL; only 56-69% of tests on the three private operators met its consistent-quality bar | Averages look ample, yet a third or more of tests miss a bar that combines upload with latency, jitter and loss; RQ1 measures the uplink part directly |
| Zoom: 1.2 Mbps up for 720p one-to-one, 2.6 Mbps for 720p group, 3.8 Mbps for 1080p | A teacher's camera feed needs 1.2-3.8 Mbps of uplink, sustained |
| LiveU bonding splits one live video across up to six connections | Industry already treats multi-link uplink as necessary for live video (proprietary) |
| Dual-SIM dual-standby phones: only one SIM carries data at a time | Realistic setups: WiFi + cellular on one device, or two devices (as in COMPACT) |
| MoMQ (2026) schedules frames only on a relay's last hop; names the publisher's first hop over cellular as future work | Sender-side cellular-uplink case is open |

## 2. Research questions and hypotheses (fixed before experiments)

Primary comparisons P1-P6 are declared in advance, Holm-corrected.

| Question | Hypothesis | Test | If it fails |
| --- | --- | --- | --- |
| RQ1 Need | H1: at weak-coverage sites, the better single uplink is below 2.6 Mbps in >= 10% of 1-s windows, and the two links together are below it at most half as often | Simultaneous two-operator traces; no QUIC | Aggregation unnecessary at these sites; focus on outage (resilience) |
| RQ2 Problem | H2: at D = 250 ms, MinRTT and ECF reach < 80% of the usable capacity of the ideal link R1 (combined rate, lower RTT) when path RTTs differ by >= 3x (P1, P2) | Bitrate sweep up to 1.1x combined capacity; R1 on the same emulator | Existing schedulers suffice; stop scheduler work and explain why |
| RQ3 Fix | H3: F2 has less freeze time than the better of MinRTT and ECF on asymmetric and real paths (P3, P4), and is equivalent within 5% on symmetric paths | Paired runs; F1 vs F2 ablation; R2 (F2 with true trace rates) separates estimator error from placement | Publish negative result with its cause |
| RQ4 Placement | H4: with identical placement and rescue logic, one MPQUIC connection (F2) and two separate QUIC connections (A1) are equivalent within 5% usable capacity (P5) | Equivalence test (TOST) | If MPQUIC clearly better, explain mechanism; if equivalent, recommend app-level design |
| RQ5 Bursts | H5: F2's advantage is larger with 2-s keyframes than with intra-refresh (P6) | Same scenarios, both encodings | Burst handling is not the source of the gain |

Decision point end of week 2: H1 and H2 decide whether F1/F2 are built or effort
moves to measurement and outage results.

## 3. System and schedulers

Testbed: sender namespace (pre-encoded lecture -> scheduler under test) -> path A
and path B (tc netem delay + tbf rate, rates replayed from traces recorded at the
same time) -> receiver namespace (logs every frame's completion time and bytes
per path) -> offline playout model.

- Frames as streams: each frame part is one QUIC stream (as Media over QUIC
  carries objects), released at the frame's capture time (25 fps, the source
  clips' native rate; frame interval 40 ms). A split
  frame uses two streams.
- Strict frame order: every scheduler sends streams in frame order
  (non-incremental priority). TQUIC's default (urgency 127, incremental=true)
  round-robins concurrent streams and would delay I-frames.
- Display rule: frame i is on time iff max(completion time over i and every
  frame it depends on) <= capture_i + D. Dependencies: periodic keyframes = all
  frames since last I-frame; intra-refresh = all earlier frames. Late frames are
  decoded as references but not shown.
- One run, every deadline: D swept 100-1000 ms offline.

| ID | Scheduler | Unit | Why |
| --- | --- | --- | --- |
| S0 | Best single path | none | Is multipath needed at all? |
| S1 | MinRTT (TQUIC built-in) | packet | Default in practice |
| S2 | Round-robin (built-in) | packet | Naive split |
| S3 | Redundant (built-in) | packet | Latency floor at 2x data |
| S4 | ECF (we implement) | packet | Strongest transport-only baseline |
| F1 | Frame pinning | frame | Whole frame on path predicted to finish it first |
| F2 | F1 + balanced split + rescue | frame | Split when that finishes sooner; resend stalled part on other path |
| A1 | F2 logic over two separate QUIC connections | frame | RQ4 |
| R1 | Ideal link: one path, combined rate, lower RTT | reference | Best any scheduler could do (RQ2) |
| R2 | F2 with true trace rates | reference | Separates estimator error from placement (RQ3) |

Finish-time estimate for a part of S bytes on path p:

    T_p = (U_p + S)/R_p + (sRTT_p - minRTT_p) + minRTT_p/2

U_p = bytes assigned to p not yet sent; R_p = measured delivery rate
(acknowledged bytes per interval, max over the last second). Do not use TQUIC's
pacing rate: with CUBIC it is cwnd/sRTT, and cwnd keeps growing while video is
application-limited, so it overstates capacity.

F2 split (whenever it gives an earlier predicted finish; independent of D), with
d_p = (sRTT_p - minRTT_p) + minRTT_p/2, clamped to [0, S]:

    S_a = ((U_b + S)/R_b + d_b - U_a/R_a - d_a) / (1/R_a + 1/R_b)

Rescue: if a path makes no progress for one PTO, F2 and A1 resend unfinished
parts on the other path; the receiver completes a frame when every byte range
has arrived from either path. (Stock TQUIC would wait out an outage: loss
detection needs a later ACK, persistent congestion is a stub, PTO re-sends at
most 2 packets with backoff.)

F1/F2 reuse known ideas (ECF completion estimates, DEMS balanced split,
stream-aware MPQUIC mapping). The contribution is the deadline- and
decode-aware measurement on two-operator uplinks, and where the logic belongs.

## 4. Evaluation method

Workload:
- Content: main matrix = camera lecture at a blackboard (60-s NPTEL clip, CC
  BY-SA, NPTEL's licence since Sep 2014; 25 fps). Controls: tablet
  handwriting, slide screen-share, and a second blackboard lecture without a
  camera cut, in one scenario.
- Encoder: main = x264 zerolatency CBR with intra-refresh (no I-frames). Stress
  case = keyframe every 2 s (YouTube's recommended live interval). Both:
  vbv-maxrate = bitrate, vbv-bufsize = 0.5 s of bitrate.
- Bitrate: main runs 2.6 Mbps (Zoom 720p group); sweeps 0.5 Mbps to 1.1x the
  combined capacity.

Scenarios (2.6 Mbps exceeds the better path but is within ~85% of the sum; each
path has a 200 ms buffer, reported):

| Scenario | Path A | Path B | Tests |
| --- | --- | --- | --- |
| control | 4 Mbps, 40 ms RTT | 4 Mbps, 40 ms RTT | over-provisioned: schedulers should not matter |
| symmetric | 1.6 Mbps, 40 ms | 1.6 Mbps, 40 ms | both paths needed, no asymmetry |
| rtt_asym | 1.6 Mbps, 30 ms | 1.6 Mbps, 150 ms | reordering |
| bw_asym | 2.0 Mbps, 40 ms | 1.2 Mbps, 60 ms | uneven split |
| outage | 1.8 Mbps, 40 ms | 1.8 Mbps, 60 ms | each path in turn drops to 0 for 2 s every 15 s |
| real_pairs | operator 1 trace | operator 2 trace, same time/place | 3 sites: indoor campus, outdoor, moving vehicle |

Metrics:
- On-time display ratio vs D (100-1000 ms), display rule above.
- Freeze time: gap between shown frames >= max(3 frame intervals, interval +
  150 ms) (WebRTC freezeCount rule); at 25 fps (40 ms interval) that is
  190 ms.
- Required playout delay: smallest D with >= 99% frames on time.
- Usable capacity: highest swept bitrate with freeze time <= 1% at D = 250 ms,
  as a share of R1's usable capacity. (250 ms leaves 150 ms of G.114's 400 ms
  end-to-end planning limit for capture, encode, display.) Also report 150 and
  400 ms.
- Path cost: bytes per path, duplicate bytes.

Statistics and checks:
- 8 runs per cell; clip start and trace start drawn from a fixed seed and reused
  for every scheduler (paired).
- P1-P6: paired Wilcoxon with Holm correction (8 pairs -> min p 0.008).
  Equivalence claims: TOST, 5% margin. Everything else: 95% bootstrap CIs.
- Emulator calibration before any result (iperf3 100 ms bins vs trace; ping vs
  configured delay).
- Sanity: control scenario all tie; one path removed -> matches S0.
- Stack check: if TQUIC CUBIC cwnd grows while app-limited, apply RFC 9002
  section 7.8 (no growth when not cwnd-limited) for every scheduler; report it.
- Discard and rerun runs with sender/receiver CPU > 80%.
- Budget ~1,240 runs x ~70 s (~25 h machine time, 3-4 overnight batches):
  main matrix 10 configs x 8 scenarios x 8 runs = 640; stress 5 configs (S1, S4,
  F1, F2, R1) x 3 scenarios (rtt_asym, bw_asym, one real site) x 8 = 120; sweeps
  4 configs (S1, S4, F2, R1) x 2 scenarios (rtt_asym, one real site) x 6
  bitrates x 8 = 384; content controls 4 configs (S0, S1, F2, R1) x rtt_asym x
  3 contents (handwriting, slides, second blackboard lecture) x 8 = 96.
- Stretch: BBR runs, 50 ms buffer sensitivity, real-world spot check (laptop
  WiFi + phone hotspot to a cloud server, MinRTT vs F2).

## 5. Objections answered (summary)
One uplink is enough -> RQ1 on own traces, S0 everywhere. One path could carry
the stream -> scenarios sized so it can't, plus control. Lower the bitrate ->
usable capacity vs ideal link. Slides need little -> slides control. Delay
tolerance -> interactive 250 ms budget + full curve. Prior art (MoMQ, Converge,
XLINK, DEMS) -> acknowledged; open question is cellular uplinks at the sender.
Strawman baselines -> ECF, Redundant, R1. Estimator decides -> R2. I-frame
artefact -> intra-refresh main, 2-s GOP stress. DSDS phones -> WiFi+cellular or
two devices. Emulation -> simultaneous traces, calibration, spot check. UDP
blocked -> logged per operator, claim scoped. TQUIC quirks -> same stack, strict
order, own rate estimate, RFC 9002 fix for all. Noise -> paired, declared
primaries, Holm, TOST, hypotheses fixed.

## 6. Tools
TQUIC (Rust) submodule + three hooks (stream-to-path filter; declined-send flag
blocking stream data on the fallback path; RFC 9002 app-limited rule if
needed). picoquic fallback. WSL2 Ubuntu 24.04, namespaces, veth, netem + tbf,
100 ms trace replay. Traces: two phones, two operators, simultaneously; iperf3
UDP offered above capacity to a small cloud VM, 100 ms bins, plus ping; 3 sites
x 10-15 min (~1 GB per phone per site); UDP reachability logged. ffmpeg/x264,
ffprobe. Python: pandas, matplotlib, scipy.

## 7. Papers (2023-2026) and prior art
draft-ietf-quic-multipath-21 (2026); draft-ietf-moq-transport (2026); Tokens,
Not Packets (ANRW 2026); MoMQ (arXiv 2608.10741, 2026); COMPACT (MMSys 2025);
Tile-Level Multipath Content-aware Live Video Streaming (TOMM 2026); Converge
(SIGCOMM 2023); Chorus (MobiCom 2024); STORM (ATC 2025); AUGUR (NSDI 2024);
QCON (NSDI 2026); multiple-description neural codec over 5G (arXiv 2608.22891,
2026); Rethinking Network Metrics (ICC 2026); QUIC-TCP Racing (TNSM 2024).
Baselines and prior art: MPQUIC (CoNEXT 2017), ECF (CoNEXT 2017), BLEST (2016),
XLINK (SIGCOMM 2021), DEMS (MobiCom 2017), stream-aware MPQUIC (EPIQ 2018),
PStream (ICCCN 2020).

## 8. Plan (final demo 17 Nov 2026)

| Week | Dates | Work | Gate |
| --- | --- | --- | --- |
| 1 | Oct 29-Nov 4 | TQUIC, two-path testbed, calibration, trace kit, first site, encode main clip | calibrated two-path testbed |
| 2 | Nov 5-11 | streamer + analysis, the 3 hooks + unit tests, S0-S4 runs, RQ1 from traces (3 sites by Nov 9) | decision: H1 and H2 |
| 3 | Nov 12-14 | F1, F2, A1, R2; full matrix; sweeps; 2-s GOP stress; R1 reference (overnight batches) | every config on every scenario |
| 4 | Nov 15-17 | statistics, plots, report, slides; final demo Nov 17; stretch (BBR, spot check) only if time is left | |
