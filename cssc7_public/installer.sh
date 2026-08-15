#!/bin/sh
# CSSC installer bootstrap (Linux / macOS). Finds a Python 3.12 — bundled first,
# then a system one — and runs installer.py with it.
HERE="$(cd "$(dirname "$0")" && pwd)"
PY=""

# 1) bundled embeddable Python (fully offline)
if [ -x "$HERE/python/bin/python3" ]; then
  PY="$HERE/python/bin/python3"
fi

# 2) a system Python that is exactly 3.12
if [ -z "$PY" ]; then
  for c in python3.12 python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)' >/dev/null 2>&1; then
        PY="$c"
        break
      fi
    fi
  done
fi

if [ -z "$PY" ]; then
  echo ""
  echo "  Python 3.12 was not found and no bundled runtime is present."
  echo "  Install Python 3.12 from https://www.python.org/downloads/ and re-run."
  echo ""
  exit 1
fi

echo "Using Python: $PY"
echo ""
"$PY" "$HERE/installer.py" "$@"
