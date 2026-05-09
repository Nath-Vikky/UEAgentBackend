# UE C++ HTTP, WebSocket, And AsyncAction Example Notes

source_note: distilled from local UE C++ course notes and rewritten for this project knowledge base
scope: local UE knowledge base
license_check: source repository says course materials are for purchased learners; this file is an original summary, not a copied chapter
domain: examples
topic: HTTP request, WebSocket client, Blueprint async action, network module dependencies
use_for: Code Generate, Project QA, Code Review

## HTTP Request Shape

Use `FHttpModule::Get().CreateRequest()` for request-response work.

Recommended pieces:

- `#include "HttpModule.h"`
- `#include "Interfaces/IHttpRequest.h"`
- `#include "Interfaces/IHttpResponse.h"`
- `#include "Dom/JsonObject.h"` and `JsonUtilities` when parsing structs.
- Bind `OnProcessRequestComplete` before calling `ProcessRequest()`.
- Check `bWasSuccessful`, `Response.IsValid()`, and HTTP response code.
- Keep API keys out of source files; read them from config or editor settings.

Build dependencies:

```csharp
PrivateDependencyModuleNames.AddRange(new string[] {
    "HTTP",
    "Json",
    "JsonUtilities"
});
```

## WebSocket Client Shape

Use `FWebSocketsModule::Get().CreateWebSocket(Url)` for persistent bidirectional communication.

Recommended pieces:

- Hold the socket in a `TSharedPtr<IWebSocket>` owned by a Subsystem, Component, or service object.
- Bind `OnConnected`, `OnConnectionError`, `OnClosed`, and `OnMessage`.
- Call `Close()` during deinitialization or owner cleanup.
- Add heartbeat and reconnect policy only when the product requirement needs it.

Build dependency:

```csharp
PrivateDependencyModuleNames.AddRange(new string[] {
    "WebSockets"
});
```

## Blueprint AsyncAction Shape

Use `UBlueprintAsyncActionBase` when designers need a Blueprint node for a one-shot async request.

Common structure:

- Static factory function marked `BlueprintCallable`.
- `Activate()` starts the async operation.
- `UPROPERTY(BlueprintAssignable)` delegates expose success/failure.
- Use `RegisterWithGameInstance(WorldContextObject)` for lifetime.
- Broadcast only on GameThread.

## Generated Code Boundaries

The backend should return non-destructive drafts. It should not write `.h`, `.cpp`, `.uasset`, `.ini`, or secrets to the UE project automatically.
