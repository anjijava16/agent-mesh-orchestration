#!/bin/bash
# Launcher for stop-local.sh
exec "$(dirname "$0")/scripts/stop-local.sh" "$@"
