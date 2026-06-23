#!/usr/bin/env bash
# ====================================================================
# ClustroView - one-click launcher (Linux / macOS)
#
# Activates the `clustroview` conda env and starts the GUI.
# First-time setup: run ./setup_env.sh
# ====================================================================
set -e

ENV_NAME="clustroview"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Locate conda: prefer 'conda' on PATH, else look in common locations
if ! command -v conda >/dev/null 2>&1; then
    for cand in "$HOME/anaconda3/bin/conda" \
               "$HOME/miniconda3/bin/conda" \
               "/opt/anaconda3/bin/conda" \
               "/usr/local/anaconda3/bin/conda"; do
        if [ -x "$cand" ]; then
            # shellcheck disable=SC1090
            source "$(dirname "$cand")/../etc/profile.d/conda.sh"
            break
        fi
    done
fi

# Activate the env unless we are already inside it
if [ "${CONDA_DEFAULT_ENV:-}" != "$ENV_NAME" ]; then
    echo "Activating conda env: $ENV_NAME"
    # shellcheck disable=SC1090
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "$ENV_NAME" || {
        echo "ERROR: Failed to activate '$ENV_NAME'. Run ./setup_env.sh first." >&2
        exit 1
    }
fi

# Launch the GUI
echo "Starting ClustroView from $SCRIPT_DIR/front ..."
cd "$SCRIPT_DIR/front"
exec python main.py "$@"
