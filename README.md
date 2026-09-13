<p align="center">
  <img src="openbundle-logo-horizontal-dark.svg" alt="openbundle" width="480">
</p>

<p align="center">
  <strong>~20× fewer prompt tokens out of the box</strong><br>
  <strong>15–40× cost · 6–8× memory</strong> if you add memory and quantization yourself
</p>

<p align="center">Your number is <code>openbundle report</code> on this traffic.</p>

<h3 align="center">One install. A local proxy that auto-wires the open-source LLM optimizations that actually help — and shows you the receipts.</h3>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square" alt="Python 3.11+"></a>
  <a href=".github/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/openbundle/openbundle/ci.yml?branch=main&style=flat-square" alt="CI"></a>
  <a href="#the-catalog"><img src="https://img.shields.io/badge/tracks-66%20OSS%20tools-informational?style=flat-square" alt="66 tools tracked"></a>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#the-catalog">Catalog</a> ·
  <a href="#not-another-ai-gateway">vs. gateways</a> ·
  <a href="#security-and-data">Security</a>
</p>

```bash
pip install openbundle
openbundle init && openbundle serve
export ANTHROPIC_BASE_URL=http://127.0.0.1:4180   # or OPENAI_BASE_URL
```

Point Claude Code, Cursor, Aider, or any OpenAI/Anthropic-compatible client at that URL. Run your usual workload, then:

```bash
openbundle report
```

```text
OpenBundle session  (n=20 requests, this machine, last hour)
                 before     after      delta
prompt tokens    184,220    147,380    -20%
completion tok     8,102      6,480    -20%
est. cost         $2.41      $1.93     -20%
p50 latency        2.8s       2.2s     -21%
cache hit rate                20%
layers wired     cache (first-party) · compression (LLMLingua-2) · routing (first-party)
advisory         memory not applied — Mem0 ranked #1, install it yourself: pip install openbundle[mem0]
pricing          claude-sonnet-4-6, verified 2026-09-09
```

That's a real session, not a benchmark. `openbundle off` and run it again — same numbers, minus the delta — if you want to see it prove itself.

---

## Why

There are ~30 real, working open-source tools that make LLM usage cheaper and faster — compressors, caches, routers, guardrails — and none of them install together or agree on a config format. Most people either use one of them by hand, or use none. OpenBundle scans your traffic, picks a tested set (usually 6–12 tools out of the ~30 candidates), and runs them as one pipeline. Nothing in your repo is touched — it's a sidecar, not a patch — and `openbundle off` is a real, instant passthrough.

The thing that makes this trustworthy instead of just another wrapper: **nothing goes live because it imported successfully.** Every pick is smoke-tested against a sample of your own recent traffic first, and shown to you with a before/after, before it's turned on by default.

## Install

```bash
pip install openbundle
openbundle init      # scans, picks, smoke-checks, writes openbundle.yaml — never touches your repo
openbundle serve     # listens on http://127.0.0.1:4180
```

```bash
# Claude Code / Cline
export ANTHROPIC_BASE_URL=http://127.0.0.1:4180
```

```python
# OpenAI SDK / Cursor-compatible
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:4180/v1", api_key="unused")
```

```bash
openbundle on | off      # flip the overlay — same URL, repo untouched either way
openbundle check         # re-run the smoke-check against fresh samples
openbundle config        # exactly what's wrapped, what's advisory, what was rejected and why
openbundle uninstall      # --yes to skip the prompt
```

Docker (loopback-only by default):

```bash
docker run --rm -p 127.0.0.1:4180:4180 -e ANTHROPIC_API_KEY -e OPENAI_API_KEY openbundle
```

## How it works

```text
client → cache → compress? → route → guardrails → provider → JSON retry → sample eval
              │ hit
              └── SSE or JSON replay
```

1. **Scan** a sample of your real traffic — long system prompts, repeated multi-turn sessions, etc.
2. **Pick** the top candidate per category (cache, compression, routing, guardrails, structured output); fall back to the next one on install failure or conflict. One pick per category — chaining three compressors degrades quality, it doesn't compound savings.
3. **Smoke-check** each pick against your own recent requests before it goes live by default: tokens, latency, cost, and a pass/fail quality check. A tool that imports fine but quietly degrades answers gets caught here, not in production.
4. **Run** the pipeline on live traffic. Evaluation is sampled and async — it never sits on the request path.
5. **Report** real, measured deltas from your own sessions — `openbundle report`, not a marketing number.

**Memory is different, on purpose.** Mem0, Supermemory, and friends are scanned, ranked, and smoke-checked exactly like everything else — but never auto-enabled. Memory persists across your whole session, so a bad pick doesn't degrade one response, it can quietly poison a session before anyone notices. OpenBundle tells you the best candidate and gives you the install command; you wire it into your own code when you decide to. Quantization and local serving get the same treatment for a different reason — see [Structurally out of scope](#structurally-out-of-scope).

## The catalog

<!-- CATALOG:START -->
**66 open-source tools tracked across 17 categories** — 30 wrap-eligible (can run in the proxy), 6 advisory-only (memory), 30 catalog-only (structurally can't run in a proxy — see below). **7 have a real, wired adapter today**; the rest are catalogued with license and install info, open for a PR to wire in next. Full table with links: [CATALOG.md](CATALOG.md) · credits: [CREDITS.md](CREDITS.md).
<!-- CATALOG:END -->

| Category | Wired today | Also catalogued |
|---|---|---|
| Cache | first-party exact-hash | GPTCache, LMCache |
| Compression | LLMLingua-2 | LLMLingua, Selective Context, AutoCompressor, PCToolkit, RECOMP, SecurityLingua |
| Routing | first-party prefix router | LiteLLM, OpenRouter, RouteLLM |
| Guardrails | first-party input fail-open | Guardrails AI, LLM Guard, NeMo Guardrails, Rebuff |
| Structured output | first-party JSON validate-retry | Instructor, PydanticAI, BAML, Mirascope |
| Evaluation (sampled) | first-party length/format check | promptfoo, DeepEval, RAGAS, TruLens, OpenBench |
| **Memory** (advisory only) | — | Mem0, Supermemory, Letta, Zep, LangMem, Cognee |

## Structurally out of scope

Quantization, local inference engines (vLLM, llama.cpp, SGLang…), token-level constrained decoding, vector databases, fine-tuning, and agent orchestration frameworks can't run inside a request/response proxy — they need the model weights or the inference loop itself, which a proxy in front of a remote API never touches. They're catalogued with install links, never claimed as integrated. Full list: [CATALOG.md](CATALOG.md#structurally-out-of-scope).

## Not another AI gateway

Portkey, LiteLLM Proxy, Bifrost, and TrueFoundry sit in the same spot on the wire — this is a crowded, legitimate category and the comparison is fair to ask for:

| | OpenBundle | Typical AI gateway |
|---|---|---|
| License | Fully open source (MIT) | Commercial or open-core |
| Runs where | Your machine only, no backend | Often a hosted control plane |
| Compression as a pipeline stage | Yes | Rarely |
| Before a pick goes live | Smoke-checked on your own traffic | Usually just "enable the feature" |
| Memory | Advisory, never auto-applied | Usually not addressed at all |
| Attribution | Every active tool named, every output | Varies |

Point solutions — LLMLingua, RouteLLM, GPTCache — aren't competitors, they're candidate adapters.

## Where the numbers come from

Two ranges, not one ceiling:

| Claim | Includes | Does not include |
|---|---|---|
| Out of the box | Cache + compression (~20× on paper, less on real traffic) + routing/guardrails | Memory, quantization |
| If you add memory / quantized serving yourself | Mem0 ~6–8× memory; quantization ~4× VRAM | The default `pip install` |
| **`openbundle report`** | **What actually happened on your machine** | **A marketing multiple** |

Naively multiplying every published number produces a fake thousands-of-x figure — we don't cite that. `openbundle report` is the only number we'll stand behind for your setup.

## Security and data

- Binds `127.0.0.1` only; `--expose` is required (and warns) to bind wider.
- `~/.openbundle/samples.jsonl` stores a local, size-capped sample of recent prompts for smoke-checking. Never transmitted anywhere. Disable with `OPENBUNDLE_NO_SAMPLES=1`; purge with `openbundle uninstall`.
- Provider errors and disconnects are forwarded as-is; failed turns are never cached.
- No virtual keys, no multi-tenant auth — this is a single-user local overlay, not an org-wide gateway.

## License

[MIT](LICENSE)