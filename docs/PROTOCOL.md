# Wire protocol reference

`branching-story-mcp` speaks JSON-RPC 2.0 over stdio. One JSON message per line,
newline-delimited, UTF-8. Only responses are written to stdout; diagnostics (if any) go to
stderr. Protocol versions `2024-11-05` and `2025-03-26` are supported; unknown requested
versions fall back to `2025-03-26`.

## Lifecycle

```text
client -> server   {"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}
server -> client   {"jsonrpc":"2.0","id":1,"result":{...}}
client -> server   {"jsonrpc":"2.0","method":"notifications/initialized"}      (no response)
client -> server   {"jsonrpc":"2.0","id":2,"method":"tools/list"}
server -> client   {"jsonrpc":"2.0","id":2,"result":{"tools":[...]}}
```

## `initialize`

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": { "name": "my-client", "version": "1.0.0" }
  }
}
```

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-03-26",
    "capabilities": {
      "tools": { "listChanged": false },
      "resources": { "subscribe": false, "listChanged": false }
    },
    "serverInfo": { "name": "branching-story-mcp", "version": "1.0.0" },
    "instructions": "branching-story-mcp exposes Ouba Studio's deterministic branching-story-kit ..."
  }
}
```

## `tools/call`

Request:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "query_ai_story_benchmark",
    "arguments": { "status": "fail" }
  }
}
```

Response (text content is the same JSON as `structuredContent`):

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [{ "type": "text", "text": "{\"benchmark\":{...},\"results\":[...],\"count\":1,...}" }],
    "structuredContent": { "benchmark": { "...": "..." }, "results": [], "count": 1 },
    "isError": false
  }
}
```

Semantic failures (e.g. a broken story graph) return `isError: true` with
`structuredContent: {"ok": false, "error": "..."}`. Malformed arguments, unknown tools and
unknown methods return JSON-RPC errors instead.

| Condition | HTTP-ish code | Message |
| :--- | :--- | :--- |
| Malformed JSON | `-32700` | `Parse error: ...` |
| Non-object message / missing method | `-32600` | `Invalid Request: ...` |
| Unknown method | `-32601` | `Method not found: ...` |
| Unknown tool, bad arguments, missing resource URI | `-32602` | `Invalid params` |
| Unknown resource URI | `-32002` | `unknown resource URI: ...` |

## `resources/read`

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "method": "resources/read",
  "params": { "uri": "ouba://benchmark/2026-10-platform-matrix" }
}
```

```json
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "contents": [
      {
        "uri": "ouba://benchmark/2026-10-platform-matrix",
        "mimeType": "application/json",
        "text": "{\"license\":\"CC-BY-4.0\", ...}"
      }
    ]
  }
}
```

## Canonical JSON and the trace hash

`trace_hash = sha256(canonical_json(payload))`, where `canonical_json` is JSON with object
keys sorted lexicographically, no insignificant whitespace, and integral numbers written
without a decimal point (so `2.0` and `2` hash identically). Python (`json.dumps(...,
sort_keys=True, separators=(",", ":"))` after collapsing integral floats) and JavaScript
(`JSON.stringify` over a recursively key-sorted object) produce the same bytes.

Any agent can therefore recompute the hash locally and prove that the story state it holds is
exactly the state the reducer produced — a mismatch is silent state drift by definition.
