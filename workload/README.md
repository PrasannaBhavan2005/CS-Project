# Workload

Pre-encoded lecture clips, sent frame by frame by the streamer. Videos stay
out of git; scripts download and encode them reproducibly.

## Clips (`clips.csv`)

All from NPTEL on YouTube; each video's page shows "Creative Commons
Attribution license (reuse allowed)" (checked 1 Nov 2026 via yt-dlp's
`license` field). NPTEL's own policy is CC BY-SA since September 2014
(earlier CC BY-NC-SA; Creative Commons wiki, "OER Case Studies", citing
NPTEL's license note). We cite them as CC BY-SA.

| clip | role | content |
| --- | --- | --- |
| `stochastic` | **main clip** | camera at a blackboard, Prof. V. Balakrishnan, IIT Madras; one camera cut in the window |
| `linalg` | control | camera at a blackboard, Dr. K.C. Sivakumar, IIT Madras; no camera cut (shows results do not hinge on the cut) |
| `handwriting` | control | tablet handwriting over slides, Dr. John Jose, IIT Guwahati |
| `slides` | control | slide screen-share, Prof. M.K. Bhuyan, IIT Guwahati |
| `probability` | not used | camera at a blackboard, Dr. Krishna Jagannathan, IIT Madras (candidate, not chosen) |

Chosen by the team on 1 Nov 2026 from three candidates, **before any
scheduler run**. Every window (`start_s` in `clips.csv`) was fixed by the
median-size rule of `pick_start.sh` before any scheduler had been run on it,
so the windows were not selected for how schedulers perform on them.

## Attribution (for the report and slides)

Video clips from NPTEL (National Programme on Technology Enhanced Learning,
https://nptel.ac.in), licensed CC BY-SA. Clips are 60 s excerpts, re-encoded.

| clip | lecturer | course, lecture | institute | URL | excerpt |
| --- | --- | --- | --- | --- | --- |
| stochastic | Prof. V. Balakrishnan | Physical Applications of Stochastic Processes, Mod-01 Lec-01 "Discrete probability distributions (Part 1)" | IIT Madras | https://www.youtube.com/watch?v=6x1pL9Yov1k | 22:00-23:00 |
| linalg | Dr. K.C. Sivakumar | Linear Algebra, Mod-01 Lec-01 "Introduction to the Course Contents" | IIT Madras | https://www.youtube.com/watch?v=LJ-LoJhbBA4 | 12:00-13:00 |
| handwriting | Dr. John Jose | Multi-Core Computer Architecture, Lec 32 "Introduction to DRAM System" | IIT Guwahati | https://www.youtube.com/watch?v=b9isuUc0CqE | 8:20-9:20 |
| slides | Prof. M.K. Bhuyan | Machine Learning and Deep Learning - Fundamentals and Applications, Lec 1 "Introduction to Machine Learning" | IIT Guwahati | https://www.youtube.com/watch?v=TIFFfLejkcA | 50:50-51:50 |

Short form for slides: "Lecture video: Prof. V. Balakrishnan, IIT Madras,
NPTEL (CC BY-SA), youtube.com/watch?v=6x1pL9Yov1k".

## Scripts

```bash
workload/pick_start.sh <youtube_id>
```

suggests a representative 60 s window: the one whose x264 CRF 23 size is
closest to the median of all windows (10 s steps, 5 minutes clear of both
ends). Its result goes into `start_s` in `clips.csv`.

```bash
workload/download.sh stochastic
```

downloads the whole source (H.264, up to 1080p) to `workload/src/` with an
info file (format, sha256, yt-dlp version).

```bash
workload/encode.sh stochastic intra
```

```bash
workload/encode.sh stochastic gop2
```

encode the clip window (main = `intra`, stress = `gop2`; optional third
argument: bitrate in kbit/s, default 2600) and write
`workload/<clip>_<mode>_<kbps>.csv` (`frame_id,frame_type,size_bytes,pts_ms`)
plus `.cmd.txt` with the exact ffmpeg command, versions and x264's option
string. Encoding settings are documented at the top of `encode.sh`.
`frame_stats.py` summarises traces.

## Encodings (1 Nov 2026, 2600 kbit/s, 1280x720, 25 fps, 60 s = 1500 frames)

Windows: `start_s` in `clips.csv`, chosen by `pick_start.sh` (slides: the same
rule restricted to 2700-3540 s, the lecture's slides-only stretch; the
whole-lecture pick, 2440 s, was tablet writing).

| clip | start | mode | mean kbit/s | I-frames (median / max KB) | P median / p95 / max KB | largest / mean frame | max 1 s window |
| --- | --- | --- | --- | --- | --- | --- | --- |
| stochastic | 1320 s | intra | 2579 | 1 (frame 0: 23.3) | 12.6 / 16.1 / 84.6 | 6.6x | 3454 kbit/s |
| | | gop2 | 2597 | 30 (50.9 / 73.8) | 12.0 / 15.9 / 60.4 | 5.7x | 3450 kbit/s |
| linalg | 720 s | intra | 2564 | 1 (23.2) | 12.6 / 16.0 / 31.5 | 2.5x | 3154 kbit/s |
| | | gop2 | 2578 | 30 (47.2 / 78.9) | 11.9 / 15.6 / 34.6 | 6.1x | 3301 kbit/s |
| probability | 1420 s | intra | 2548 | 1 (27.3) | 12.1 / 17.0 / 53.6 | 4.2x | 3360 kbit/s |
| | | gop2 | 2568 | 30 (56.1 / 77.4) | 11.4 / 16.6 / 56.3 | 6.0x | 3419 kbit/s |
| handwriting | 500 s | intra | 1174 | 1 (21.2) | 3.5 / 12.6 / 71.8 | 12.2x | 3452 kbit/s |
| | | gop2 | 764 | 30 (58.7 / 65.9) | 0.9 / 13.2 / 73.2 | 19.2x | 3466 kbit/s |
| slides | 3050 s | intra | 1127 | 1 (22.3) | 5.4 / 10.4 / 61.9 | 11.0x | 2534 kbit/s |
| | | gop2 | 684 | 30 (60.5 / 70.8) | 0.8 / 12.2 / 69.3 | 20.7x | 2799 kbit/s |

Notes:
- Intra refresh removes periodic I-frames but not every large frame: a camera
  cut or a slide change is coded as a large P-frame (up to 84.6 KB in
  stochastic, larger than any of its gop2 I-frames).
- The controls cannot use 2.6 Mbit/s: without filler, static slides and
  handwriting need 0.7-1.2 Mbit/s on average, with rare large frames.
