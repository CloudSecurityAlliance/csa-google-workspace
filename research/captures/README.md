# Captures of Google's official Workspace MCP servers

**Captured 2026-09-16 at 20:47:47Z UTC**, unauthenticated, from this machine. Method: a raw JSON-RPC
`initialize`, then `tools/list`, `resources/list` and `prompts/list` POSTed to each endpoint.
No credentials were used and no Google account was involved — the tool registries are served to
unauthenticated callers.

| Endpoint | Exists | Server name | Capabilities | Instructions | Tools |
|---|---|---|---|---|---|
| `drivemcp.googleapis.com/mcp/v1` | yes | `StatelessServer` | `tools` only | **none** | 8 |
| `docsmcp.googleapis.com/mcp/v1` | yes | `StatelessServer` | `tools` only | **none** | 2 |
| `sheetsmcp.googleapis.com/mcp/v1` | yes | `StatelessServer` | `tools` only | **none** | 6 |
| `slidesmcp.googleapis.com/mcp/v1` | yes | `StatelessServer` | `tools` only | **none** | 2 |

A control probe against a non-existent `*.googleapis.com` host returned 404 to both GET and POST;
these four returned **405 to GET and 200 to POST**, which is how their existence was confirmed rather
than assumed. (405-on-GET is the correct stateless-server behaviour — see
`research/mcp-servers/STATELESS-GET-HANG.md` in CINO-Platform-Engineering.)

`resources/list` and `prompts/list` return an HTML **400** from the Google frontend rather than a
JSON-RPC error, consistent with the `tools`-only capability declaration. The raw responses are kept
as captured.

## The finding

**Google's servers now do comments, and this repository's positioning assumed they did not.**

| Surface | Read comments | Write comments | Suggestions |
|---|---|---|---|
| Docs (`docsmcp`) | `commentsIncluded` | insert · reply · update · delete · deleteReply | **accept / reject** |
| Sheets (`sheetsmcp`) | `commentsIncluded` | insert · reply · update · delete · deleteReply | — |
| Slides (`slidesmcp`) | `commentsIncluded` | — | — |
| Drive (`drivemcp`) | `includeComments`, with a `CommentThread` output schema | — | — |

`docsmcp/update_doc` also carries a mode: *"Changes are applied directly to the document"* versus
*"Changes are made as suggestions"*.

**This is [#364](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/364) having
already happened.** That issue recorded the Docs API gaining comments and suggestion accept/reject in
Developer Preview, and noted it *"obsoletes two of our 'API-impossible' claims"*. It has since
shipped into Google's own MCP servers, and nothing here noticed — because nothing was watching. See
[CINO-PE #49](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/issues/49).

## What is still differentiated, precisely

Read against the capture rather than assumed:

- **Slides comment writes.** Google reads Slides comments and does not write them; this server does.
- **Sharing writes.** Google has `get_file_permissions` (read). No grant, no revoke, no access
  proposals. This server has `share_file`, `unshare_file`, `update_file_permission`,
  `list_access_proposals`, `resolve_access_proposal`.
- **The capability layer.** Google's servers have no profiles, no gating, and no operator control over
  what an agent may do — which is the whole of `csa-google-workspace`'s security posture.
- **Anchors.** Whether this server's anchor resolution and localisation handling exceeds Google's is
  **not established by this capture** and needs a behavioural comparison, not a registry diff.

## What is no longer differentiated

- **Comment reads across all four surfaces.** Uniform, in Google's own servers.
- **Comment writes on Docs and Sheets.**
- **Suggestion accept/reject on Docs.**

## Re-running this

The registries are public and unauthenticated, so unlike `csa-skilljar`'s official-server capture
this one **can** be re-derived in CI. It should be: see CINO-PE #49.
