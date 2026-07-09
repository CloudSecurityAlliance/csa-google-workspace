# MCP Protocol Notes (for this project)

> **Refreshed July 2026.** Replaces the scraped `llms-full.md`, which documented spec revision `2025-06-18` and the since-removed HTTP+SSE transport. This is a concise, current orientation — the [official spec](https://modelcontextprotocol.io/specification) is authoritative; check it before implementing.

## Current spec status
- **Stable / ratified: `2025-11-25`.** Target this.
- **Release candidate `2026-07-28`** is landing at end of July 2026 — it introduces breaking changes (see "Coming soon"). Do not build against it yet, but be aware.
- Superseded: `2025-06-18` (what the old doc referenced), `2025-03-26`, `2024-11-05`.

## Message layer
- **JSON-RPC 2.0** over stateful connections with capability negotiation via `initialize` / `initialized`. Unchanged.

## Transports
- **stdio** — primary for local servers (Claude Desktop launches the process; JSON-RPC over stdin/stdout). Current.
- **Streamable HTTP** — the current recommended **remote** transport. Client POSTs JSON-RPC; the server replies with either a single JSON body or an upgraded SSE stream for streaming responses.
- ⚠️ **The old standalone "HTTP+SSE" transport is gone** — replaced by Streamable HTTP in revision `2025-03-26`. Don't design around a separate SSE endpoint.

## Primitives
- **Server → client:** Tools, Resources, Prompts.
- **Client → server:** Sampling, Roots, **Elicitation** (server asks the user for more input mid-flow — added since mid-2025; likely absent from the old doc).

## Notable additions since mid-2025 (relevant to this project)
- **Authorization:** a formal **OAuth 2.1** framework for HTTP-transport servers (resource-server model, RFC 8707 resource indicators). Matters if this server is ever deployed remotely.
- **Structured tool output:** tools can return `structuredContent` with an `outputSchema` — useful for returning comment lists as typed data rather than prose.
- **Tool annotations:** read-only / destructive hints exist, but the spec warns they are **untrusted unless from a trusted server**.
- Tool I/O schemas standardizing on **JSON Schema 2020-12**.

## Coming soon (RC 2026-07-28 — not yet current)
Flagged so the design isn't blindsided: removal of protocol-level sessions (`Mcp-Session-Id`), a move toward stateless operation, required `Mcp-Method`/`Mcp-Name` routing headers, `InputRequiredResult` replacing persistent SSE, and deprecation of Roots/Sampling/Logging with replacements. Treat as future.

## Sources
- <https://modelcontextprotocol.io/specification> (current `2025-11-25`)
- <https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/> (upcoming RC)
- TypeScript SDK: <https://github.com/modelcontextprotocol/typescript-sdk>
