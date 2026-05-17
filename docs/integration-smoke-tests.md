# Integration Smoke Tests

These checks are intended for a local developer machine. They verify that the
backend can complete the core UE Agent paths without requiring a live UE editor,
LLM key, embedding model, or Qdrant instance.

Start the backend first:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Set a base URL:

```powershell
$BaseUrl = "http://127.0.0.1:8000/api/v1"
```

## 0. No-UE Backend Smoke

If you want to verify the backend without launching Unreal Editor, run:

```powershell
.\.venv\Scripts\python.exe scripts\run_no_ue_live_smoke.py --output storage\artifacts\smoke\no-ue-live-smoke-latest.json
```

This script uses FastAPI `TestClient`, an isolated in-memory database, local `knowledge/`, deterministic LLM fallback, and a mock controlled Web Search result.

Pass criteria:

- `overall_ok` is `true`.
- `code_generate_enhanced_input_1` returns Enhanced Input Character code for `角色增强输入代码怎么写`.
- `code_generate_enhanced_input_2` returns Enhanced Input Character code for `角色输入增强的代码怎么写`.
- `agent_chat_web_search_tool.web_search_tool_called` is `true`.
- `agent_chat_web_search_tool.web_search_status` is `completed`.

Optional live LLM check:

```powershell
.\.venv\Scripts\python.exe scripts\run_no_ue_live_smoke.py --live-llm --output storage\artifacts\smoke\no-ue-live-smoke-live-llm.json
```

The default mode is better for regression because it proves backend tool routing and deterministic fallbacks without depending on proxy/API-key state.

PowerShell 注意：如果使用反引号换行，反引号后面不能有空格。否则后续
`-Method Post` 可能不会被解析，`Invoke-RestMethod` 会按默认 GET 请求发送，
后端就会返回 `{"detail":"Method Not Allowed"}`。排查时优先使用本文的单行
`Invoke-RestMethod "$BaseUrl/..." -Method Post ...` 写法。

## 1. Agent Chat Direct Answer

```powershell
$Body = @{
  session = @{
    session_id = "smoke_direct"
    messages = @(@{ role = "user"; content = "你好，简单介绍一下你能做什么"; language = "zh-CN" })
  }
  context = @{ project_name = "SmokeProject"; active_panel = "AgentChat" }
  runtime_options = @{ preferred_output_language = "zh-CN"; debug = $true }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod "$BaseUrl/chat/runs" -Method Post -ContentType "application/json" -Body $Body
```

Pass criteria:

- `success` is `true`.
- `user_view.blocks` is not empty.
- `debug_view.agent_decision_trace` exists.

## 2. Project QA With Inventory

Submit a minimal project inventory:

```powershell
$Inventory = @{
  project_id = "SmokeProject"
  project_name = "SmokeProject"
  assets = @(
    @{
      asset_path = "/Game/Characters/BP_Hero"
      asset_name = "BP_Hero"
      asset_type = "Blueprint"
      class_name = "Blueprint"
      parent_class = "Character"
      dependencies = @("/Game/Input/IA_Move")
      metadata = @{ owner = "smoke" }
    }
  )
  code_files = @(
    @{ path = "Source/SmokeProject/Private/HeroCharacter.cpp"; extension = ".cpp"; module = "SmokeProject" }
  )
} | ConvertTo-Json -Depth 8

Invoke-RestMethod "$BaseUrl/project-inventory/snapshot" -Method Post -ContentType "application/json" -Body $Inventory
```

Ask a current-project question:

```powershell
$Body = @{
  session = @{
    session_id = "smoke_inventory"
    messages = @(@{ role = "user"; content = "当前项目有哪些蓝图资产？"; language = "zh-CN" })
  }
  context = @{ project_name = "SmokeProject"; active_panel = "AgentChat" }
  runtime_options = @{ preferred_output_language = "zh-CN"; debug = $true }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod "$BaseUrl/chat/runs" -Method Post -ContentType "application/json" -Body $Body
```

Pass criteria:

- `assistant_message` or `user_view.blocks` mentions `BP_Hero`.
- `debug_view.tools` includes `query_project_inventory`.
- The answer should not rely only on KB/RAG for current-project facts.

## 3. Code Review

```powershell
$Body = @{
  task_type = "code_review"
  session = @{ session_id = "smoke_code_review"; messages = @() }
  context = @{ project_name = "SmokeProject"; active_panel = "CodeReview" }
  payload = @{
    files = @(
      @{
        path = "Source/SmokeProject/Private/HeroCharacter.cpp"
        content = "void AHeroCharacter::Tick(float DeltaTime) { LoadObject<UTexture2D>(nullptr, TEXT(""/Game/UI/T_Icon.T_Icon"")); }"
      }
    )
    review_focus = "UE C++ risky patterns"
  }
  runtime_options = @{ preferred_output_language = "zh-CN"; debug = $true }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod "$BaseUrl/tasks/code-review" -Method Post -ContentType "application/json" -Body $Body
```

Pass criteria:

- `data.review_scope.source_kind` is `content` or `file_path`.
- `data.review_scope.content_length` is greater than `0`.
- `data.issue_list` contains at least one issue for the sample risky code.
- `user_view.blocks` includes review summary / suggestions.
- `debug_view.tools` includes `review_ue_cpp_files`.
- If an LLM key is configured, `data.llm_analysis.status` should normally be `completed`; otherwise it should be `skipped` with a stable `reason_code`.
- If the first structured LLM review fails because the selected file is long or the model returns non-JSON text, backend will try a compact natural-language retry. In that case `data.llm_review.reason = "completed_text_fallback"` and `data.llm_review.fallback_mode = "compact_text_retry"`.
- If it is still skipped, inspect `data.review_scope.read_status/content_length/source_field` first, then `data.llm_review.reason/error/fallback_result`.

## 4. Code Generate

```powershell
$Body = @{
  task_type = "code_generate"
  session = @{ session_id = "smoke_code_generate"; messages = @() }
  context = @{ project_name = "SmokeProject"; active_panel = "CodeGenerate" }
  payload = @{
    user_query = "角色增强输入代码怎么写？"
    target_type = "ue_cpp"
    module_name = "SmokeProject"
    class_name = "SmokeHeroCharacter"
  }
  runtime_options = @{ preferred_output_language = "zh-CN"; debug = $true }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod "$BaseUrl/tasks/code-generate" -Method Post -ContentType "application/json" -Body $Body
```

Pass criteria:

- `data.generated_items` is not empty.
- Generated content references Enhanced Input concepts such as `UInputAction` or `UEnhancedInputComponent`.
- `write_policy.written_to_disk` is `false`.

## 5. Logs Analyze

```powershell
$Body = @{
  task_type = "logs_analyze"
  session = @{ session_id = "smoke_logs"; messages = @() }
  context = @{ project_name = "SmokeProject"; active_panel = "LogsAnalyze" }
  payload = @{
    source = "EditorLog"
    log_text = "LogUObjectGlobals: Warning: Failed to find object '/Game/Missing/BP_Missing.BP_Missing'\nLogWindows: Error: Fatal error!"
    user_note = "只需要分析 error 和 warning"
  }
  runtime_options = @{ preferred_output_language = "zh-CN"; debug = $true }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod "$BaseUrl/tasks/logs-analyze" -Method Post -ContentType "application/json" -Body $Body
```

Pass criteria:

- `data.findings` or `data.log_summary` exists.
- `debug_view.tools` includes `analyze_ue_log`.
- Weak KB matches may be skipped by the log retrieval quality gate.

## 6. Assets Inspect

```powershell
$Body = @{
  task_type = "assets_inspect"
  session = @{ session_id = "smoke_assets"; messages = @() }
  context = @{
    project_name = "SmokeProject"
    active_panel = "AssetsInspect"
    selected_assets = @("/Game/Characters/BP_Hero")
  }
  payload = @{
    assets = @(
      @{
        asset_path = "/Game/Characters/BP_Hero"
        asset_name = "BP_Hero"
        asset_type = "Blueprint"
        parent_class = "Character"
        dependencies = @("/Game/Input/IA_Move")
        metadata = @{ blueprint_type = "Character" }
      }
    )
    user_query = "检查命名、类型和依赖关系"
  }
  runtime_options = @{ preferred_output_language = "zh-CN"; debug = $true }
} | ConvertTo-Json -Depth 10

Invoke-RestMethod "$BaseUrl/tasks/assets-inspect" -Method Post -ContentType "application/json" -Body $Body
```

Pass criteria:

- `user_view.blocks` contains asset inspection output.
- `debug_view.tools` includes `inspect_asset_metadata`.
- LLM analysis may be marked as fallback when no LLM key is configured.

## 7. Proposal Loop

Create an editor-operation proposal:

```powershell
$Proposal = @{
  operation_type = "rename_selected_asset"
  payload = @{
    asset_path = "/Game/Characters/BP_Hero"
    new_name = "BP_PlayerHero"
  }
  reason = "Smoke test rename proposal"
  requested_by = "smoke"
} | ConvertTo-Json -Depth 8

$Created = Invoke-RestMethod "$BaseUrl/editor-operations/proposals" -Method Post -ContentType "application/json" -Body $Proposal
$Created
$ProposalId = $Created.item.proposal_id
```

Confirm it:

```powershell
$Decision = @{ decision = "confirmed"; actor = "smoke"; comment = "Approved in smoke test" } | ConvertTo-Json -Depth 4
Invoke-RestMethod "$BaseUrl/proposals/$ProposalId/decision" -Method Post -ContentType "application/json" -Body $Decision
```

Report execution result:

```powershell
$Result = @{
  proposal_id = $ProposalId
  operation_type = "rename_selected_asset"
  execution_state = "completed"
  success = $true
  executed_by = "ue_plugin_smoke"
  result = @{ old_path = "/Game/Characters/BP_Hero"; new_path = "/Game/Characters/BP_PlayerHero" }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod "$BaseUrl/editor-operations/results" -Method Post -ContentType "application/json" -Body $Result
```

Pass criteria:

- Proposal creation returns a pending/created proposal id.
- Confirmation changes the proposal state.
- Execution report is accepted without a 500 response.

## Notes

- These smoke tests are intentionally small and local.
- They do not replace `pytest`, RAG eval, hallucination eval, or UE-side manual testing.
- UE frontend changes are not required for this smoke suite. It documents existing HTTP contracts and backend fallback behavior.
