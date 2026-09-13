<p align="center">
  <img src="openbundlelogo.png" alt="OpenBundle" width="520">
</p>

<p align="center">
  <strong>The compatibility layer for open-source AI optimization tools — auto-selects, wires, and shows before/after for the ones that work together.</strong><br>
  Point Claude Code, Cursor, or any OpenAI/Anthropic client at localhost.<br>
  OpenBundle stacks the right wrap-eligible tools and shows a before/after.
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
  <a href="#the-catalog">Catalog</a> ·
  <a href="#where-these-numbers-come-from">Numbers</a> ·
  <a href="#security-defaults">Security</a>
</p>

### Out of the box (auto wrap)

Cache + compression + routing + input guardrails + structured JSON retry + sampled eval. No memory. No quantization. The paper-range this wrap set can honestly claim is **prompt compression up to ~20×** ([LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)](https://github.com/microsoft/LLMLingua)) plus exact-hash cache hits and prefix routing. That is the default install ceiling.

### If you add memory and/or quantization yourself

[Mem0 (github.com/mem0ai/mem0, Apache-2.0)](https://github.com/mem0ai/mem0) reports ~90–99% context reduction (about **6–8×** less memory on their benches). Quantization / local serving can add ~4× VRAM headroom. Combined **15–40×** figures are contingent on those **advisory / native** adds — they are not what `pip install openbundle` turns on.

Your number is `openbundle report` (and `openbundle check`) on this machine’s traffic. That is the only figure we treat as true for you.

```text
OpenBundle session  (n=20 requests)
                 before     after      delta
prompt tokens    184,220    147,380    -20%
completion tok     8,102      6,480    -20%
est. cost        $2.41      $1.93      -20%
p50 latency      2.8s       2.2s       -21%
cache hit rate              20%
layers           OpenBundle exact-hash cache (first-party, MIT)
advisory         memory not applied (Mem0 (github.com/mem0ai/mem0, Apache-2.0))
pricing          claude-sonnet-4-6 as of 2026-09-09
```

Cold start is cache-only until a few requests are logged and you run `openbundle check`. Pricing rows die after 30 days (`n/a`, not a quiet wrong dollar).

Off is a real off: `openbundle off` writes `~/.openbundle/overlay.yaml`. Same repo, same `ANTHROPIC_BASE_URL`, requests passthrough. That is the proof, not the product.

## Install

```bash
pip install openbundle
```

## Quick start

```bash
openbundle init          # resolve wrap-eligible tools, write openbundle.yaml, regenerate CREDITS.md
openbundle serve
```

`init` is the only setup step. It does not patch a git repo. It writes a sidecar `openbundle.yaml` and names every wrap pick. Memory stays advisory. `--core-only` keeps extras off even if they are installed.

```bash
openbundle on            # overlay on — same attach URL; repo not touched
openbundle off           # overlay off — passthrough; repo not touched
openbundle check         # smoke-check wrap extras against local samples
openbundle config        # wrap vs advisory vs rejected, with specific reasons
```

To take it off this machine:

```bash
openbundle uninstall          # lists configs, cache, extras; asks first
openbundle uninstall --yes    # no prompt
openbundle update             # check PyPI; install if newer
openbundle update --check     # report only
```

That deletes `openbundle.yaml`, `~/.openbundle` (cache, sessions, `overlay.yaml`, `samples.jsonl`), pip packages OpenBundle installed ([LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)](https://github.com/microsoft/LLMLingua)), and `openbundle` itself. It does not edit your repo. Unset `ANTHROPIC_BASE_URL` afterward if you pointed a client at localhost.

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
- **Wrap-eligible stack** — exact-hash cache, optional [LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)](https://github.com/microsoft/LLMLingua), prefix router, input guardrails, JSON validate-and-retry, sampled eval. One pick per category.
- **Memory is advisory** — [Mem0 (github.com/mem0ai/mem0, Apache-2.0)](https://github.com/mem0ai/mem0) is ranked and credited, never auto-enabled. Add it in your own code.
- **Smoke-check before extras go live** — compression does not go live because it imported. Fail → skip the category.
- **Fail-open layers** — if a wrap adapter errors, the original request still goes to the provider.
- **SSE-correct replay** — cache hits on `stream: true` replay Anthropic/OpenAI events, including tool-use deltas.
- **Dated pricing** — `est. cost` uses [`src/openbundle/kb/pricing.yaml`](src/openbundle/kb/pricing.yaml) with `last_verified`. Stale or unknown → `n/a`.

## How it works

Integration is the product, not a directory.

1. Request arrives (OpenAI `/v1/chat/completions` or Anthropic `/v1/messages`).
2. [OpenBundle exact-hash cache (first-party, MIT)](CREDITS.md) on the **original** messages.
3. Optional [LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)](https://github.com/microsoft/LLMLingua) on a miss (never tools or `cache_control` blocks).
4. Prefix router sends `claude*` to Anthropic and `gpt*` / `o*` to OpenAI.
5. Input guardrails clip oversize prompts (fail-open).
6. Provider call; if `response_format` JSON is invalid, one retry.
7. Sampled eval writes a length/format pass/fail to the session log — not on the blocking path.
8. `openbundle report` prints tokens, latency, dated cost, and that memory was not applied.

```text
client  →  cache  →  compress?  →  route  →  guardrails  →  provider  →  JSON retry  →  sample eval
              │ hit
              └── SSE or JSON replay
```

Memory is never in this path.

## The catalog

<!-- CATALOG:START -->
OpenBundle tracks **66** open-source tools across **17** categories (30 wrap-eligible, 6 advisory, 30 catalog-only). **7** have a wired adapter today; the rest are catalogued, licensed, and ready to be adapted next — see [CREDITS.md](CREDITS.md) and open an issue/PR to help wire one in.

### Wrap-eligible (proxy can run these)

#### Cache

| Tool | License | Status |
|---|---|---|
| OpenBundle exact-hash cache | MIT | active in v2 (wired) |
| [GPTCache](https://github.com/zilliztech/GPTCache) | MIT | mapped — not wired yet |
| [LMCache](https://github.com/LMCache/LMCache) | Apache-2.0 | mapped — not wired yet |

#### Compression

| Tool | License | Status |
|---|---|---|
| [LLMLingua-2](https://github.com/microsoft/LLMLingua) | MIT | active in v2 (wired) |
| [AutoCompressor](https://github.com/princeton-nlp/AutoCompressors) | MIT | mapped — not wired yet |
| [LLMLingua / LongLLMLingua](https://github.com/microsoft/LLMLingua) | MIT | mapped — not wired yet |
| [PCToolkit](https://github.com/3DAgentWorld/Toolkit-for-Prompt-Compression) | MIT | mapped — not wired yet |
| [RECOMP](https://github.com/stanford-futuredata/RECOMP) | MIT | mapped — not wired yet |
| [SecurityLingua](https://github.com/microsoft/LLMLingua) | MIT | mapped — not wired yet |
| [Selective Context](https://github.com/liyucheng09/Selective_Context) | MIT | mapped — not wired yet |

#### Routing

| Tool | License | Status |
|---|---|---|
| OpenBundle prefix router | MIT | active in v2 (wired) |
| [LiteLLM](https://github.com/BerriAI/litellm) | MIT | mapped — not wired yet |
| [OpenRouter](https://github.com/OpenRouterTeam/openrouter) | MIT | mapped — not wired yet |
| [RouteLLM](https://github.com/lm-sys/RouteLLM) | MIT | mapped — not wired yet |

#### Guardrails

| Tool | License | Status |
|---|---|---|
| OpenBundle input guardrails | MIT | active in v2 (wired) |
| [Guardrails AI](https://github.com/guardrails-ai/guardrails) | Apache-2.0 | mapped — not wired yet |
| [LLM Guard](https://github.com/protectai/llm-guard) | MIT | mapped — not wired yet |
| [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails) | Apache-2.0 | mapped — not wired yet |
| [Rebuff](https://github.com/protectai/rebuff) | Apache-2.0 | mapped — not wired yet |
| [SecurityLingua](https://github.com/microsoft/LLMLingua) | MIT | mapped — not wired yet |

#### Evaluation

| Tool | License | Status |
|---|---|---|
| OpenBundle sample eval | MIT | active in v2 (wired) |
| [DeepEval](https://github.com/confident-ai/deepeval) | Apache-2.0 | mapped — not wired yet |
| [OpenBench](https://github.com/groq/openbench) | MIT | mapped — not wired yet |
| [promptfoo](https://github.com/promptfoo/promptfoo) | MIT | mapped — not wired yet |
| [RAGAS](https://github.com/explodinggradients/ragas) | Apache-2.0 | mapped — not wired yet |
| [TruLens](https://github.com/truera/trulens) | MIT | mapped — not wired yet |

#### Structured output

| Tool | License | Status |
|---|---|---|
| OpenBundle JSON schema retry | MIT | active in v2 (wired) |
| [BAML](https://github.com/BoundaryML/baml) | Apache-2.0 | mapped — not wired yet |
| [Instructor](https://github.com/instructor-ai/instructor) | MIT | mapped — not wired yet |
| [Mirascope](https://github.com/Mirascope/mirascope) | MIT | mapped — not wired yet |
| [PydanticAI](https://github.com/pydantic/pydantic-ai) | MIT | mapped — not wired yet |

#### RAG

| Tool | License | Status |
|---|---|---|
| [RECOMP](https://github.com/stanford-futuredata/RECOMP) | MIT | mapped — not wired yet |

### Advisory only (never auto-enabled)

#### Memory (advisory)

| Tool | License | Status |
|---|---|---|
| [Mem0](https://github.com/mem0ai/mem0) | Apache-2.0 | active in v2 (wired) |
| [Cognee](https://github.com/topoteretes/cognee) | Apache-2.0 | mapped — not wired yet |
| [LangMem](https://github.com/langchain-ai/langmem) | MIT | mapped — not wired yet |
| [Letta (MemGPT)](https://github.com/letta-ai/letta) | Apache-2.0 | mapped — not wired yet |
| [Supermemory](https://github.com/supermemoryai/supermemory) | AGPL-3.0 | mapped — not wired yet |
| [Zep](https://github.com/getzep/zep) | Apache-2.0 | mapped — not wired yet |

### Structurally out of scope (not wireable into a proxy)

#### Cache

| Tool | License | Status |
|---|---|---|
| [SGLang](https://github.com/sgl-project/sglang) | Apache-2.0 | mapped — not wired yet |
| [vLLM](https://github.com/vllm-project/vllm) | Apache-2.0 | mapped — not wired yet |

#### Structured output

| Tool | License | Status |
|---|---|---|
| [Guidance](https://github.com/guidance-ai/guidance) | MIT | mapped — not wired yet |
| [Jsonformer](https://github.com/1rgs/jsonformer) | MIT | mapped — not wired yet |
| [LM Format Enforcer](https://github.com/noamgat/lm-format-enforcer) | MIT | mapped — not wired yet |
| [Outlines](https://github.com/dottxt-ai/outlines) | Apache-2.0 | mapped — not wired yet |
| [XGrammar](https://github.com/mlc-ai/xgrammar) | Apache-2.0 | mapped — not wired yet |

#### Attention

| Tool | License | Status |
|---|---|---|
| [FlashAttention](https://github.com/Dao-AILab/flash-attention) | BSD-3-Clause | mapped — not wired yet |
| [MInference](https://github.com/microsoft/MInference) | MIT | mapped — not wired yet |

#### Coding-agent tools

| Tool | License | Status |
|---|---|---|
| CacheAligner | unknown | mapped — not wired yet |
| Caveman | unknown | mapped — not wired yet |
| Graphify | unknown | mapped — not wired yet |
| [Headroom](https://github.com/headroomhq/headroom) | unknown | mapped — not wired yet |

#### Fine-tuning

| Tool | License | Status |
|---|---|---|
| [PEFT](https://github.com/huggingface/peft) | Apache-2.0 | mapped — not wired yet |
| [Unsloth](https://github.com/unslothai/unsloth) | Apache-2.0 | mapped — not wired yet |

#### Observability

| Tool | License | Status |
|---|---|---|
| [Langfuse](https://github.com/langfuse/langfuse) | MIT | mapped — not wired yet |

#### Orchestration

| Tool | License | Status |
|---|---|---|
| [LangChain](https://github.com/langchain-ai/langchain) | MIT | mapped — not wired yet |
| [LangGraph](https://github.com/langchain-ai/langgraph) | MIT | mapped — not wired yet |
| [LlamaIndex](https://github.com/run-llama/llama_index) | MIT | mapped — not wired yet |

#### Prompt optimization

| Tool | License | Status |
|---|---|---|
| [DSPy](https://github.com/stanfordnlp/dspy) | MIT | mapped — not wired yet |

#### Quantization

| Tool | License | Status |
|---|---|---|
| [AutoAWQ](https://github.com/casper-hansen/AutoAWQ) | MIT | mapped — not wired yet |
| [AutoGPTQ](https://github.com/AutoGPTQ/AutoGPTQ) | MIT | mapped — not wired yet |
| [bitsandbytes](https://github.com/bitsandbytes-foundation/bitsandbytes) | MIT | mapped — not wired yet |
| [GGUF / llama.cpp quantization](https://github.com/ggml-org/llama.cpp) | MIT | mapped — not wired yet |

#### RAG

| Tool | License | Status |
|---|---|---|
| [Chroma](https://github.com/chroma-core/chroma) | Apache-2.0 | mapped — not wired yet |
| [LlamaIndex](https://github.com/run-llama/llama_index) | MIT | mapped — not wired yet |
| [Qdrant](https://github.com/qdrant/qdrant) | Apache-2.0 | mapped — not wired yet |

#### Serving

| Tool | License | Status |
|---|---|---|
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | MIT | mapped — not wired yet |
| [Ollama](https://github.com/ollama/ollama) | MIT | mapped — not wired yet |
| [SGLang](https://github.com/sgl-project/sglang) | Apache-2.0 | mapped — not wired yet |
| [vLLM](https://github.com/vllm-project/vllm) | Apache-2.0 | mapped — not wired yet |

#### Speculative decoding

| Tool | License | Status |
|---|---|---|
| [EAGLE-2](https://github.com/SafeAILab/EAGLE) | Apache-2.0 | mapped — not wired yet |
| [Medusa](https://github.com/FasterDecoding/Medusa) | MIT | mapped — not wired yet |
<!-- CATALOG:END -->

## Security defaults

- Binds **`127.0.0.1` only**. `--expose` (or `OPENBUNDLE_EXPOSE=1`) is required for `0.0.0.0`, and prints a warning that provider keys on this box are reachable on the LAN.
- Incoming `Authorization` / `x-api-key` is not an auth system. Keys come from `openbundle.yaml` / env. No virtual keys, no multi-tenant.
- Provider 429 / 5xx / mid-stream disconnects are forwarded as the provider sent them. Failed turns are not cached.
- `layers.cache.semantic: true` is **off** by default. A similar-but-wrong cache hit is a correctness bug.

**Sample log (`~/.openbundle/samples.jsonl`).** After a few overlay requests, OpenBundle keeps a local, size-capped, rotated copy of recent prompts so `openbundle check` can replay wrap candidates vs passthrough. The file is **local-only** — never sent to OpenBundle or any third party. It is used only for on-box smoke-check. Prompts can include secrets. A security-conscious user can disable sampling with `OPENBUNDLE_NO_SAMPLES=1`, and can purge the file with `openbundle uninstall` or by deleting `~/.openbundle/samples.jsonl`.

Off: `openbundle off` (writes `~/.openbundle/overlay.yaml`) or `OPENBUNDLE_ENABLED=false` or `--passthrough`. Nothing in your source to undo. `uninstall` removes the sidecar from the machine. Unset `ANTHROPIC_BASE_URL` to leave localhost.

## Add a layer

Compression extra, after traffic exists:

```bash
pip install openbundle[llmlingua]    # LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)
openbundle check                     # smoke-check on local samples, then enable if it passes
```

Memory stays advisory. Install it for your own code; OpenBundle will not put it on the live path:

```bash
pip install openbundle[mem0]         # Mem0 (github.com/mem0ai/mem0, Apache-2.0)
# add Mem0 in your application — not via openbundle.yaml
```

[LLMLingua-2 (github.com/microsoft/LLMLingua, MIT)](https://github.com/microsoft/LLMLingua) will not silently rewrite prompts with a heuristic, and will not go live on “it imported.”

## Not Portkey / not LiteLLM Proxy

Portkey and LiteLLM Proxy are gateways: keys, routing, virtual orgs. OpenBundle is a **localhost optimization overlay**. It does not edit your repo, does not invent a control plane, and only auto-wraps the stack that can go live after a smoke-check. Memory and quantization stay yours to add natively.

## Where these numbers come from

Two paper-range blocks — not one caveated ceiling.

| Claim | What it includes | What it is not |
|---|---|---|
| Out-of-box wrap | Cache + LLMLingua-2 (up to ~20× fewer prompt tokens) + routing / guardrails / structured / sampled eval | Memory, quantization, or a stacked 15–40× |
| If you add memory / quant | Mem0 ~90–99% context / ~6–8× memory; quant ~4× VRAM | The default `pip install` |
| Live (`openbundle report`) | Measured tokens, latency, dated cost on this traffic | A marketing multiple |

Naively multiplying every published number produces a fake thousands-of-x figure. We do not cite that as the install. Re-validate with `openbundle report`.

Cost dollars track [`pricing.yaml`](src/openbundle/kb/pricing.yaml) `last_verified`, not an undated vendor scrape.

## Config

`openbundle init` writes `openbundle.yaml`, turns the overlay on in `~/.openbundle/overlay.yaml`, and regenerates [CREDITS.md](CREDITS.md). See [`openbundle.yaml.example`](openbundle.yaml.example).

```bash
openbundle doctor    # keys, extras, per-layer /health, stale prices
openbundle config    # wrap vs advisory vs rejected (specific reasons)
openbundle on | off  # overlay file; env OPENBUNDLE_ENABLED wins and is announced
```

## License

[MIT](LICENSE)
