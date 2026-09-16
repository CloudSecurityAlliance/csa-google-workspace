# Business Case

## Executive summary

CSA's documents live in Google Drive, and the work that matters happens in the **comments** — peer
review, editorial passes, the disposition of a reviewer's objection. Google's own Drive MCP server
does not offer the destructive tools and does not reach comments across Docs, Sheets and Slides
uniformly; the third-party Drive servers surveyed in `research/server-landscape.md` reach files and
content, not the review layer.

So the capability gap is narrow and deep rather than wide: **the part people actually need is the
part nobody built**, and the people who have tried arrive having already failed to build it
themselves.

The second half is that this server is pointed at a real person's Drive. Two dated security audits,
a threat model, and a capability layer that ships destructive tools *present and off* are what make
that defensible — and none of it comes with an API client.

**Benefit categories:** Synergy (primary) · Brand (secondary) · Research / Exploration (secondary)

## CSA value

**The document pipeline becomes scriptable at the review stage.** Comment triage, peer-review
registers, and the disposition of a closed comment set are the expensive manual steps in CSA's
publishing workflow, and they are what this reaches.

**It is the fleet's most weathered server**, so its scar tissue is where the shared standard comes
from: guards that decay, docs that drift ahead of code, and a security mitigation that was real on
the maintainer's platform and a no-op on Windows all surfaced here first and are now fleet-wide
practice.

**It is genuinely used outside CSA.** Public, PyPI-published, and the issue tracker carries
consumer-reported problems from people who are not us — which is the only evidence of adoption that
cannot be manufactured.

## Why not the alternatives

| Alternative | Why not |
|---|---|
| **Google's own Drive MCP server** | Declines the destructive tools entirely — a defensible answer, and a different one from ours. Does not reach comments uniformly across the three file types, which is the capability CSA needs |
| **Third-party Drive MCP servers** | Surveyed in `research/server-landscape.md`. Files and content, not the review layer. "Feature parity" with them was explicitly abandoned as a framing — the question is what a person needs done, not what a competitor's tool list contains |
| **The Google API client libraries** | The right foundation and not a product. This *is* a library first; the point is what sits on top — the capability gate, the comment model, and the probing that established what Drive actually does |
| **Doing it by hand** | The current state for most of it, and the reason peer-review registers take a day |

## The security component is what makes it usable at all

Pointing an agent at someone's Drive is the whole risk. The investment is visible in the tracker: 22
security-labelled issues, 13 hardening, and **two dated audit campaigns** (`audit-2026-07-22`,
`audit:2026-08-27-01`).

What that bought, specifically:

- **Prompt injection treated as a first-class surface.** Document content is attacker-controlled and
  is rendered to the model as the document's own words — a finding, not a hypothetical.
- **Destructive tools present and off.** Having a tool and being permitted to call it are separable,
  which is a different answer from Google's and a better fit for an operator who wants to choose.
- **Read-only proven by refusal upstream**, not by our own gate — Google declines the call.
- **Guards that can fail**, after three from a prior remediation were found asserting nothing.

None of that arrives with an API client, and all of it is the difference between a tool you can point
at a colleague's documents and one you cannot.

## Operational burden

Moderate and the highest in the fleet — six GitHub workflows including a weekly controls job,
lockfile maintenance, and a release cadence of 77 releases in seven weeks. Inventoried in
[`OPERATIONAL-RESOURCES.md`](OPERATIONAL-RESOURCES.md).

## AI enablement

The server exists to be driven by an agent, and the design test is applied at PR time: *can I write a
useful script against this library with no agent present?* If not, the library is wrong. The
escape hatch matters more than the tool count — a tool set is finite and an API is not.
