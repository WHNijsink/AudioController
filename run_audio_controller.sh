#!/bin/bash
# Run the audio_controller from within its package directory.
# set -e: abort on error; pipefail: fail a pipeline if any part fails.
# (-u is intentionally omitted: sourcing the venv activate script trips on unset vars.)
set -eo pipefail

# resolve paths relative to this script, not the current working directory (B2)
cd "$(dirname "$0")"

source pyenv/bin/activate
cd audio_controller
python3 -m audio_controller
cd ..
deactivate
