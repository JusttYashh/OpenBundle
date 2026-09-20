# Catalog

OpenBundle runs **22** distinct jobs for hosted APIs, plus **5** if local inference / `--with-lynx` is detected. **8** tools are advisory (never in the live path).

## 22 jobs for hosted APIs

| Job | Tool | License | Tier |
|---|---|---|---|
| exact-hash cache | OpenBundle exact-hash cache | MIT | A |
| semantic cache | [GPTCache](https://github.com/zilliztech/GPTCache) | MIT | B |
| compress | [LLMLingua-2](https://github.com/microsoft/LLMLingua) | MIT | B |
| history prune | [Selective Context](https://github.com/liyucheng09/Selective_Context) | MIT | B |
| RAG compress | [RECOMP](https://github.com/stanford-futuredata/RECOMP) | MIT | B |
| secrets scan | [LLM Guard](https://github.com/protectai/llm-guard) | MIT | A |
| PII scan | [Microsoft Presidio](https://github.com/microsoft/presidio) | MIT | B |
| injection scan | [Rebuff](https://github.com/protectai/rebuff) | Apache-2.0 | A |
| NeMo rails | [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails) | Apache-2.0 | A |
| semantic router | [Semantic Router](https://github.com/aurelio-labs/semantic-router) | MIT | B |
| cost router | [RouteLLM](https://github.com/lm-sys/RouteLLM) | MIT | A |
| LiteLLM dispatch | [LiteLLM](https://github.com/BerriAI/litellm) | MIT | A |
| output validate | [Guardrails AI](https://github.com/guardrails-ai/guardrails) | Apache-2.0 | A |
| structured output | [Instructor](https://github.com/instructor-ai/instructor) | MIT | A |
| promptfoo | [promptfoo](https://github.com/promptfoo/promptfoo) | MIT | A |
| DeepEval | [DeepEval](https://github.com/confident-ai/deepeval) | Apache-2.0 | A |
| Opik | [Opik](https://github.com/comet-ml/opik) | Apache-2.0 | A |
| Langfuse | [Langfuse](https://github.com/langfuse/langfuse) | MIT | C |
| OpenObserve | [OpenObserve](https://github.com/openobserve/openobserve) | Apache-2.0 | C |
| OpenMeter | [OpenMeter](https://github.com/openmeterio/openmeter) | Apache-2.0 | A |
| AgentOps | [AgentOps](https://github.com/AgentOps-AI/agentops) | MIT | A |
| Agenta | [Agenta](https://github.com/Agenta-AI/agenta) | MIT | C |

## 5 more if local inference / --with-lynx

LMCache, kvcached, and KVzip are not verified to work together.
RAG faithfulness (Lynx) is conditional — not one of the 22 hosted jobs.

| Job | Tool | License |
|---|---|---|
| RAG faithfulness | [Patronus Lynx-8B](https://huggingface.co/PatronusAI/Llama-3-Patronus-Lynx-8B-Instruct) | Apache-2.0 |
| LMCache | [LMCache](https://github.com/LMCache/LMCache) | Apache-2.0 |
| kvcached | [kvcached](https://github.com/ovg-project/kvcached) | Apache-2.0 |
| KVzip | [KVzip](https://github.com/snu-mllab/KVzip) | MIT |
| DeepSpec | [DeepSpec](https://github.com/deepseek-ai/DeepSpec) | MIT |

## Advisory — not on the live path

| Tool | License |
|---|---|
| [Mem0](https://github.com/mem0ai/mem0) | Apache-2.0 |
| [Zep](https://github.com/getzep/zep) | Apache-2.0 |
| [Letta (MemGPT)](https://github.com/letta-ai/letta) | Apache-2.0 |
| [Cognee](https://github.com/topoteretes/cognee) | Apache-2.0 |
| [Supermemory](https://github.com/supermemoryai/supermemory) | AGPL-3.0 |
| [LangMem](https://github.com/langchain-ai/langmem) | MIT |
| [MemPalace](https://github.com/MemPalace/mempalace) | MIT |
| Provider Batch API | see provider |
