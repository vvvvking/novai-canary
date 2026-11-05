#!/usr/bin/env python3
"""Canary fidelity test: does the relay serve the same model as the official API?

Protocol: fixed probing prompts, temperature 0, 3 repeats each, run against both
the relay and the official provider. A downgrade is only flagged when the relay
fails a probe that the reference passes (not the other way around).
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

MODEL = "deepseek-v4-pro"
RELAY = "https://aiapi-pro.com/v1"
REF = "https://api.deepseek.com/v1"
REPEATS = 3

PROBES = [
    ("echo_json", 'Return exactly this JSON and nothing else: {"a":1,"b":[2,3]}',
     lambda t: t.strip().replace(" ", "") == '{"a":1,"b":[2,3]}'),
    ("primes", "Return the first 8 prime numbers as a JSON array and nothing else.",
     lambda t: _json_eq(t, [2, 3, 5, 7, 11, 13, 17, 19])),
    ("arith", "What is 17*23? Answer with the number only.", lambda t: _num(t) == 391),
    ("count_r", 'How many letter r are in the word "strawberry"? Answer with the number only.',
     lambda t: _num(t) == 3),
    ("exact_ok", "Reply with exactly: OK", lambda t: t.strip() == "OK"),
    ("list_len", "List the integers 1 to 10 separated by single spaces, nothing else.",
     lambda t: re.sub(r"\s+", " ", t.strip()) == "1 2 3 4 5 6 7 8 9 10"),
    ("json_keys", 'Output a JSON object with keys "x" and "y" where x=1 and y=2.',
     lambda t: _json_obj(t, {"x": 1, "y": 2})),
]


def _num(text):
    m = re.search(r"-?\d+", text.replace(",", ""))
    return int(m.group(0)) if m else None


def _json_eq(text, expected):
    try:
        start, end = text.find("["), text.rfind("]")
        return json.loads(text[start:end + 1]) == expected
    except Exception:
        return False


def _json_obj(text, expected):
    try:
        start, end = text.find("{"), text.rfind("}")
        d = json.loads(text[start:end + 1])
        return all(str(d.get(k)) == str(v) for k, v in expected.items())
    except Exception:
        return False


def call(base, key, prompt, max_tokens=96):
    payload = {"model": MODEL, "messages": [{"role": "user", "content": prompt}],
               "temperature": 0, "max_tokens": max_tokens}
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "User-Agent": "novai-canary/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
            text = d["choices"][0]["message"]["content"]
            usage = d.get("usage") or {}
            return {"ok": True, "text": text, "prompt_tokens": usage.get("prompt_tokens")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"{e.code}: {e.read().decode(errors='replace')[:120]}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def env_val(path, keyname):
    for line in Path(path).read_text().splitlines():
        if line.startswith(keyname + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


relay_key = env_val("/opt/novai/.secrets/qa.env", "QA_API_KEY")
if not relay_key:
    raise SystemExit("missing QA_API_KEY in /opt/novai/.secrets/qa.env")
ref_key = env_val("/opt/novai/.env", "DEEPSEEK_API_KEY")
print(f"model={MODEL} repeats={REPEATS} probes={len(PROBES)}")

results = []
for name, prompt, check in PROBES:
    row = {"probe": name, "relay": [], "ref": []}
    for _ in range(REPEATS):
        r = call(RELAY, relay_key, prompt)
        row["relay"].append({"ok": r["ok"] and check(r["text"] or ""), "raw": r})
        time.sleep(1.2)
        r2 = call(REF, ref_key, prompt)
        row["ref"].append({"ok": r2["ok"] and check(r2["text"] or ""), "raw": r2})
        time.sleep(1.2)
    rp = sum(1 for x in row["relay"] if x["ok"])
    fp = sum(1 for x in row["ref"] if x["ok"])
    row["relay_pass"] = f"{rp}/{REPEATS}"
    row["ref_pass"] = f"{fp}/{REPEATS}"
    row["downgrade"] = bool(rp < fp)
    results.append(row)
    print(f"  {name:<10} relay={rp}/{REPEATS} ref={fp}/{REPEATS}"
          f"{'  <-- DOWNGRADE' if row['downgrade'] else ''}")

# tokenizer fingerprint: same prompt should tokenise identically
probe = "The quick brown fox jumps over the lazy dog. " * 8
t_relay = call(RELAY, relay_key, probe)["prompt_tokens"]
t_ref = call(REF, ref_key, probe)["prompt_tokens"]
print(f"\nprompt_tokens: relay={t_relay} ref={t_ref} skew={None if None in (t_relay, t_ref) else t_relay - t_ref}")

flags = [r["probe"] for r in results if r["downgrade"]]
out = {"model": MODEL, "repeats": REPEATS, "results": results,
       "prompt_tokens": {"relay": t_relay, "ref": t_ref},
       "downgrade_flags": flags,
       "verdict": "OK - no probe passed on the reference while failing on the relay"
       if not flags else "SUSPECT - relay failed a probe the reference passed"}
Path("/tmp/canary_result.json").write_text(json.dumps(out, indent=2))
print("\nverdict:", out["verdict"])
