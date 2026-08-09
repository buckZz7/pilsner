# SECURITY (draft for Pilsner)

## Reporting

Private disclosure to the maintainer (GitHub: buckZz7). Public issues are
fine for non-sensitive questions. No bounty program yet.

## In scope

- Gaming the scored battery: submissions designed to score well without
  doing the task (hardcoded outputs, configs that lie about the artifact,
  reward-hacking the instrument).
- Compromising the eval box or the receipt chain.
- Breaking the submission flow (serving.json abuse, path tricks under
  submissions/).

## Threat model (what we defend against)

- **Scoring fraud:** the eval box serves exactly what serving.json
  declares; the receipt records what ran. Anyone can re-run. Single box
  today, no TEE — the box operator is trusted; attested eval is on the
  roadmap.
- **Memorization:** tau2 is stateful (evolving DB state decides success);
  the task set is public by design. Freshness layer added only if
  evidence of contamination appears.
- **Config gaming:** a serving.json that claims a config the entry can't
  serve fails the size gate or scores poorly; the receipt makes the
  served config public.
- **Social:** no judge models, no human rubric on scores. The label is a
  function of the measured result.

## Out of scope

- Vulnerabilities in upstream tau2-bench, llama.cpp, or the serving
  engines (report to their projects).
