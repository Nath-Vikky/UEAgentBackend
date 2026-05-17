# Router Signal Eval Report

- Generated at: `2026-05-17T09:32:30.875867+00:00`
- Dataset: `D:\Projects\agent-infra-study\UEAgentBackend\backend\tests\eval\router_signal_dataset.jsonl`
- Cases: `5`
- Route accuracy: `1.0000`
- Tool accuracy: `1.0000`
- Shadow stability: `1.0000`
- Recommendation accuracy: `1.0000`
- Override applied count: `0`

## Cases

### router_signal_direct_chat_generic

- Baseline route: `direct_answer` / `None`
- Shadow route: `direct_answer` / `None`
- Recommendation: `shadow_only` `direct_answer` / `None`
- Checks: route=`True`, tool=`True`, stable=`True`, recommendation=`True`

### router_signal_project_inventory

- Baseline route: `project_qa` / `query_project_inventory`
- Shadow route: `project_qa` / `query_project_inventory`
- Recommendation: `eligible` `project_qa` / `query_project_inventory`
- Checks: route=`True`, tool=`True`, stable=`True`, recommendation=`True`

### router_signal_ue_knowledge

- Baseline route: `project_qa` / `retrieve_project_knowledge`
- Shadow route: `project_qa` / `retrieve_project_knowledge`
- Recommendation: `eligible` `project_qa` / `retrieve_project_knowledge`
- Checks: route=`True`, tool=`True`, stable=`True`, recommendation=`True`

### router_signal_explicit_project_qa

- Baseline route: `project_qa` / `None`
- Shadow route: `project_qa` / `None`
- Recommendation: `eligible` `project_qa` / `retrieve_project_knowledge`
- Checks: route=`True`, tool=`True`, stable=`True`, recommendation=`True`

### router_signal_casual_hello

- Baseline route: `direct_answer` / `None`
- Shadow route: `direct_answer` / `None`
- Recommendation: `no_signal` `None` / `None`
- Checks: route=`True`, tool=`True`, stable=`True`, recommendation=`True`
