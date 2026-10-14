#!/usr/bin/env bash
# One-line runner for Termux: installs what's missing, then builds the film.
#   bash daf_katan/make.sh                 # finds the video + playback on the phone
#   bash daf_katan/make.sh VIDEO PLAYBACK  # explicit files
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3 || command -v python || true)"

need=""
command -v ffmpeg >/dev/null || need="$need ffmpeg"
[ -n "$PY" ] || need="$need python"
if [ -n "$PY" ]; then
  "$PY" -c "import numpy" 2>/dev/null || need="$need python-numpy"
  "$PY" -c "import PIL" 2>/dev/null || need="$need python-pillow"
fi
if [ -n "$need" ]; then
  if command -v pkg >/dev/null; then
    echo "installing:$need"
    pkg install -y $need
  else
    echo "missing:$need - install them and run again"; exit 1
  fi
  PY="$(command -v python3 || command -v python)"
fi

if [ ! -d "$HOME/storage/shared" ] && command -v termux-setup-storage >/dev/null; then
  echo "Allow access to files on the phone ..."
  termux-setup-storage
  sleep 5
fi

# keep Android from killing the render half way
command -v termux-wake-lock >/dev/null && termux-wake-lock || true
status=0
"$PY" "$HERE/daf.py" "$@" || status=$?
command -v termux-wake-unlock >/dev/null && termux-wake-unlock || true

# show the film in the gallery straight away
OUT="/sdcard/Movies/דף קטן על פני הים.mp4"
if [ -f "$OUT" ] && command -v am >/dev/null; then
  am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file://$OUT" >/dev/null 2>&1 || true
fi
exit $status
