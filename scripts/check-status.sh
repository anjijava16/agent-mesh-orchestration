#!/bin/bash
# Launcher for check-status.sh
exec "$(dirname "$0")/scripts/check-status.sh" "$@"
