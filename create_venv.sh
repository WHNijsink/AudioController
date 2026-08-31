#!/bin/bash
# Create the python virtualenv for the audio_controller.
# set -e: abort on error; pipefail: fail a pipeline if any part fails.
# (-u is intentionally omitted: sourcing the venv activate script trips on unset vars.)
set -eo pipefail

# resolve paths relative to this script, not the current working directory (B2)
cd "$(dirname "$0")"

rm -rf ./pyenv
python3 -m venv pyenv
source ./pyenv/bin/activate
python -m pip install -U pip
python -m pip install pylint
python -m pip install black
python -m pip install pyserial
python -m pip install tornado
python -m pip install python-socketio
python -m pip install transcrypt
python -m pip install watchdog
python -m pip install python-decouple
python -m pip install onvif-zeep
python -m pip install pytest
cd audio_controller
python -m pip install --editable .
cd ..
deactivate
