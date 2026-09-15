#!/usr/bin/env bash
# Set your API keys in .env without wiping what's already there, then run the app.
# Input is hidden and never touches shell history. Press Enter to keep a key as-is.
set -euo pipefail
cd "$(dirname "$0")"

[ -f .env ] || cp .env.example .env

read -rsp "Tavily API key (hidden, Enter to keep current): " TAVILY_IN; echo
read -rsp "Nebius API key (hidden, Enter to keep current): " NEBIUS_IN; echo

TAVILY_IN="$TAVILY_IN" NEBIUS_IN="$NEBIUS_IN" python3 - <<'PY'
import os, pathlib, re

env = pathlib.Path(".env")
updates = {
    "TAVILY_API_KEY": os.environ.get("TAVILY_IN", "").strip(),
    "NEBIUS_API_KEY": os.environ.get("NEBIUS_IN", "").strip(),
}
updates = {k: v for k, v in updates.items() if v}

lines = env.read_text().splitlines()
written = set()
for i, line in enumerate(lines):
    match = re.match(r"^([A-Z0-9_]+)=", line)
    if match and match.group(1) in updates:
        lines[i] = f"{match.group(1)}={updates[match.group(1)]}"
        written.add(match.group(1))

for key, value in updates.items():
    if key not in written:
        lines.append(f"{key}={value}")

env.write_text("\n".join(lines) + "\n")
env.chmod(0o600)

for key in ("TAVILY_API_KEY", "NEBIUS_API_KEY"):
    current = next((l.split("=", 1)[1] for l in lines if l.startswith(key + "=")), "")
    print(f"  {key}: {len(current)} chars" if current else f"  {key}: STILL EMPTY")
PY

echo
[ "${SKIP_RUN:-0}" = "1" ] && exit 0
exec ./run.sh
