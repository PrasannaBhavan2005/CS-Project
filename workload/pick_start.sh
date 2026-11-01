#!/usr/bin/env bash
# Suggest a representative 60 s window of a lecture: the window whose encoding
# complexity (bytes at x264 CRF 23, 640x360) is closest to the median over all
# windows that start on a 10 s step and keep 5 minutes clear of both ends
# (skips intros and outros). Not the hardest minute, a typical one.
#
# Usage: workload/pick_start.sh <youtube_id> [window_s, default 60]
# Needs yt-dlp (~/.venvs/tools/bin/yt-dlp or on PATH). Works in
# workload/src/scan/ (git-ignored); prints the suggested start in seconds and
# the window's complexity relative to the median and the range.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
id=${1:?usage: pick_start.sh <youtube_id> [window_s]}
win=${2:-60}
ytdlp=$(command -v yt-dlp || echo "$HOME/.venvs/tools/bin/yt-dlp")
dir=$here/src/scan; mkdir -p "$dir"

[[ -f $dir/$id.mp4 ]] || "$ytdlp" -q -f "bv*[height<=360][vcodec^=avc1]" -o "$dir/$id.mp4" "https://www.youtube.com/watch?v=$id"
[[ -f $dir/$id.crf23.csv ]] || {
    ffmpeg -hide_banner -loglevel error -y -i "$dir/$id.mp4" -an -s 640x360 \
        -c:v libx264 -preset veryfast -crf 23 -f mp4 "$dir/$id.crf23.mp4"
    ffprobe -v error -select_streams v -show_entries packet=pts_time,size -of csv=p=0 \
        "$dir/$id.crf23.mp4" > "$dir/$id.crf23.csv"
}
python3 -I - "$dir/$id.crf23.csv" "$win" <<'EOF'
import statistics, sys
rows = [l.split(",") for l in open(sys.argv[1]) if l.strip()]
win = int(sys.argv[2])
per_s = {}
for t, size in rows:
    if t in ("", "N/A"):
        continue
    per_s[int(float(t))] = per_s.get(int(float(t)), 0) + int(size)
dur = max(per_s) + 1
starts = range(300, dur - 300 - win + 1, 10)
w = {s: sum(per_s.get(t, 0) for t in range(s, s + win)) for s in starts}
med = statistics.median(w.values())
best = min(w, key=lambda s: abs(w[s] - med))
lo, hi = min(w.values()), max(w.values())
print(f"start_s={best} window_s={win} bytes={w[best]} median={med:.0f} "
      f"min={lo} max={hi} windows={len(w)} duration_s={dur}")
EOF
