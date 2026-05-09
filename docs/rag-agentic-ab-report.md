# Agentic RAG A/B Report

## Summary

- Generated at: `2026-05-09T04:21:27.833758+00:00`
- Datasets: `D:\Projects\agent-infra-study\UEAgentBackend\backend\tests\eval\rag_project_qa_dataset.jsonl, D:\Projects\agent-infra-study\UEAgentBackend\backend\tests\eval\rag_ue_knowledge_dataset.jsonl, D:\Projects\agent-infra-study\UEAgentBackend\backend\tests\eval\rag_agentic_ab_dataset.jsonl`
- Source paths: `./README.md, ./docs, ./knowledge`
- Top K: `4`

| Metric | Baseline RAG | Agentic RAG | Delta |
| --- | ---: | ---: | ---: |
| `recall_at_k` | 0.7727 | 0.8182 | 0.0455 |
| `precision_at_k` | 0.2045 | 0.2273 | 0.0228 |
| `precision_at_retrieved` | 0.4773 | 0.5076 | 0.0303 |
| `labeled_precision_ceiling` | 0.3182 | 0.3182 | 0.0000 |
| `normalized_precision_at_k` | 0.7727 | 0.8182 | 0.0455 |
| `hit_at_k` | 0.8182 | 0.9091 | 0.0909 |
| `top1_accuracy` | 0.7273 | 0.7273 | 0.0000 |
| `mrr` | 0.7727 | 0.8030 | 0.0303 |
| `ndcg_at_k` | 0.7624 | 0.7903 | 0.0279 |
| `route_accuracy` | 1.0000 | 1.0000 | 0.0000 |
| `language_accuracy` | 1.0000 | 1.0000 | 0.0000 |
| `citation_coverage` | 0.9091 | 0.9091 | 0.0000 |
| `low_confidence_ratio` | 0.0909 | 0.0909 | 0.0000 |
| `no_result_ratio` | 0.1818 | 0.0909 | -0.0909 |

## Cases

| Case | Hit Delta | Top1 Delta | MRR Delta | Agentic Round | Rewrite Used | Selected Query |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `dual-views-zh` | 0.0000 | 0.0000 | 0.0000 | 1 | False | 请说明 user_view debug_view 职责区别。 |
| `language-policy-zh` | 0.0000 | 0.0000 | 0.0000 | 1 | False | 请说明 locale final_output_language language_source editor_locale 语言策略。 |
| `code-review-ui-zh` | 0.0000 | 0.0000 | 0.0000 | 1 | False | Code Review user_view blocks llm_analysis 高亮按钮应该展示哪些字段？ |
| `backend-guide-kb-settings-zh` | 0.0000 | 0.0000 | 0.0000 | 1 | False | 请说明 KB_SOURCE_PATHS kb_chunk_size chunk sizing 配置。 |
| `ue-gas-zh` | 0.0000 | 0.0000 | 0.0000 | 2 | True | GAS技能系统是什么，核心类有哪些？ Gameplay Ability System AbilitySystemComponent AttributeSet GameplayEffect GameplayTag |
| `ue-threading-zh` | 0.0000 | 0.0000 | 0.0000 | 2 | True | UE多线程怎么做，AsyncTask 和 FRunnable 怎么选？ FRunnable AsyncTask TaskGraph GameThread ParallelFor thread safety |
| `ue-reflection-zh` | 0.0000 | 0.0000 | 0.0000 | 1 | False | UE反射宏怎么选，UCLASS USTRUCT UPROPERTY UFUNCTION 有什么区别？ |
| `ue-http-zh` | 0.0000 | 0.0000 | 0.0000 | 1 | False | HTTP请求怎么写，UE C++ 里需要哪些模块依赖？ |
| `agentic-enhanced-input-synonym` | 0.0000 | 0.0000 | 0.0000 | 1 | True | 角色输入绑定怎么写，PlayerCharacter 需要哪些类？ |
| `agentic-websocket-long-connection` | 0.0000 | 0.0000 | 0.0000 | 2 | True | 游戏里长连接客户端怎么做，断线要注意什么？ WebSockets IWebSocket GameInstanceSubsystem connect onmessage onclosed |
| `agentic-gas-attribute-synonym` | 1.0000 | 0.0000 | 0.3333 | 2 | True | 属性集和技能组件怎么接，属性变化怎么同步？ Gameplay Ability System AbilitySystemComponent AttributeSet GameplayEffect GameplayTag |

## Interpretation

- Positive deltas mean Agentic RAG improved retrieval for the labeled dataset.
- Zero deltas with stable quality are still useful: the refinement layer did not regress existing retrieval.
- If a case shows `rewrite_used=True`, the second retrieval round was exercised.
- This report is local/offline and is intentionally not a production A/B platform.
