#!/usr/bin/env bash
# encode.sh <frames_dir> <out.mp4|out.mov> [--audio score.wav] [--fps 60] [--tmix N] [--alpha]
# (--alpha expects a PNG frame dir and a .mov output path — see below)
#
# Encodes a JPEG frame sequence to H.264 with sensible settings for social
# platforms (high profile, faststart, closed GOP every 2s).
#
# --tmix N averages N consecutive input frames and decimates to --fps, giving
# true 360-degree-shutter motion blur. Render at N x the target fps to use it:
#   render at 120fps  ->  encode.sh dir out.mp4 --fps 60 --tmix 2
# Without --tmix the frame rate is taken as-is.
#
# --alpha packs a transparent PNG sequence (render_frames.py --alpha output)
# into ProRes 4444 with a real alpha channel (yuva444p10le). Output should
# end in .mov. This was VP9/yuva420p/WebM originally, per this skill's own
# older §10.5 note — verified BROKEN with ffmpeg 8.1.2:
# encode reports no errors and even tags alpha_mode=1 in metadata, but the
# alpha plane does not survive decode (round-tripped back to solid opaque).
# ProRes 4444 was verified frame-for-frame correct (decoded alpha matches
# the source PNG exactly) — use it unless a specific downstream tool needs
# WebM, in which case re-test the VP9 path on that machine before trusting it.
# If the destination is a footage-led editing workflow (e.g. aaaai-video-editor)
# that only needs the raw frames, skip encoding
# entirely and hand over the PNG directory as-is — that is the primary
# interop path; this flag is for when a packaged alpha video file is wanted.
set -euo pipefail

# --- ffmpeg / ffprobe resolution ------------------------------------------
# Order: $AAAAI_EDITOR_FFMPEG -> Apple Silicon ffmpeg-full (keg-only) -> Intel
# ffmpeg-full -> whatever `ffmpeg` is on PATH. ffprobe is taken as the
# sibling of the chosen ffmpeg when it exists there, else from PATH.
resolve_ffmpeg() {
  local c
  for c in "${AAAAI_EDITOR_FFMPEG:-}" \
           /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg \
           /usr/local/opt/ffmpeg-full/bin/ffmpeg; do
    if [[ -n "$c" && -x "$c" ]]; then echo "$c"; return 0; fi
  done
  command -v ffmpeg || { echo "ffmpeg not found (set AAAAI_EDITOR_FFMPEG)" >&2; return 1; }
}
FFMPEG="$(resolve_ffmpeg)"
FFPROBE="$(dirname "$FFMPEG")/ffprobe"
[[ -x "$FFPROBE" ]] || FFPROBE="$(command -v ffprobe || echo ffprobe)"

DIR="${1:?frames dir}"; OUT="${2:?output mp4}"; shift 2
AUD=""; FPS=60; TMIX=1; CRF=17; ALPHA=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --audio) AUD="$2"; shift 2 ;;
    --fps)   FPS="$2"; shift 2 ;;
    --tmix)  TMIX="$2"; shift 2 ;;
    --crf)   CRF="$2"; shift 2 ;;
    --alpha) ALPHA=1; shift 1 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

IN_FPS=$(( FPS * TMIX ))
KEYINT=$(( FPS * 2 ))

if [[ "$ALPHA" -eq 1 ]]; then
  if [[ "$TMIX" -gt 1 ]]; then
    W=$(printf '1 %.0s' $(seq 1 "$TMIX")); W="${W% }"
    VF="[0:v]tmix=frames=${TMIX}:weights='${W}',fps=${FPS},format=yuva444p10le[v]"
  else
    VF="[0:v]format=yuva444p10le[v]"
  fi
  "$FFMPEG" -y -loglevel error -stats \
    -framerate "$IN_FPS" -start_number 0 -i "$DIR/f%05d.png" \
    -filter_complex "$VF" -map "[v]" \
    -c:v prores_ks -profile:v 4 -pix_fmt yuva444p10le \
    "$OUT"
  echo "--- $OUT (ProRes 4444 alpha — verified round-trips correctly; large file, intended for NLE handoff not web delivery)"
  "$FFPROBE" -v error -select_streams v:0 \
    -show_entries stream=width,height,r_frame_rate,nb_frames,pix_fmt \
    -show_entries format=duration,size -of default=noprint_wrappers=1 "$OUT"
  exit 0
fi

if [[ "$TMIX" -gt 1 ]]; then
  W=$(printf '1 %.0s' $(seq 1 "$TMIX")); W="${W% }"
  VF="[0:v]tmix=frames=${TMIX}:weights='${W}',fps=${FPS},format=yuv420p[v]"
else
  VF="[0:v]format=yuv420p[v]"
fi

X264="keyint=${KEYINT}:min-keyint=$(( KEYINT / 4 )):scenecut=0:ref=4:bframes=3"

if [[ -n "$AUD" ]]; then
  "$FFMPEG" -y -loglevel error -stats \
    -framerate "$IN_FPS" -start_number 0 -i "$DIR/f%05d.jpg" -i "$AUD" \
    -filter_complex "$VF" -map "[v]" -map 1:a \
    -c:v libx264 -profile:v high -level 4.2 -preset slow -crf "$CRF" \
    -x264-params "$X264" \
    -c:a aac -b:a 192k -ar 48000 -ac 2 \
    -movflags +faststart -shortest "$OUT"
else
  "$FFMPEG" -y -loglevel error -stats \
    -framerate "$IN_FPS" -start_number 0 -i "$DIR/f%05d.jpg" \
    -filter_complex "$VF" -map "[v]" \
    -c:v libx264 -profile:v high -level 4.2 -preset slow -crf "$CRF" \
    -x264-params "$X264" -movflags +faststart "$OUT"
fi

echo "--- $OUT"
"$FFPROBE" -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,nb_frames \
  -show_entries format=duration,size -of default=noprint_wrappers=1 "$OUT"
