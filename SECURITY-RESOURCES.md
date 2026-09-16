# Security Resources

The security surface of this project: what it exposes, to whom, and how it is protected.

**Last reviewed:** 2026-09-16 · **Next review:** 2026-12-16

## Summary

**No network surface.** A Python library and a local stdio MCP server run on an operator's own
machine — nothing listens, nothing is deployed. The exposure is a credential, a published artifact,
and document content that is attacker-controlled.

This is the most-released and most-audited project in the CSA MCP fleet: 77 releases in seven weeks,
two dated audit campaigns, a maintained threat model. It is also the one pointed at real CSA
documents daily, which is why that investment exists.

## Exposure surface inventory

| Surface | Type | Exposure tier | Cloudflare | Auth | Notes |
|---|---|---|---|---|---|
| `github.com/CloudSecurityAlliance/csa-google-workspace` | public repo | `public-unauthed` | n/a | none | Source, threat model, audit records |
| Local stdio MCP server | process on an operator's machine | `internal-staff` | n/a | inherits the operator's shell | Not network-reachable. No listener |
| **PyPI `csa-google-workspace`** | **published artifact** | `public-unauthed` | n/a | n/a | **Live.** Trusted Publishing with attestations; 77 releases, one yanked. The real supply-chain surface in this fleet |
| Google Workspace APIs | outbound only | n/a | n/a | per-user OAuth | Acts as the operating user; Google's ACLs are the ceiling |
| **Document content** | **inbound data** | n/a | n/a | n/a | **Attacker-controlled.** `quoted_text` is rendered to the model as the document's own words |

**Cloudflare is not applicable** to any row — none is a CSA-operated inbound network surface. A
conclusion, not an omission.

## Access model

Per-user OAuth: the server acts as the operating user, so Google enforces the real ceiling and our
capability layer is defence in depth. A gate failure exposes that user to their own access.

Above that:

- **A fail-closed capability layer at the data seam.** An undeclared method is refused, not
  delegated, so new capability arrives *off*. Named profiles exist because nobody composes a
  capability list correctly under pressure.
- **Destructive tools ship present and off.** Having a tool and being permitted to call it are
  separable — a different answer from Google's Drive server, which declines them outright.
- **Read-only is proven by Google refusing the call**, not by our own guard (PR #443).

Full model and re-scored ratings: [`THREAT_MODEL.md`](THREAT_MODEL.md).

## Data classification

**Nothing is stored.** No cache, no index. Document content, comment bodies and user identities pass
through memory in transit; there is no `DATA-RESOURCES.md` and that is an explicit N/A.

Two rules follow from content being attacker-controlled, and the second is counter-intuitive:

- Raising log detail raises detail about **the operation**, never about **the content**.
- A debug log of document content is **a persistence step for an injection payload** into a client
  cache directory we cannot see or purge, under the client's retention rather than ours.

## Known gaps and accepted risks

| Gap | Status | Owner |
|---|---|---|
| **CI is ubuntu-only; 27 Windows test failures.** Three named security mitigations were POSIX-only no-ops (#452), and the threat model said otherwise. A green badge means green on one platform | Open — #453, actively worked | Kurt Seifried |
| **Nothing watches Google's API surface.** The Docs API gained comments and suggestion accept/reject, obsoleting two "API-impossible" claims — caught by a human (#364) | Open — [CINO-PE #49](https://github.com/CloudSecurityAlliance-Internal/CINO-Platform-Engineering/issues/49) | Kurt Seifried |
| **Security controls have no single readable place and no guided setup** (#286) | Open | Kurt Seifried |
| **Prompt-injection hardening is researched, not decided** (#297) | Open | Kurt Seifried |
| **Guards decay.** Three from a prior remediation were found asserting nothing; a drift detector always exited 0 | Mitigated — each guard now needs a test proven to fire | Kurt Seifried |
| **Pre-1.0.0 with known bugs in the current release**, stated plainly in the README | Accepted — the tracker is authoritative, the shipped README cannot be | Kurt Seifried |

## Review schedule

Reviewed 2026-09-16. Next review 2026-12-16, or **before 1.0.0**, whichever is sooner — tier-1
requires a security audit to precede 1.0.0, and this project has had two.
