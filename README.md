# Google Drive Comments Research

Research on how **comments on Google Drive / Google Sheets files** work via the Google APIs, and a design for a Model Context Protocol (MCP) server that manages them. There is **no code yet** — this repo is research and design.

> **Last verified: July 2026.** See [`CHANGELOG.md`](./CHANGELOG.md) for what was corrected in the latest refresh.

## Documents

| Document | What it is |
|----------|------------|
| [`research/google-drive-comments-reference.md`](./research/google-drive-comments-reference.md) | **Start here.** The canonical reference on how Drive/Sheets comments actually work: the 10 API methods, fields, resolution/deletion models, OAuth scopes, and the hard truth about the `anchor` field for Sheets. |
| [`research/mcp-server-design.md`](./research/mcp-server-design.md) | Design for a comment-management MCP server, with a 2026 reality check and a revised, still-viable scope. |
| [`research/mcp-protocol-notes.md`](./research/mcp-protocol-notes.md) | Concise, current MCP protocol orientation (spec `2025-11-25`, transports, primitives). |
| [`CHANGELOG.md`](./CHANGELOG.md) | What changed in each refresh, and why. |

## The three things worth knowing

1. **Comments are a Google Drive API v3 concern — not the Sheets API.** (Sheets *notes* are separate, and use the Sheets API.)
2. **You cannot reliably anchor a comment to a specific Sheets cell via the API.** Google treats API-created anchors as unanchored. Mapping a comment back to a cell requires exporting the sheet as XLSX and parsing the comment XML. This is the central constraint of the whole problem.
3. **The space is no longer greenfield.** Several MCP servers already handle Google comments. The defensible differentiator is doing the hard read-side cell mapping (and Sheets/Slides coverage) well — not merely supporting comments.

## License

Dual-licensed under [MIT](./LICENSE-MIT) and [Apache 2.0](./LICENSE-APACHE).
