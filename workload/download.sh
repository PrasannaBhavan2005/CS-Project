#!/usr/bin/env bash
# Download a clip's full source video (videos stay out of git).
#
# Usage: workload/download.sh <clip>        (clip name from workload/clips.csv)
# Writes workload/src/<youtube_id>.mp4 (best H.264 stream up to 1080p, no
# audio) and <youtube_id>.info.txt (format, size, sha256, yt-dlp version,
# download time). encode.sh cuts the clip's window from it. The whole lecture
# is downloaded because cutting a section at download time either snaps to a
# keyframe or re-encodes.
# Needs yt-dlp (~/.venvs/tools/bin/yt-dlp or on PATH).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
clip=${1:?usage: download.sh <clip>}
id=$(python3 -I -c "
import csv, sys
for r in csv.DictReader(open('$here/clips.csv')):
    if r['clip'] == '$clip': print(r['youtube_id']); break
else: sys.exit('download.sh: no clip $clip in clips.csv')")
ytdlp=$(command -v yt-dlp || echo "$HOME/.venvs/tools/bin/yt-dlp")
mkdir -p "$here/src"
out=$here/src/$id.mp4
if [[ -f $out ]]; then echo "$out exists"; exit 0; fi
"$ytdlp" -q -f "bv*[height<=1080][vcodec^=avc1]" -o "$out" "https://www.youtube.com/watch?v=$id"
{
    echo "youtube_id=$id"
    echo "url=https://www.youtube.com/watch?v=$id"
    ffprobe -v error -select_streams v -show_entries stream=codec_name,width,height,r_frame_rate,bit_rate \
        -show_entries format=duration -of default=nw=1 "$out"
    echo "sha256=$(sha256sum "$out" | cut -d' ' -f1)"
    echo "yt_dlp=$("$ytdlp" --version)"
    echo "downloaded=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$here/src/$id.info.txt"
cat "$here/src/$id.info.txt"
