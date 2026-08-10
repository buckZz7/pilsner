#!/usr/bin/env bash
# Head-to-head: one fresh seed, one bundle — run against the CHALLENGER,
# then re-run the KING on the SAME bundle. Both receipts land (linked by
# seed + bundle hash); the board pools both; freshness for both, exact
# comparison (same tasks, same box, same session).
#
# Usage:  PILSNER_KING_MODEL=... PILSNER_KING_BASE_URL=... \
#         PILSNER_CHALLENGER_MODEL=... PILSNER_CHALLENGER_BASE_URL=... \
#         PILSNER_T2_DOMAIN=... PILSNER_BENCHBREW_SEED=... ./arena/head_to_head.sh
set -euo pipefail
cd "$(dirname "$0")/.."

: "${PILSNER_KING_MODEL:?set the king's model}"
: "${PILSNER_KING_BASE_URL:?set the king's endpoint}"
: "${PILSNER_CHALLENGER_MODEL:?set the challenger's model}"
: "${PILSNER_CHALLENGER_BASE_URL:?set the challenger's endpoint}"
: "${PILSNER_T2_DOMAIN:?set the lane}"
: "${PILSNER_BENCHBREW_SEED:?set the fresh seed}"

export OPENAI_API_KEY="${OPENAI_API_KEY:-pilsner-dummy-key}"

echo "=== head-to-head: ${PILSNER_T2_DOMAIN} seed ${PILSNER_BENCHBREW_SEED} ==="

# pass 1: the challenger on the fresh bundle
PILSNER_T2_DOMAIN="$PILSNER_T2_DOMAIN" \
PILSNER_BENCHBREW_SEED="$PILSNER_BENCHBREW_SEED" \
PILSNER_MODEL="$PILSNER_CHALLENGER_MODEL" \
PILSNER_BASE_URL="$PILSNER_CHALLENGER_BASE_URL" \
PILSNER_RUN_ROLE="challenger" \
uv run python arena/run_tau2.py

# pass 2: the king on the SAME bundle (same seed — no re-emit, identical tasks)
PILSNER_T2_DOMAIN="$PILSNER_T2_DOMAIN" \
PILSNER_BENCHBREW_SEED="$PILSNER_BENCHBREW_SEED" \
PILSNER_MODEL="$PILSNER_KING_MODEL" \
PILSNER_BASE_URL="$PILSNER_KING_BASE_URL" \
PILSNER_RUN_ROLE="king" \
uv run python arena/run_tau2.py

echo "=== done: challenger + king receipts for seed ${PILSNER_BENCHBREW_SEED} ==="
