# novai-canary

Reproducible model-fidelity evidence for `aiapi-pro.com` (NovAI), the relay listed under
"unverified" in [cuihuan/awesome-ai-gateway](https://github.com/cuihuan/awesome-ai-gateway).

The question this answers: **does the relay serve the model it claims, or a cheaper one?**
It does not answer billing accuracy, privacy, or uptime.

## Protocol

- Model: `deepseek-v4-pro`, present on both the relay and the official DeepSeek API.
- Endpoints: relay `https://aiapi-pro.com/v1`, reference `https://api.deepseek.com/v1`.
- 7 fixed probes, `temperature: 0`, `max_tokens: 96`, **3 repeats per probe per endpoint**
  (21 relay calls, 21 reference calls).
- Probes are graded by a deterministic predicate (exact string, parsed JSON equality, or a
  single expected integer) — no LLM-as-judge.
- A **downgrade** is only flagged when the relay fails a probe that the reference *passes*.
  Both sides failing is a model limitation, not a relay fault.
- A tokenizer fingerprint is taken separately: the same 360-character prompt must yield the
  same `prompt_tokens` on both endpoints.

## Results — 2026-11-05

| probe | relay | reference | downgrade |
| --- | --- | --- | --- |
| echo_json | 3/3 | 3/3 | no |
| primes | 3/3 | 3/3 | no |
| arith (17*23) | 3/3 | 3/3 | no |
| count_r ("strawberry") | 1/3 | 0/3 | no |
| exact_ok | 3/3 | 3/3 | no |
| list_len | 3/3 | 3/3 | no |
| json_keys | 3/3 | 3/3 | no |

```
prompt_tokens: relay=164  reference=164  skew=0
downgrade_flags: []
verdict: OK — no probe passed on the reference while failing on the relay
```

`count_r` is the interesting row: **both** endpoints fail it most of the time — the classic
"how many r in strawberry" weakness. The relay scored 1/3 and the reference 0/3, so this row
carries no signal about fidelity in either direction.

Raw output: [`results-2026-11-05.json`](results-2026-11-05.json). Script: [`canary.py`](canary.py).

## How to reproduce independently

You need your own keys for both sides — that is the point of an independent run.

```bash
pip install nothing   # stdlib only
export RELAY_BASE=https://aiapi-pro.com/v1
export RELAY_KEY=<your NovAI key>          # signup: https://aiapi-pro.com/signup
export REF_BASE=https://api.deepseek.com/v1
export REF_KEY=<your DeepSeek key>
python canary.py
```

Edit the constants at the top of `canary.py` if you prefer to point it at another model pair;
the relay also serves Qwen, GLM, Kimi, MiniMax and Doubao.

## Limits, stated plainly

- 7 probes on **one** model route. It says nothing about the other 110 models.
- It cannot detect subtle quantisation that preserves these behaviours.
- It says nothing about billing, logging, retention or uptime.
- It was run by the operator. **Self-reported evidence cannot promote the listing out of
  "unverified"** — this repo exists so an unaffiliated party can re-run it cheaply and the
  result can be compared line by line.

Maintained by NovAI (operator of aiapi-pro.com). Affiliation disclosed deliberately.

## Where this is linked from

- Write-up with the reasoning and the exact failure mode this protocol avoids:
  https://aiapi-pro.com/blog/is-my-llm-api-relay-downgrading-the-model
- The trust page it backs: https://aiapi-pro.com/provenance.html
