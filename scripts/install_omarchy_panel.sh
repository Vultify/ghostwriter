#!/usr/bin/env bash
# Puts Ghostwriter's panel in Omarchy's bar: links ghostwriter/linux/omarchy into Omarchy's plugin folder, places
# the ghost just after the tray (beside its arrow, not behind it), and hides Ghostwriter's own tray icon there,
# since the panel takes its place.
# Other desktops keep the tray icon. Run it again any time; it only changes what isn't set up yet.
set -euo pipefail

project=$(cd "$(dirname "$0")/.." && pwd)
plugin_id=vultify.ghostwriter
plugins="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins"

if ! command -v omarchy >/dev/null; then
  echo "This desktop isn't Omarchy, so Ghostwriter stays in the tray."
  exit 0
fi

mkdir -p "$plugins"
ln -sfn "$project/ghostwriter/linux/omarchy" "$plugins/$plugin_id"
omarchy-shell -q shell rescanPlugins
# The shell finds new plugins in the background, so wait for it to know this one.
for _ in $(seq 1 20); do
  omarchy-shell shell listPlugins 2>/dev/null | grep -q "\"id\":\"$plugin_id\"" && break
  sleep 0.25
done
omarchy plugin enable "$plugin_id" --after omarchy.tray

# The tray icon's id is the tray item's name, "Ghostwriter": move it from pinned (if it was) to hidden.
pinned=$(omarchy bar get omarchy.tray pinned 2>/dev/null || echo '[]')
hidden=$(omarchy bar get omarchy.tray hidden 2>/dev/null || echo '[]')
omarchy bar set omarchy.tray pinned "$(jq -c 'map(select(. != "Ghostwriter"))' <<<"$pinned")" --json
omarchy bar set omarchy.tray hidden "$(jq -c '. + ["Ghostwriter"] | unique' <<<"$hidden")" --json

echo "Ghostwriter's panel is in the bar."
