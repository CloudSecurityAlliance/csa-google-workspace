# Design spec — built-in MCP server (`csa_google_workspace.mcp`)

**Date:** 2026-07-23
**Status:** Approved for planning (brainstorm settled 2026-07-23).
**Phase:** 2 — a delivery layer over the shipped `csa-google-workspace` library (v0.1.0, on PyPI).

## 1. Goal & context

Ship a **built-in Model Context Protocol server** so an AI client (Claude Desktop/CLI) can
review comments, read content, and edit Google Docs/Sheets/Slides through the library. The
server is a thin **delivery method** for the library — it adds no document logic, only
maps MCP tools/resources/prompts onto the existing `Workspace` API.

**Self-hosted by design.** The server runs on infrastructure the user controls (their own
machine for v1); it never routes Google credentials through a third-party SaaS host. This
matches the project's standing constraint on sensitive-Drive access.

Decisions locked in the brainstorm:
- **Transport:** local single-user **stdio** first; structured so Streamable HTTP can be
  added later without reworking the tools.
- **Framework:** the official **`mcp` SDK's bundled FastMCP** (`from mcp.server.fastmcp
  import FastMCP`) — first-party, spec-tracking. Target spec revision `2025-11-25`.
- **Write posture:** **full read + write, on by default**, mirroring the library. Hedged
  (not gated) with MCP tool annotations and an optional read-only launch flag (§7).
- **v1 primitives:** tools + one Resource (document text) + one Prompt (comment triage).

## 2. Scope

**In (v1):** stdio server; full read/write tool surface; a document-text Resource; a
comment-triage Prompt; `[mcp]` optional-dependency extra; a console entry point; typed-error
→ tool-error mapping; unit tests via `FakeBackend` + FastMCP's in-memory client.

**Out (v1, designed-for not built):** Streamable HTTP / remote transport; multi-user OAuth
2.1 (resource-server model) + per-user token custody; MCP Sampling/Elicitation; a raw
`batch_update` escape-hatch tool; document discovery (`files.list`) — the library is
document-scoped, so every tool takes a file id/URL.

## 3. Architecture

Mirrors the library's own composition — a factory/DI seam plus per-axis **tool producers** —
so the delivery layer never re-derives what the library already owns. `create_server` parallels
`Workspace`; the producers parallel the library's two axes (uniform comments ~ `CommentsMixin`;
variant content ~ `documents/`).

```
src/csa_google_workspace/mcp/
  __init__.py        # re-exports create_server, main
  __main__.py        # `python -m csa_google_workspace.mcp` -> main()
  server.py          # create_server(workspace) -> FastMCP app; composes the producers below
  _comments.py       # register_comment_tools(app, ws)   — UNIFORM axis (all file types) ~ CommentsMixin
  _content.py        # register_content_tools(app, ws)    — VARIANT axis; read/write via open() + typed methods
  _resources.py      # register_resources(app, ws)        — the document-text resource
  _prompts.py        # register_prompts(app, ws)          — the comment-triage prompt
  _config.py         # env -> Workspace (from_oauth); read_only flag
  _schemas.py        # structured-output models for tool results
```

- **`create_server(workspace: Workspace) -> FastMCP`** builds the app and calls each
  `register_*` producer to bind tools/resources/prompts to the given `Workspace`. This is the
  DI seam (parallel to `Workspace` itself): tests pass `Workspace(FakeBackend(...))`, the CLI
  builds a real one. Each producer is independently testable against `FakeBackend`.
- **`main()`** (entry point) reads config (§5), constructs the `Workspace` via `from_oauth`,
  calls `create_server`, and runs it over stdio (`app.run()`). **All logging goes to stderr** —
  under stdio, stdout is the JSON-RPC channel and must never be written to (no `print`, no
  stdout log handler; the library's own `logging` warnings must land on stderr).
- **Factory-based dispatch (not a type ladder).** Content tools use `ws.open(file)` — the
  library's MIME-sniffing producer — and call the returned typed `Document`'s method directly,
  leaning on the library's polymorphism. A capability the type lacks (e.g. `replace_text` on a
  `Sheet`) is translated into a clean tool error, rather than re-derived with an
  `if doc.type == …` ladder in the MCP layer. Stateless: a fresh `open()` per call (matches the
  library's point-in-time read model; no caching).

## 4. Tool / resource / prompt surface

Structured output (`structuredContent` + `outputSchema`, JSON Schema 2020-12) for anything
list-shaped, so the client gets typed data, not prose. `file` is an id or share URL.

### Reads — `readOnlyHint: true`
| Tool | Maps to | Returns |
|------|---------|---------|
| `open_document(file)` | `ws.open` | `{id, name, type, url}` |
| `list_comments(file, resolved?, author?, since?, include_deleted=False)` | `doc.comments.filter/all` | `list[CommentOut]` |
| `get_comment(file, comment_id)` | `comments.get` | `CommentOut` |
| `read_text(file, tab?, suggestions?)` | `doc.as_text(...)` | `{text}` |
| `list_suggestions(file)` | `Doc.suggestions` | `list[SuggestionOut]` (Docs only) |
| `comments_by_cell(file, cell)` | `Sheet.comments_by_cell` | `list[CommentOut]` (Sheets only) |

### Writes — annotated `destructiveHint`/`idempotentHint` as appropriate
`reply_comment`, `resolve_comment`, `reopen_comment`, `create_comment(…, cell?)`,
`edit_comment`, `delete_comment` *(destructive)*; `replace_text(find, replace, match_case=True)`
*(Doc/Slides)*, `append_text`, `insert_text(text, index)`, `delete_range(start, end)` *(destructive)*;
`update_cells(range, values, value_input_option="RAW")`, `append_rows`, `clear_cells` *(destructive)*
*(Sheets)*; `slides_insert_text(object_id, text, index=0)`.
A tool whose capability the opened document lacks translates the library's absence /
`UnsupportedOperation` into a clear tool error (e.g. `replace_text` on a spreadsheet →
"not supported for spreadsheets; use update_cells") — via the factory dispatch in §3, not a
hand-rolled type ladder.

### `CommentOut` (structured)
`{id, author, content, resolved, created_time, cell|null, replies: [{id, author, content}]}`
— `author` is display name (email is usually absent and not surfaced). Content **is**
returned (the agent needs it); the library's redacted `__repr__` protects *logs*, not tool output.

### Resource
- `document://{file_id}/text` — a read resource returning the document's plain text
  (`as_text`). Keyed by **bare file id** (not a share URL) to keep the URI clean; the tools
  still accept id-or-URL.

### Prompt
- `triage_open_comments(file)` — a prompt template that instructs the model to list open
  comments and propose replies/resolutions, **explicitly framing comment/document text as
  untrusted data, not instructions** (see §7).

## 5. Configuration (local single-user)

Env vars (no secrets in argv):
- `CSA_GW_CLIENT_SECRETS` — path to the installed-app OAuth client secrets (required).
- `CSA_GW_TOKEN` — token cache path (default `~/.csa_google_workspace/token.json`).
- `CSA_GW_READ_ONLY=1` — build a read-only `Workspace` (writes then error at the library guard).

`main()` calls `Workspace.from_oauth(client_secrets, token_path, read_only=…)` — browser
consent on first run, cached/refreshed after (the flow already proven in `tests/oauth/`).

## 6. Error handling

Tool bodies translate the library's typed exceptions into MCP tool errors (`isError`) with a
short, safe message: `NotFoundError`→"file/comment not found", `AccessError`→"permission
denied", `ReadOnlyError`→"server is read-only", `UnsupportedOperation`→the library's message,
`ValueError`→bad-argument message. Messages never interpolate token material (consistent with
the auth hardening). Unexpected exceptions surface as a generic tool error, logged server-side.

## 7. Security posture

Writes are on by default, so the containment from `SECURITY.md` is applied as **hedges, not
gates**:
- **Tool annotations** — `readOnlyHint` on reads; `destructiveHint` on delete/clear/delete_range;
  `idempotentHint` where true. Clients can surface confirmations on destructive tools.
- **Optional `CSA_GW_READ_ONLY=1`** — a one-flag path to a read-only server.
- **Prompt-injection framing** — the triage Prompt and tool docstrings state that document/
  comment content is untrusted input, never instructions; steer edits toward the surgical
  `replace_text` over raw index edits.
- No credential material in tool output, errors, or logs.

## 8. Packaging

- Optional extra in `pyproject.toml`: `[project.optional-dependencies] mcp = ["mcp>=1.2"]`.
  Core library dependencies are unchanged.
- Entry point: `[project.scripts] csa-google-workspace-mcp = "csa_google_workspace.mcp:main"`,
  plus `python -m csa_google_workspace.mcp`.
- README/RELEASING: a "Use as an MCP server" section with the Claude Desktop config snippet.

## 9. Testing

- **Unit (gates CI):** `create_server(Workspace(FakeBackend(...)))` driven by FastMCP's
  in-memory `Client` — call each tool, assert structured output and error mapping. No network,
  no credentials — the same `FakeBackend` strategy as the rest of the suite. The `mcp` extra is
  added to the `dev` install so CI can import it.
- **Gated live smoke (optional):** one `CSA_GW_MCP_LIVE`-gated test that starts the server
  against the real `cino-gmail-mcp` token and lists comments on a throwaway doc.
- ruff/mypy/coverage/bandit gates apply to the new module as to the rest of `src`.

## 10. Phasing

One implementation plan (via writing-plans), TDD, bite-sized tasks: (a) `[mcp]` extra +
package skeleton + `create_server` + config; (b) read tools + structured schemas + tests;
(c) write tools + annotations + tests; (d) Resource + Prompt + tests; (e) entry point + docs
+ a gated live smoke. Each task: FakeBackend tests, then commit; PR at the end.
