# Speed tier design note (2026-08-08)

## The question

The owner mandate says "concurrent throughput on one 5090." The arena's
current tie-break is time-to-task at light concurrency (parallel 2). Are
those the same? No — and the difference is the "pour rate" story.

## Measured reality (our own box, Q8 27B)

- decode: median 40 tok/s (p10 20 / p90 48), single stream
- prefill: median 1260 tok/s (up to 2951)
- VRAM math at 16k ctx / q8 KV: Q8 (28.5GB) fits ~2 slots; 1-bit
  (3.8GB) fits 16+; ternary (5.9GB) ~10; IQ2 (~9GB) ~6; 4B (4.3GB) ~12

## Field research (concurrency)

- llama.cpp is competitive-or-faster than vLLM up to ~16 parallel
  requests (llama.cpp/vllm comparison #15180, Red Hat, spheron). vLLM's
  continuous-batching edge appears at 16-100+ concurrent.
- Our entries are VRAM-bounded far below that for the dense rungs; the
  low-bit entries CAN reach high concurrency. So llama.cpp is the right
  engine for the scored measurement, and the concurrent ceiling is a
  real differentiator between entries.

## Decision (v1)

- Scored: quality gate at the fixed battery (parallel 2, reasoning off)
  + time-to-task tie-break from the same receipt. `parallel` is now in
  the receipt and in the challenge battery key (same-config comparisons
  enforced).
- Informational: pour rate on the board = max parallel slots that fit
  VRAM on the eval box x battery pace = tasks/min at full load. Reported,
  not scored.
- Path to scoring (if the mandate pushes): swap the tie-break to
  tasks/min at declared concurrency, measured same-box. One rule stays;
  the informational number becomes the scored one. Requires the size
  gate to pin the slot count (declared serving.json parallel validated
  to fit VRAM).

## Why informational-first

- One number, one rule, one tie-break (the design's core).
- The pour-rate number is load-bearing context for the board (the
  phone/edge story: same VRAM, more concurrent pours) without turning
  the arena into a kernel race.
- If the field demands it, the scored swap is a small, tested change.
