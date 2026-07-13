#!/usr/bin/env bash
set -euo pipefail

# Creates a virtual environment in pvlib/.venv and installs requirements
# Usage: bash pvlib/setup_venv.sh

PYTHON=${PYTHON:-python3}
VENV_DIR=${VENV_DIR:-.venv}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/$VENV_DIR"

echo "Creating virtual environment at $VENV_PATH using $PYTHON..."
$PYTHON -m venv "$VENV_PATH"

echo "Upgrading pip and installing requirements..."
"$VENV_PATH/bin/python" -m pip install --upgrade pip
"$VENV_PATH/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

cat <<EOF
Done.
Activate the virtual environment with:
  source $VENV_PATH/bin/activate
Then run the example:
  python $SCRIPT_DIR/minimalExample.py
EOF
