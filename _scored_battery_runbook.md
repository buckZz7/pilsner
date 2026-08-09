# Scored battery runbook (fixed-user design, 2026-08-08)

The ladder survey is DIRECTIONAL (same-model-both user sim = confound).
The scored battery is what crowns kings: FIXED user simulator across all
entries. Agent varies, customer is constant.

## The confound (why this exists)

Ladder convention: each rung plays agent AND customer. A weak customer is
a pushover (asks fewer questions, accepts more) -> inflates its own agent
score. Falsification from the ladder is valid (a loss with the bias
helping you is real); confirmation needs the fixed-user rerun.

## Fixed user choice

- Universal fit: Qwen3-4B Q4_K_M (2.5GB) — fits alongside every agent
  rung on 32GB (worst case: Q8 agent 28.5 + 2.5 + KV = ~31.5, tight but
  OK at 16k ctx with q8 KV; use 8k ctx if it doesn't fit).
- Stronger user option (1-bit/ternary agent only): the Q8 27B itself as
  the user sim (28.5GB + small agent fits) — keeps the hard tail hardest.
- The 4B user may flatten difficulty (weak customer = easy tasks). The
  validation gate below decides whether it's sharp enough.

## Two-server serving (scored battery)

CONTEXT RULE: with a non-unified KV cache, `-c N --parallel P` gives each
slot N/P context (NOT N). Every entry must get 16k per conversation slot:
small agents (<12GB) `-c 32768 --parallel 2`; the Q8 floor `-c 16384
--parallel 1`. ALWAYS verify `n_ctx_slot` in the serve log at startup
(`grep n_ctx_slot serve_*.log`) — an 8k slot halves context silently.

```
agent server:  llama-server -p 8000 -m <agent.gguf>  -c 32768 --parallel 2 ... --reasoning off
user server:   llama-server -p 8001 -m Qwen3-4B-Q4_K_M.gguf -c 8192 --parallel 2 ... --reasoning off
```

Run (per entry):

```bash
PILSNER_MODEL=<entry> PILSNER_BASE_URL=http://127.0.0.1:8000/v1 \
PILSNER_USER_MODEL=qwen3-4b-q4km PILSNER_USER_BASE_URL=http://127.0.0.1:8001/v1 \
PILSNER_T2_DIR=/root/tau2-bench PILSNER_T2_TASKS=50 PILSNER_T2_TRIALS=2 \
PILSNER_T2_DOMAINS=airline,retail \
PILSNER_T2_MAX_STEPS=50 PILSNER_T2_MAX_STEPS_SECONDS=600 \
PILSNER_SEED=<n> PILSNER_REASONING=off PILSNER_ENGINE=llama.cpp \
PILSNER_ENGINE_VERSION=$(cd /root/llama.cpp && git rev-parse --short HEAD) \
PILSNER_PARALLEL=2 PILSNER_CTX=16384 PILSNER_OUT=/root/receipts \
python3 -m arena.run_tau2
```

Receipt records agent_llm + user_llm; the challenge referee refuses
matchups with different user sims.

## Validation gate (does the fixed user still discriminate?)

After the first fixed-user battery: `python3 -m arena.failure_analysis
<receipt>`. PASS = failed tasks are significantly harder than passed
(mean difficulty spread >= ~2 points, hard-tail pass rate < easy rate).
FAIL = uniform failures -> the fixed user flattened the battery; switch
to the stronger fixed user (Q8) or accept reduced discrimination with
disclosure.

## Bias quantification experiment (calibrate, don't guess)

One battery, three user sims, same agent (Q8), 50 tasks x 1 trial each:

1. Q8 agent + Q8 user       (the ladder confound baseline)
2. Q8 agent + 1-bit user    (how much does a weak customer inflate?)
3. Q8 agent + 4B user       (the fixed-user candidate)

Score spread between (1) and (2) = the confound's size. Spread between
(1) and (3) = what switching to the fixed user costs in absolute terms.
~3h on the box, ~$3. Run once, record in the skill reference.

## King-vs-challenger flow (the arena's actual decision)

SCORED BATTERY (multi-domain, cost-neutral): 2 trials x 50 tasks x 2
domains (airline + retail) = 200 sims — same power and price as 4x50
single-domain, with breadth (harder to specialize/memorize; retail's
distribution is sharper: 60/114 tasks need 5+ actions). Task caps: 50
steps / 600s per attempt (tau2's 200-step default lets pathological
tasks grind ~2h). PILSNER_T2_DOMAINS=airline,retail,
PILSNER_T2_TRIALS=2, PILSNER_T2_MAX_STEPS=50,
PILSNER_T2_MAX_STEPS_SECONDS=600.

1. Entry passes size gate + submission validation (CI).
2. Eval box serves agent (:8000) + fixed user (:8001), runs the scored
   battery (~4.5h, ~$4.50/model at $0.99/hr).
3. Receipt lands; `python3 -m arena.challenge king.json challenger.json`
   -> WIN/LOSS/REFUSE (refuses on battery mismatch incl. user sim,
   context, caps).
4. WIN by >2%: new king. Board updates. Old king's receipt stays public.
5. LOSS: PR closed, receipt public, label applied.

## Post-ladder execution sequence (locks in 2026-08-09)

When the 5-rung ladder completes (1-bit, 4B, IQ2, Q2_K_XL, Q8), run in
this order — quick diagnostics first so the expensive decisions are
data-driven:

0. **IQ1 cliff-pinning rungs** (`_iq1_batteries.sh`, ~1.5h, seeds 7/8):
   IQ1_S (~1.6 bpw) + IQ1_M (~1.75 bpw) for Qwen3.6-27B (mradermacher
   i1 imatrix quants — the only pre-made IQ1 artifacts). The scientific
   question: is the 1-bit collapse bit-depth or group-scale-resolution?
   IQ1_S surviving where Q1_0 died = scale granularity (fixable);
   dying like Q1_0 = the cliff is real below ~2 bpw. These are ladder
   extensions (same operating point, same build) — they pin the cliff
   between Bonsai's Q1_0 (1.125) and IQ2_XXS (2.06).
0b. **Entity-inject adapter experiment** (`_adapter_experiment.sh`,
   ~40 min, seed 9): Bonsai 1-bit served THROUGH the entity-inject
   proxy (agent via :8000 proxy -> :8001 server, user direct). The
   mechanism (generation-time exact-string corruption, 98% of errors =
   wrong user ID) predicts the adapter either lifts the score off 0.16
   (collapse is partly salience/attention -> serving-layer fix works)
   or not (arg-generation machinery -> weights-only fix). Either way:
   the arena's first challenger, measured on its own ruler, receipts
   public. The serving-layer allowlist becomes real.

1. **Kernel control** (`_kernel_control.sh`, ~20 min): Bonsai 1-bit vs
   Q8 on the eval/ FC harness (OLD build — the same build that produced
   the 0.16). Decent 1-bit FC score + tau2 failure = genuine precision
   collapse; failure everywhere = Q1_0 kernel artifact.
2. **MTP probe** (`_probe_mtp.sh`, ~15 min): does `--reasoning on`
   terminate cleanly? If runaways persist, the companion battery is
   meaningless (thinking is broken at the model level, not the flag).
3. **Companion battery** (`_companion_battery.sh`, ~1.5h, seeds 31/32):
   Bonsai 1-bit + Q8 with THINKING ON — their methodology, the
   apples-to-apples reproduction of their 61.34 claim. If 1-bit
   recovers to ~60: "the phone model needs cloud-grade thinking." If it
   stays near 0.16: the collapse is operating-point-independent.
4. **Bias experiment** (`_bias_experiment.sh`, ~1h): IQ2 agent x 3 user
   sims (seeds 21-23) — quantifies the same-model user confound (the
   VRAM-feasible version; the runbook's ideal Q8-agent version needs a
   second big model that 32GB can't pair).
5. **Scored king battery** (the PRIZE, ~4.5h, ~$4.50): Q2_K_XL (interim
   king) with the fixed 4B user, multi-domain (airline+retail), 200
   sims, caps 50/600. This is the FIRST real king verification — the
   ladder was directional; this crowns with statistical teeth.

Total ~8h pod time (~$8). All receipts carry engine_version; the
challenge referee refuses cross-build matchups.
