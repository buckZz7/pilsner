#!/usr/bin/env bash
# One-command ladder analysis: pull receipts from the pod, produce the
# full board + per-receipt failure analysis + Bonsai comparison.
# Run from the local machine: bash _analyze_ladder.sh
set -euo pipefail
POD="root@157.157.221.29"
PORT=52659
OUT="/opt/data/pilsner/outputs"
mkdir -p "$OUT"

echo "== pulling receipts =="
scp -q -o StrictHostKeyChecking=no -i ~/.ssh/id_ed25519 -P "$PORT" \
  "$POD":/root/receipts/report_tau2_seed*.json "$OUT"/ 2>/dev/null \
  || echo "(none on pod yet)"

# archive raw results by unique name (pod fs is ephemeral — the raw
# trajectories are the ground truth behind the receipts)
mkdir -p "$OUT/raw"
for r in "$OUT"/report_tau2_seed*.json; do
  [ -f "$r" ] || continue
  rf=$(python3 -c "import json,sys;print(json.load(open('$r')).get('results_file',''))" 2>/dev/null)
  model=$(python3 -c "import json,sys;print(json.load(open('$r')).get('model','raw'))")
  [ -n "$rf" ] || continue
  scp -q -o StrictHostKeyChecking=no -i ~/.ssh/id_ed25519 -P "$PORT" \
    "$POD:/root/tau2-bench/data/simulations/$(basename "$(dirname "$rf")")/results.json" \
    "$OUT/raw/$model.json" 2>/dev/null || true
done

cd /opt/data/pilsner
RECEIPTS=$(ls outputs/report_tau2_seed*.json 2>/dev/null | sort || true)
if [ -z "$RECEIPTS" ]; then
  echo "no receipts on pod yet — ladder still running"
  exit 0
fi

echo "== trust audit =="
python3 -m arena.audit $RECEIPTS || echo "WARNING: receipts not fully comparable — board is directional only"

echo
echo "== board =="
python3 -m arena.board outputs --write

# append-only board ledger (sparkinfer pattern): every board state is
# auditable line-by-line, never rewritten
LEDGER=outputs/board_ledger.jsonl
touch "$LEDGER"
for r in $RECEIPTS; do
  python3 -c "
import json, datetime
rec = json.load(open('$r'))
row = {'ts': datetime.datetime.utcnow().isoformat() + 'Z',
       'model': rec.get('model'), 'score': rec.get('success_rate'),
       'n_scored': rec.get('n_scored'), 'wall_clock_s': rec.get('wall_clock_s'),
       'engine_version': rec.get('engine_version'),
       'model_sha256': rec.get('model_sha256'), 'gpu_clock': rec.get('gpu_clock'),
       'receipt': '$r'}
print(json.dumps(row, sort_keys=True))
" >> "$LEDGER"
done
echo "ledger appended: $(wc -l < "$LEDGER") entries"

for r in $RECEIPTS; do
  echo
  echo "== failure analysis: $r =="
  python3 -m arena.failure_analysis "$r" 2>&1 | head -8
  echo
  echo "== diagnostics: $r =="
  python3 -m arena.diagnostics "$r" 2>&1 | head -6
done

echo
echo "== bonsai comparison =="
python3 -m arena.bonsai_compare $RECEIPTS 2>&1 | head -25
