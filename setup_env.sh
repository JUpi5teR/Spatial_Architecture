#!/usr/bin/env bash
# ====================================================================
# ClustroView - first-time environment setup (Linux / macOS)
#
# Creates the `clustroview` conda env (Python 3.12) and installs
# front/requirements.txt into it. Safe to re-run.
#
# Usage:  ./setup_env.sh
# ====================================================================
set -e

ENV_NAME="clustroview"
PY_VERSION="3.12"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== ClustroView first-time setup ==="
echo

# Locate conda
if ! command -v conda >/dev/null 2>&1; then
    for cand in "$HOME/anaconda3/bin/conda" \
               "$HOME/miniconda3/bin/conda" \
               "/opt/anaconda3/bin/conda" \
               "/usr/local/anaconda3/bin/conda"; do
        if [ -x "$cand" ]; then
            PATH="$(dirname "$cand"):$PATH"
            break
        fi
    done
    if ! command -v conda >/dev/null 2>&1; then
        echo "ERROR: 'conda' not found. Install Anaconda or Miniconda first." >&2
        exit 1
    fi
fi

# shellcheck disable=SC1090
source "$(conda info --base)/etc/profile.d/conda.sh"

# Create env if it does not exist
if ! conda info --envs | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    echo "Creating conda env '$ENV_NAME' with Python $PY_VERSION ..."
    conda create -n "$ENV_NAME" "python=$PY_VERSION" -y
else
    echo "Conda env '$ENV_NAME' already exists - skipping create."
fi

echo
echo "Activating '$ENV_NAME' and installing dependencies ..."
conda activate "$ENV_NAME"

# The 'python>=3.10' line in requirements.txt is a metadata directive,
# not a real pip package. Filter it out before installing.
REQ_FILE="$SCRIPT_DIR/front/requirements.txt"
TMP_FILE="$(mktemp)"
trap 'rm -f "$TMP_FILE"' EXIT
grep -v -E '^python[><=]' "$REQ_FILE" > "$TMP_FILE" || true

python -m pip install --upgrade pip
python -m pip install -r "$TMP_FILE"

echo
echo "=== Setup complete ==="
echo "Run ./run.sh to start the GUI."
