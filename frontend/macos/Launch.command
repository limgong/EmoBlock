#!/bin/bash
set -e
cd "$(dirname "$0")/../.."
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python frontend/macos/launch.py
fi
exec python3 frontend/macos/launch.py
