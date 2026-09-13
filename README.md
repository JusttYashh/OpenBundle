<p align="center">
  <img src="openbundle-logo-horizontal-centered.png" alt="openbundle" width="520">
</p>

<p align="center">
  <strong>~20× fewer prompt tokens out of the box</strong><br>
  <strong>6–8× less memory</strong> on by default<br>
  Provider prompt-cache savings follow your live hit rate — see <code>openbundle report</code>
</p>

<p align="center">Your number is <code>openbundle report</code> on this traffic.</p>

<h3 align="center">One install. A local proxy that auto-wires the open-source LLM optimizations that actually help — and shows you the receipts.</h3>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square" alt="Python 3.11+"></a>
  <a href=".github/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/openbundle/openbundle/ci.yml?branch=main&style=flat-square" alt="CI"></a>
  <a href="#the-catalog"><img src="https://img.shields.io/badge/catalog-open-informational?style=flat-square" alt="catalog"></a>
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
layers wired     cache · memory · compression · routing
pricing          claude-sonnet-4-6, verified 2026-09-09
```

That's a real session, not a benchmark. `openbundle off` and run it again — same numbers, minus the delta — if you want to see it prove itself.

---

## Why

There are dozens of real, working open-source tools that make LLM usage cheaper and faster — compressors, caches, memory, routers, guardrails — and none of them install together or agree on a config format. OpenBundle scans your traffic, picks a tested set, and runs them as one pipeline. Nothing in your repo is touched — it's a sidecar, not a patch — and `openbundle off` is a real, instant passthrough.

**Nothing goes live because it imported successfully.** Every pick is smoke-tested against a sample of your own recent traffic first.

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
openbundle config        # what's on, what's coming, what you add yourself
openbundle uninstall      # --yes to skip the prompt
```

Docker (loopback-only by default):

```bash
docker run --rm -p 127.0.0.1:4180:4180 -e ANTHROPIC_API_KEY -e OPENAI_API_KEY openbundle
```

## How it works

```text
client → cache → coalesce → memory → hygiene → compress? → prompt-cache → route → guardrails → provider → JSON retry → eval
              │ hit
              └── SSE or JSON replay
```

1. **Scan** a sample of your real traffic.
2. **Pick** one tool per category; fall back on install failure or conflict.
3. **Smoke-check** each pick against your own recent requests before it goes live.
4. **Run** the pipeline. Evaluation is sampled — it never sits on the request path.
5. **Report** measured deltas — `openbundle report`, not a marketing number.

Memory is on by default (first-party sliding window; Mem0 when that extra is installed and passes smoke-check). Session hygiene drops repeated turns and stale tool output so the window you already have stays cleaner — not a bigger window. Provider prompt caching discounts stable prefixes (system prompts, tools) on later turns; the live saving is your cache hit rate.

For nightly evals or bulk jobs that can wait, we recommend the provider Batch API (about 50% off). That path has no streaming, so we never turn it on for interactive traffic.

## The catalog

<!-- CATALOG:START -->
**50 tools we ship or recommend** across **13** categories — **11** on today, 1 you add yourself (Batch API). Full table: [CATALOG.md](CATALOG.md) · credits: [CREDITS.md](CREDITS.md).
<!-- CATALOG:END -->

| Category | On today | Also queued |
|---|---|---|
| Cache | first-party exact-hash · coalesce · prompt-cache inject | GPTCache, stampede, Autocache |
| Compression | LLMLingua-2 | LLMLingua, Selective Context, AutoCompressor, PCToolkit |
| Memory | first-party summary (Mem0 when installed) | Supermemory, Letta, Zep, LangMem, Cognee |
| Context | first-party session hygiene | openai-agents-context-compaction |
| Routing | first-party prefix router | LiteLLM, OpenRouter, RouteLLM |
| Guardrails | first-party input fail-open | Guardrails AI, LLM Guard, NeMo Guardrails, Rebuff |
| Structured output | first-party JSON validate-retry | Instructor, PydanticAI, BAML, Mirascope |
| Evaluation (sampled) | first-party length/format check | promptfoo, DeepEval, RAGAS, TruLens, OpenBench |
| Batch (you add) | — | Anthropic / OpenAI Batch API — 50% off, no streaming |

## Not another AI gateway

Portkey, LiteLLM Proxy, Bifrost, and TrueFoundry sit in the same spot on the wire. Bifrost already injects prompt-cache breakpoints — that feature is table stakes among gateways now, not our only trick.

| | OpenBundle | Typical AI gateway |
|---|---|---|
| License | Fully open source (MIT) | Commercial or open-core |
| Runs where | Your machine only, no backend | Often a hosted control plane |
| Compression + memory + hygiene | Yes | Rarely stacked |
| Before a pick goes live | Smoke-checked on your own traffic | Usually just "enable the feature" |
| Attribution | Every active tool named, every output | Varies |

Point solutions — LLMLingua, RouteLLM, GPTCache — aren't competitors, they're candidate adapters.

## Where the numbers come from

| Claim | What it is |
|---|---|
| ~20× fewer prompt tokens | Compression + exact-hash cache, paper range for LLMLingua-2; real traffic is usually less |
| 6–8× memory | First-party window / Mem0 on by default |
| Provider prompt cache | Hit-rate dependent — `openbundle report`, not a static 90% |
| **`openbundle report`** | **What actually happened on your machine** |

We do not multiply those into one fake thousands-of-x figure. `openbundle report` is the only number we'll stand behind for your setup.

## Security and data

- Binds `127.0.0.1` only; `--expose` is required (and warns) to bind wider.
- `~/.openbundle/samples.jsonl` stores a local, size-capped sample of recent prompts for smoke-checking. Never transmitted anywhere. Disable with `OPENBUNDLE_NO_SAMPLES=1`; purge with `openbundle uninstall`.
- Provider errors and disconnects are forwarded as-is; failed turns are never cached.
- No virtual keys, no multi-tenant auth — this is a single-user local overlay.

## License

[MIT](LICENSE)
