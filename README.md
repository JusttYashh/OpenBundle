<p align="center">
  <img src="openbundlelogo.png" alt="OpenBundle" width="520">
</p>

<p align="center">
  <strong>The compatibility layer for open source AI optimization tools.</strong><br>
  Point Claude Code, Cursor, or any OpenAI/Anthropic client at localhost.<br>
  OpenBundle stacks the right tools and shows a before/after.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square" alt="Python 3.11+"></a>
  <a href=".github/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/openbundle/openbundle/ci.yml?branch=main&style=flat-square" alt="CI"></a>
</p>

<p align="center">
  <a href="#install">Install</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#where-these-numbers-come-from">Numbers</a> ·
  <a href="#security-defaults">Security</a>
</p>

```text
OpenBundle session  (n=20 requests)
                 before     after      delta
prompt tokens    184,220    147,380    -20%
completion tok     8,102      6,480    -20%
est. cost        $2.41      $1.93      -20%
p50 latency      2.8s       2.2s       -21%
cache hit rate              20%
layers           OpenBundle exact-hash cache (first-party, MIT)
pricing          claude-sonnet-4-6 as of 2026-09-09
```

Default install is [OpenBundle exact-hash cache (first-party, MIT)](CREDITS.md) only. The table is `openbundle report` — measured session tokens, not a paper multiple. Pricing rows die after 30 days (`n/a`, not a quiet wrong dollar).

Off is a real off: run `openbundle` to flip `enabled` in `openbundle.yaml`, same repo, same `ANTHROPIC_BASE_URL`, and watch the numbers change back. That is the proof, not the product.

## Install

```bash
pip install openbundle
```

## Quick start

```bash
openbundle init          # resolve compatible tools, write openbundle.yaml, regenerate CREDITS.md
openbundle serve
```

`init` is the only setup step. It does not patch a git repo. It writes a sidecar `openbundle.yaml` (`enabled: true`) and names every activated tool. `--core-only` keeps extras off even if they are installed.

```bash
openbundle               # flip overlay on/off (passthrough; source untouched)
openbundle config        # named tools, licenses, why a candidate was skipped
openbundle config set memory off
```

To take it off this machine:

```bash
openbundle uninstall          # lists configs, cache, extras; asks first
openbundle uninstall --yes    # no prompt
openbundle update             # check PyPI; install if newer
openbundle update --check     # report only
```

That deletes `openbundle.yaml`, `~/.openbundle` (cache/sessions), pip packages OpenBundle installed ([Mem0 (github.com/mem0ai/mem0, Apache-2.0)](https://github.com/mem0ai/mem0) / [LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)](https://github.com/microsoft/LLMLingua)), and `openbundle` itself. It does not edit your repo. Unset `ANTHROPIC_BASE_URL` afterward if you pointed a client at localhost.

Listens on `http://127.0.0.1:4180`.

```bash
# Claude Code / Cline
export ANTHROPIC_BASE_URL=http://127.0.0.1:4180
```

```python
# OpenAI SDK / Cursor-compatible
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:4180/v1", api_key="unused")
```

Then run your usual workload and:

```bash
openbundle report
```

Docker (publish **host loopback only**):

```bash
docker build -t openbundle .
docker run --rm -p 127.0.0.1:4180:4180 \
  -e ANTHROPIC_API_KEY -e OPENAI_API_KEY \
  openbundle
```

## Highlights

- **Localhost proxy** — one `base_url` change; Claude Code, Cursor, Aider, and OpenAI SDKs all attach.
- **OpenBundle exact-hash cache (first-party, MIT) by default** — identical prompts replay as protocol-correct SSE, not a JSON dump. Semantic similarity is opt-in because it can be wrong.
- **Fail-open layers** — if [Mem0 (github.com/mem0ai/mem0, Apache-2.0)](https://github.com/mem0ai/mem0) or [LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)](https://github.com/microsoft/LLMLingua) errors, the original request still goes to the provider.
- **SSE-correct replay** — cache hits on `stream: true` replay Anthropic/OpenAI events, including tool-use deltas.
- **Dated pricing** — `est. cost` uses [`src/openbundle/kb/pricing.yaml`](src/openbundle/kb/pricing.yaml) with `last_verified`. Stale or unknown → `n/a`.
- **Optional extras** — [Mem0 (github.com/mem0ai/mem0, Apache-2.0)](https://github.com/mem0ai/mem0) and [LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)](https://github.com/microsoft/LLMLingua) when those extras are already installed. See [CREDITS.md](CREDITS.md).

## How it works

Integration is the product, not a directory.

1. Request arrives (OpenAI `/v1/chat/completions` or Anthropic `/v1/messages`).
2. [OpenBundle exact-hash cache (first-party, MIT)](CREDITS.md) on the **original** messages.
3. Optional [Mem0 (github.com/mem0ai/mem0, Apache-2.0)](https://github.com/mem0ai/mem0) shrinks history / retrieved context.
4. Optional [LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)](https://github.com/microsoft/LLMLingua) on what is left (never tools or `cache_control` blocks).
5. Forward to the provider. Errors pass through unchanged.
6. `openbundle report` prints tokens, latency, and dated cost.

```text
client  →  OpenBundle exact-hash cache  →  Mem0?  →  LLMLingua-2?  →  Anthropic / OpenAI
              │ hit
              └── SSE or JSON replay
```

## Security defaults

- Binds **`127.0.0.1` only**. `--expose` (or `OPENBUNDLE_EXPOSE=1`) is required for `0.0.0.0`, and prints a warning that provider keys on this box are reachable on the LAN.
- Incoming `Authorization` / `x-api-key` is not an auth system. Keys come from `openbundle.yaml` / env. No virtual keys, no multi-tenant.
- Provider 429 / 5xx / mid-stream disconnects are forwarded as the provider sent them. Failed turns are not cached.
- `layers.cache.semantic: true` is **off** by default. A similar-but-wrong cache hit is a correctness bug.

Off: `openbundle` (flips `enabled`) or `OPENBUNDLE_ENABLED=false` or `--passthrough`. Nothing in your source to undo. `uninstall` removes the sidecar from the machine. Unset `ANTHROPIC_BASE_URL` to leave localhost.

## Add a layer

After the core is working:

```bash
pip install openbundle[mem0]         # Mem0 (github.com/mem0ai/mem0, Apache-2.0)
pip install openbundle[llmlingua]    # LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)
openbundle config set memory mem0
openbundle config set compress llmlingua2
```

[Mem0 (github.com/mem0ai/mem0, Apache-2.0)](https://github.com/mem0ai/mem0) extract defaults (every 3 turns / 15s / 4 per minute) exist so it cannot add an LLM call on every turn. Raise them and `openbundle report` will show `memory_extract_tokens`.

[LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)](https://github.com/microsoft/LLMLingua) is off until the extra is installed. It will not silently rewrite prompts with a heuristic.

## Not LiteLLM / not OmniRoute

LiteLLM routes providers. OmniRoute stacks free tiers and routing. OpenBundle bundles **optimization tools that already exist** — cache, memory, compression — and makes them work together on the wire.

## Where these numbers come from

The README table is a **measured** default-core session (exact-hash repeats). Stacked 15–40× figures in the broader pitch are discounted **paper ranges** from independent tools, not OpenBundle’s guarantee:

| Layer | Reported gain | Why we do not multiply it in |
|---|---|---|
| [LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)](https://github.com/microsoft/LLMLingua) | up to 20× fewer prompt tokens | Overlaps with memory-layer shrinkage |
| [Mem0 (github.com/mem0ai/mem0, Apache-2.0)](https://github.com/mem0ai/mem0) | ~90–99% context reduction on their benches | Different slice than raw prompt compression, still not 20× × 10× on the same tokens |
| KV-cache / speculative / quant | 2–5× throughput, 2–3× decode, ~4× memory | Serving-side; not this proxy’s v1 path |

Naively multiplying every published number produces a fake thousands-of-x figure. We do not cite that. Re-validate with `openbundle report` on your traffic.

Cost dollars track [`pricing.yaml`](src/openbundle/kb/pricing.yaml) `last_verified`, not an undated vendor scrape.

## Config

`openbundle init` writes `openbundle.yaml` and regenerates [CREDITS.md](CREDITS.md). See [`openbundle.yaml.example`](openbundle.yaml.example).

```bash
openbundle doctor    # keys, extras, /health, stale prices
openbundle config    # why a tool was skipped (extra missing vs not wired)
```

## License

[MIT](LICENSE)
