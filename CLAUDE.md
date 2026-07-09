# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This is a **research and design repository**, not an implemented codebase. There is no source code, build system, or test suite yet. It contains the specification for a future Model Context Protocol (MCP) server that manages **comments on Google Drive files (with a focus on Google Sheets)**. When implementation begins, the design in `research/` is the blueprint to follow.

All content lives in `research/`:

- **`Google Sheets Comments MCP Server - Design Document.md`** — the authoritative build spec: MCP tool definitions (with TypeScript schemas), caching architecture, chosen tech stack, and a phased implementation plan. Start here when writing code.
- **`Google Drive API Comment-Related Capabilities.md`** — reference for all 12 `comments.*` / `replies.*` Drive API v3 methods, the anchoring system, and OAuth scopes.
- **`report-claude.md`** / **`report-chatgpt.md`** — market analysis and empirical API-behavior findings; `report-chatgpt.md` has the most detail on real-world anchor parsing.
- **`llms-full.md`** — MCP protocol reference (transports, message types, lifecycle).

## Critical architectural facts

These are the non-obvious decisions that shape any implementation and are spread across multiple documents:

1. **Comments are a Google Drive API v3 concern, not Sheets.** The Google Sheets API cannot create, read, or delete comments — all comment/reply CRUD goes through `/drive/v3/files/{fileId}/comments`. (Sheets *notes* are different and are explicitly out of scope.)

2. **The `anchor` field is the core engineering risk.** A comment's spatial location (which cell/row/column/range) is stored in an undocumented, inconsistently-formatted `anchor` string (e.g. `R1C2`, structured `range=` forms, or opaque object references). Parsing it into A1 notation is fragile — merged cells, named ranges, and multiple tabs produce ambiguous anchors. Treat anchor normalization as a first-class module developed against a synthetic test sheet covering these edge cases, with fallbacks.

3. **Resolution is done via action-replies, not a settable field.** `resolved` cannot be PATCHed directly on a comment; resolve/reopen is performed by creating a reply with an action. Deletes are soft (comment marked `deleted: true`).

4. **Scope is comments-only, by design.** Reading/writing cell data and document content are handled by *separate* MCP servers. This server is meant to run alongside them. Do not add spreadsheet-data or doc-content features.

5. **Caching + spatial indexing is central, not optional.** Large sheets have thousands of comments that would overflow an AI context window. The design mandates an in-memory cache (per `spreadsheetId`) plus a spatial index (cell/row/col/range → commentIds), with automatic invalidation on any write. Cache is in-memory only — no persistent storage of comment content.

## Intended tech stack (when implementing)

Per the design doc, not yet present in the repo:

- **TypeScript** with `@modelcontextprotocol/sdk` and the `googleapis` npm package
- **Stdio transport** primary, SSE optional
- **Jest** for tests (target 90%+ coverage, focused on cache invalidation and anchor/spatial parsing), **ESLint + Prettier**
- Default to **read-only mode**; writes require explicit opt-in (`enable_write`)

## Working in this repo today

Since the repo is documentation only, work is normal Markdown editing under `research/` and `README.md`. There are no commands to build, lint, or test. Keep `README.md`'s manifest in sync when adding or restructuring research documents.
