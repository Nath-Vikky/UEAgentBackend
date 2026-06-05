# Demo Checklist

This checklist helps you run a local UEAgentCraft demo with the backend and
UEAgentTool plugin.

## 1. Start The Backend

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
copy .env.example .env
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check:

```http
GET http://127.0.0.1:8000/api/v1/system/health
GET http://127.0.0.1:8000/api/v1/system/capabilities
GET http://127.0.0.1:8000/api/v1/editor-operations/capabilities
GET http://127.0.0.1:8000/api/v1/editor-operations/inspect/assets
GET http://127.0.0.1:8000/api/v1/editor-operations/inspect/asset-detail?asset_id=SM_Rock
```

## 2. Prepare The UE Plugin

Plugin repository:

```text
https://github.com/Nath-Vikky/UEAgentTool
```

Checklist:

- Enable the plugin in an Unreal project.
- Compile the plugin in Rider or Unreal Editor.
- Set backend URL to `http://127.0.0.1:8000`.
- Open the plugin panel and verify backend connection status.
- Wait for automatic Project Inventory sync, or click `Sync Inventory Now`.

Quick read-only views:

- `Show Assets`: list recent project assets from Project Inventory.
- `Show Selected Asset`: select one Content Browser asset and show its type,
  path, dependencies, referencers, settings, and properties.
- `Show Blueprint Graphs`: select one Blueprint when possible and show graph /
  node summaries.
- `Show Level Actors`: show recent loaded-level Actor summaries.
- `Show Materials`: show Material Instance parameter summaries.
- `Show Tools`: show supported editor-operation tools, read-only inspections,
  groups, and confirmation policy.
- `Show Activity`: show recent editor-operation proposals, execution states,
  and diagnostic counts.
- `Show Inventory Summary`: show compact Project Inventory counts.

All buttons above are read-only. They do not create Proposals and do not modify
assets, levels, Blueprints, Widgets, or Materials.

## 3. Run Backend-Only Smoke Checks

These checks do not launch Unreal Editor, call an LLM, or write a project.

```powershell
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m pytest tests\unit tests\contract -q
.\.venv\Scripts\python.exe scripts\run_blueprint_graph_operation_smoke.py
.\.venv\Scripts\python.exe scripts\run_editor_operation_chat_bridge_smoke.py
.\.venv\Scripts\python.exe scripts\run_editor_workflow_materialization_smoke.py
.\.venv\Scripts\python.exe scripts\run_project_inventory_chat_smoke.py
.\.venv\Scripts\python.exe scripts\run_tool_registry_readonly_smoke.py
.\.venv\Scripts\python.exe scripts\run_mcp_tcp_adapter_smoke.py
```

If the local shell cannot write smoke report files under `storage/artifacts`,
pass `--output -` to print the JSON report without writing a file.

Or run the whole deterministic demo baseline as one suite:

```powershell
.\.venv\Scripts\python.exe scripts\run_editor_demo_smoke_suite.py
```

Use `--include-child-reports` only when you need the full per-case JSON from all
child smoke scripts.

Expected:

- Blueprint graph proposal/result smoke: `17/17 passed`
- Agent Chat editor-operation smoke: `30/30 passed`
- Editor workflow materialization smoke: `9/9 passed`
- Project Inventory chat smoke: `2/2 passed`; these cases check normal Inventory
  grounding plus explicit MCP read-only route fallback through the local
  Tool Registry / Project Inventory path, and also check that `react_trace`
  includes the display-safe `validation` phase.
- Tool Registry read-only smoke: `6/6 passed`; this checks the local
  MCP-compatible read-only call path for Blueprint graph, Widget tree, Level
  Actor, Material Instance, and write-tool blocking.
- Tool Registry Proposal bridge smoke: `7/7 passed`; this simulates an
  MCP/Tool Registry client requesting Blueprint, UMG, Material, and Level Actor
  writes, verifies compact demo tool profiles such as `umg_demo`, checks the
  high-level Blueprint `editor_blueprint_add_step` alias, and confirms that the
  backend creates pending Proposals instead of executing editor writes directly.
- MCP TCP adapter smoke: `6/6 passed`; this emulates the UEAgentTool JSON-RPC
  line TCP server and checks `get_blueprint_graph`, `get_widget_tree`, allow-list
  blocking, and raw-write rejection.
- Aggregated editor demo smoke suite: `7/7 suites`, `77/77 cases`

## 4. Demo The Agent Features

Recommended order:

1. Project QA: ask a general Unreal project question and check citations or tool context.
2. Code Review: scan C++ files, select one file, run review, and open the structured result.
3. Code Generate: ask for a common UE C++ snippet, such as Enhanced Input setup.
4. Logs Analyze: paste a short error log or provide a safe log file path.
5. Assets Inspect: select one asset in Content Browser and run inspection.

Optional live TCP tool-server check:

```powershell
.\.venv\Scripts\python.exe scripts\run_live_ue_tool_server_smoke.py --host 127.0.0.1 --port 8765 --output -
```

If you want to test live read-only graph calls, pass real paths from your
project:

```powershell
.\.venv\Scripts\python.exe scripts\run_live_ue_tool_server_smoke.py --host 127.0.0.1 --port 8765 --blueprint-path /Game/Blueprints/BP_PlayerCharacter --widget-blueprint-path /Game/UI/WBP_MainHUD --output -
```

This check requires UEAgentTool's optional TCP tool server to be running. It
does not execute editor writes.

## 5. Demo Confirmed Editor Operations

Keep the first demo project disposable. The backend does not auto-save, but the
UE editor operation still changes the open project after confirmation.

Suggested low-risk demos:

- Rename one test asset.
- Duplicate one test asset to a safe `_Copy` name.
- Fix redirectors under a bounded test folder such as `/Game/AgentDemo`.
- Create one test Blueprint under `/Game/AgentDemo`.
- Add a `Print String` Blueprint node template.
- Add an `ActorBeginOverlap -> PrintString` Blueprint node chain in a test Blueprint.
- Add a `Custom Event -> PrintString` Blueprint node chain in a test Blueprint.
- Add an Enhanced Input Action event that connects `Triggered -> PrintString`.
- Compile the test Blueprint.
- Set one TextBlock text in a test Widget Blueprint.
- Duplicate one non-panel UMG widget under the same parent with a safe new name.
- Delete one non-root non-panel UMG widget from a test Widget Blueprint.
- Set one TextBlock opacity or font size through `set_umg_widget_appearance`.
- Set one Image or Border texture/material through `set_umg_widget_brush`.
- Set one HorizontalBox/VerticalBox/Overlay slot padding or alignment through `set_umg_slot_layout_v2`.
- Set one scalar or vector color parameter on a test Material Instance.
- Set one texture or static switch parameter on a test Material Instance.
- Move one named level Actor with a bounded transform delta.
- Rename or tag one level Actor through a confirmed `set_actor_metadata` proposal.
- Arrange 2 or 3 safe test level Actors through `arrange_actors_pattern`.

Safety checks:

- The plugin shows a Proposal before execution.
- The user can reject the Proposal.
- The operation result is posted back to the backend.
- `GET /api/v1/editor-operations/history` shows the operation.
- `GET /api/v1/editor-operations/diagnostics` summarizes recent operation health.
- The plugin `Show Activity` button displays the same recent activity in the
  Agent Chat workspace.

## 6. Regenerate The Tool Catalog

```powershell
.\.venv\Scripts\python.exe scripts\export_editor_operation_catalog.py --output docs\editor-operation-catalog.md
```

Use this after adding or changing editor operations.
