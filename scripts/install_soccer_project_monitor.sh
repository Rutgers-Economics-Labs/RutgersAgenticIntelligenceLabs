#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
PROJECT_SLUG="${PROJECT_SLUG:-european-soccer-competitive-ecosystem-analysis}"
API_ROOT="${API_ROOT:-http://127.0.0.1:8000/api/v1}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-600}"
REMIND_AFTER_MINUTES="${REMIND_AFTER_MINUTES:-90}"
STATE_DIR="${STATE_DIR:-$HOME/Library/Application Support/RAIL/external-monitors}"
LOG_DIR="${LOG_DIR:-$HOME/Library/Logs/RAIL}"
PLIST_PATH="$HOME/Library/LaunchAgents/com.rail.soccer-project-monitor.plist"

mkdir -p "$(dirname "$PLIST_PATH")" "$LOG_DIR" "$STATE_DIR"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.rail.soccer-project-monitor</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$ROOT_DIR/scripts/monitor_soccer_project.py</string>
    <string>--project-slug</string>
    <string>$PROJECT_SLUG</string>
    <string>--api-root</string>
    <string>$API_ROOT</string>
    <string>--health-url</string>
    <string>$HEALTH_URL</string>
    <string>--state-dir</string>
    <string>$STATE_DIR</string>
    <string>--remind-after-minutes</string>
    <string>$REMIND_AFTER_MINUTES</string>
    <string>--advance</string>
    <string>--notify</string>
  </array>
  <key>StartInterval</key>
  <integer>$INTERVAL_SECONDS</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/soccer-project-monitor.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/soccer-project-monitor.err.log</string>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl kickstart -k "gui/$(id -u)/com.rail.soccer-project-monitor"

echo "Installed com.rail.soccer-project-monitor"
echo "Plist: $PLIST_PATH"
echo "Logs: $LOG_DIR/soccer-project-monitor.log"
echo "State: $STATE_DIR/$PROJECT_SLUG.json"
