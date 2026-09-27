# csa-google-workspace

A **Python library** for managing **comments** and **content** on Google **Docs, Sheets, and Slides**, via the Google APIs. Comments are handled uniformly across all three file types (a single Drive API v3 concern); content read/write and Sheets comment→cell mapping are the variant, per-API parts.

> **Which comment API this uses, and why.** Comments go through the **Drive API v3**, which is
> GA and works on any Drive file. Since mid-2026 the Docs, Sheets and Slides APIs have their own
> **native** comment surfaces in Google's **Developer Preview** — with anchoring the Drive API
> cannot reproduce (a character range in Docs, a cell coordinate in Sheets) and a stable author
> identity the Drive API does not populate. We deliberately **stay on Drive for now**: support for
> the native APIs is planned **post-1.0, before they reach general availability, and behind a
> flag** — most people are not enrolled in the preview, so it cannot be the default. Google has
> not announced deprecation of the Drive comments API and it remains the only option for
> non-editor files, so this is **coexistence, not migration**. Background and measurements:
> [`research/comments-apis-2026-09.md`](./research/comments-apis-2026-09.md).

It's designed to be **embedded**: a clean, typed Python surface for building AI tooling on top of Google Workspace — **MCP servers, agent/LLM plugins, review bots, and automation services** that need to read documents, triage and reply to comments, and write edits back. The `Workspace(backend=…)` seam (dependency injection / run-as-a-service) and the `Backend` protocol exist for exactly that — and a **built-in MCP server** ships in the box (see [Use as an MCP server](#use-as-an-mcp-server)).

## Status: beta — pre-1.0.0, and moving fast

**This is pre-1.0.0 software under active daily development. Expect rough edges, and expect
current releases to contain bugs.**

The pace is real and it is deliberate: **32 releases since 22 July**, fourteen of them on a single
day, one [yanked](./PROVENANCE.md#yanking). It is being used on real CSA documents and fixed as
things surface, which is the fastest way to find what actually breaks — and it means the version
you install today is newer and less weathered than most software you install.

What to expect while it is pre-1.0.0:

- **Known bugs, in the current release.** The
  [open issues](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues) list is the
  live and authoritative one; this file cannot be, because the README shipped to PyPI is frozen at
  each release. **Read the tracker before relying on anything unusual.**
- **Breaking changes before 1.0.0.** Nothing is frozen yet. What *will* be stable, and what
  deliberately will not, is written down in [`API-STABILITY.md`](./API-STABILITY.md).
- **Docs that can lag the code.** Two stale claims in this very file were found and corrected on
  2026-08-27, one of them describing a capability that had shipped fifteen releases earlier. If the
  code and the prose disagree, **the code is right** — and please report it.

Practical advice, none of it hypothetical:

- **Nothing is off by default, and an unconfigured install has your full Drive reach.** All
  eleven capabilities are on and both allowlists permit every file; **narrowing is what you
  configure** — [start here](#which-one-to-reach-for). That is coherent because a capability
  enabled here is not a permission granted (every call runs as you, against Drive's own ACLs),
  but it does mean a default install adds no bound of its own. `CSA_GW_READ_ONLY=1` is the one
  variable that changes the most for the least effort.
  *(This bullet said the opposite — "every destructive capability is off until an operator names
  it, and the file allowlists fail closed" — for the eleven releases after v0.31.0 reversed it.
  Found by an external correctness review, 2026-09-01, as RR-003.)*
- **`apply_comment_actions` defaults to a dry run.** Read what it says it would do before passing
  `apply`. This posts under your name to a document your colleagues are reading.
- **Try the write path on a document you can afford to break first.** Then use it in anger.
- **Report anything odd** — ask your AI client to *"report a problem with csa-google-workspace"* and
  the server assembles the version, platform and effective policy for you, with no document content
  in it.

None of which is to undersell what works: the library is **feature-complete for its scoped
roadmap** and **live-verified end-to-end against real Google**, behind **over 1,600 offline
tests**, with
`ruff` and `mypy` clean in CI across Python 3.10–3.14. Shipped across Docs/Sheets/Slides: comment
management, content read/write, Sheets comment→cell mapping, and Docs suggestions read. See
[`CHANGELOG.md`](./CHANGELOG.md); design and phased plans under
[`docs/superpowers/`](./docs/superpowers/).

**Built-in MCP server** (since 0.2.2) (`csa_google_workspace.mcp`): a local stdio server, **58
tools**, so an AI client can read documents, triage and write comments, and edit content through
the library. Content writes landed in 0.13.0 and Docs suggestions in 0.20.0, so the server now
reaches everything the library does. Install with the `[mcp]` extra; see below.

## Install

```bash
pip install csa-google-workspace
```

Python >=3.10. The package is typed (ships `py.typed`), so downstream `mypy`/`pyright` consume
its type hints. Working on the library itself? See [Development](#development).

## Usage

```python
from csa_google_workspace import Workspace

ws = Workspace.from_credentials(my_google_creds)   # BYO credentials (or .from_oauth("client_secret.json"))
doc = ws.open("https://docs.google.com/document/d/…/edit")   # -> Doc | Sheet | Slides

# Comments — uniform across all three file types
for c in doc.comments.filter(resolved=False):      # triage open comments
    print(c.author.display_name, c.content)
    c.reply("looking into it"); c.resolve()
doc.create_comment("Please review section 3")

# Content read + write (type-specific)
doc.as_text()                                       # plain text of a Doc / Sheet grid / Slides deck
doc.replace_text("draft", "final")                  # Doc & Slides;  doc.append_text / insert_text / delete_range too
doc.suggestions                                     # Docs suggesting-mode edits (read-only)
doc.as_text(suggestions="accepted")                 # preview as if suggestions accepted / rejected

sheet = ws.open(sheet_url)
sheet.update("Sheet1!A1", [["=SUM(B:B)"]], value_input_option="USER_ENTERED")   # formulas ok
sheet.append_rows("Sheet1!A1", [["new", "row"]])    # append after the last row
sheet.as_text(tab="Data")                           # one tab; as_text() renders all tabs
sheet.comments_by_cell("B11")                       # comments mapped back to a cell (best-effort)
```

**Entry points:** `Workspace.from_credentials(creds)` (bring-your-own credentials — user OAuth or a service account), `Workspace(backend=…)` (dependency injection / run-as-a-service), `Workspace.from_oauth(...)` (interactive login). **Writes are on by default**; pass `read_only=True` to lock them (and narrow to read-only OAuth scopes). Public types — `Comment`, `Author`, `Reply`, `Location`, `Suggestion`, `Slide` — are importable from the package root.

## Use as an MCP server

**1. Install it.** Either of these puts the CLI in its own environment — use whichever you have:

```bash
uv tool install "csa-google-workspace[mcp]"    # or:
pipx install "csa-google-workspace[mcp]"
```

`pip install` works too, and is the right choice when you are embedding the **library** in your
own application — see [the note below](#why-an-isolated-install) for when it is not.

**2. Authorize, once, in a terminal.** Put your Desktop-app OAuth client at
`~/.csa_google_workspace/client_secret.json` (or point `CSA_GW_CLIENT_SECRETS` elsewhere):

```bash
csa-google-workspace-mcp login
csa-google-workspace-mcp login --force         # ...or re-authorize deliberately
```

**3. Register it with your MCP client.** All of these are stdio clients launching the same console
script, so the server is identical; only the registration differs.

```bash
# Claude Code          (-s user: see the scope note below)
claude mcp add -s user csa-google-workspace -- csa-google-workspace-mcp

# Codex CLI            (already global)
codex mcp add csa-google-workspace -- csa-google-workspace-mcp

# Gemini CLI           (note: no `--`)
gemini mcp add -s user csa-google-workspace csa-google-workspace-mcp

# Claude Desktop       (a JSON file, not a command - so this writes it for you)
csa-google-workspace-mcp configure
csa-google-workspace-mcp configure --print     # ...or show the JSON without writing
```

**Claude Desktop is the one that needs its own command**, and not for tidiness. Desktop is a GUI
app: it inherits launchd's `PATH` (`/usr/bin:/bin:/usr/sbin:/sbin`), which contains neither
`~/.local/bin` nor Homebrew, so a bare command name is simply not found. `configure` writes the
**absolute** path along with your `CSA_GW_*` variables, merged into whatever else is already in
the file, with a timestamped backup. Restart Desktop afterwards.

**Three differences that bite**, read from the installed CLIs — Claude Code 2.1.251, `codex-cli`
0.151.0, Gemini CLI 0.57.0 — rather than from docs:

| | Claude Code | Codex | Gemini |
|---|---|---|---|
| separator before the command | `--` | `--` | **none** — the command is positional |
| default scope | **`local`** — this project only | global | **`project`** — lands in `./.gemini/` |
| an environment variable | `-e KEY=value` | `--env KEY=value` | `-e KEY=value` |

**The scope default is the trap, and it catches two of the three.** Only Codex registers globally
on its own. Claude Code defaults to `local` and Gemini to `project`, so a plain `mcp add` in
whatever directory you happened to be in registers the server *there* — and it is then missing
everywhere else, which reads as a failed install rather than a scoping choice. `-s user` is what
you almost certainly want for a tool like this; drop it deliberately when you want one project to
have Drive access and the rest not to, which is a legitimate thing to want.

**Two Gemini flags to leave alone.** `--trust` *"bypass all tool call confirmation prompts"* — not
on a server that can edit documents, share files and answer access requests. And
`--include-tools` / `--exclude-tools` filter **client-side**: they change what the model is
offered, not what the credentials can reach, so they are tidiness rather than a control. For a
real bound on the surface, use `CSA_GW_FLAVOUR` or a profile, which this server enforces.

**On DesktopSetup.** CSA's `DesktopSetup` scripts install this server among other things — so if
you ran those, you already have it. It is a *meta-installer*, not an install method for this
project: the instructions above are the canonical ones, and are what a person outside CSA uses.

## Security — narrowing what this can do

Everything below this heading is about bounding the server. Two things belong at the top rather
than buried, because they are the ones people get wrong:

**1. Turn off the built-in Drive connector** (next section). Leaving both enabled **defeats the
scoping entirely** — the connector reaches the same account with none of these controls, so a
refusal here stops being a refusal.

**2. This is a ceiling *below* Drive's permissions, never an expansion.** Every call runs as the
authorizing user against Drive's own ACLs. These controls stop an agent doing what you *could* do
but did not intend; they cannot grant anything. The named primary risk stays **prompt injection
through document and comment content** ([`SECURITY.md`](./SECURITY.md)), and this is **damage
containment, not prevention**.

### Which one to reach for

In order. Most installs need only the first, and each line is independently useful:

| Want | Set | Why this one |
|---|---|---|
| **triage / read and report only** | `CSA_GW_READ_ONLY=1` | The strongest and simplest. The guarantee is *which credential exists* — a separate token cache and `.readonly` OAuth scopes — not which code path runs, so there is no write authority to reach even if something else is misconfigured |
| **comment, but never edit the document** | `CSA_GW_PROFILE=commenter` | Additive only; a resolve leaves a visible reply |
| **edit, but never share or destroy history** | `CSA_GW_PROFILE=writer` | Everything *recoverable*. Drive's own Editor cannot share either |
| **one capability off an otherwise-right profile** | `CSA_GW_CAPABILITIES=…` | An explicit **complete** list, not a delta, so it reviews like code |
| **the agent to see less than you can** | `CSA_GW_ALLOWLIST_READ` | A project or working set instead of your whole Drive |
| **to bound what a successful injection can damage** | `CSA_GW_ALLOWLIST_MODIFY` | Almost always worth a short explicit list. `READ="*"` with a narrow `MODIFY` is a coherent posture; `*` on both is the one to talk yourself out of |
| **a smaller tool surface** | `CSA_GW_FLAVOUR` | Fewer tools published — allowed *and* advertised |

**The ladder is ordered by what can be undone, not by how alarming the verb sounds.** Four
capabilities are irreversible and flagged as such: **`comment.edit`**, **`comment.delete`**,
**`content.delete`** and **`file.share`**. Trashing a file is *not* among them — Drive's bin holds
it for 30 days and its owner can restore it — so `writer` may trash while holding **none** of the
four. All three of the local ones arrive together at `fileOrganizer`; `file.share` is what
`organizer` adds, because it is the only one that moves data out of the organisation. There is no
permanent delete anywhere in this library, and nothing that empties the trash.

### Checking your own work

Reading a config back is a different act from writing one, and these answer the question the
table cannot:

```bash
csa-google-workspace-mcp describe        # the effective policy, from a terminal
```

| Ask the server | Tells you |
|---|---|
| `describe_configuration` | the live effective policy as structured output — what is on, what is off |
| `preview_allowlist` | each allowlist entry resolved to its **real Drive name**, and whether it is `ok`, `trashed` or `unreachable` |

`preview_allowlist` is the one worth running after any edit: an allowlist entry is a bare file id,
so a wrong paste under a right-looking comment is invisible until something resolves it. Note that
**matching is by file id** — a *copy* of an allowlisted document is not allowlisted.

The full reference lives at `csa-gw://help/configuration`; the sections below are the reasoning.

### Turn off the built-in Google Drive connector

**If you use this server, disable Claude's own Google Drive connector.** Not merely to avoid
confusion — although there is that, since the tool names are deliberately identical — but
because leaving both enabled **defeats the scoping described below.**

The allowlists and capability gating here are enforced by *this* server. Claude's built-in
connector reaches the same Google account with none of them. So with both enabled, a refusal
from this server is not a refusal: the same operation is available through the other route, on
the same files, with no allowlist at all. **The scoping stops being a bound on what the model
can do and becomes a bound on one of two ways to do it.**

Where to turn it off:

- **Claude Desktop / claude.ai** — Settings → Connectors → Google Drive → disconnect. This is
  where it matters most; connectors are on by default once authorized.
- **Claude Code** — the same connector, unless another auth source takes precedence. If `/mcp`
  reports *"claude.ai connectors are disabled because ANTHROPIC_API_KEY or another auth source
  is set"*, they are already inactive and there is nothing to do.

Keeping the built-in one instead is a perfectly reasonable choice — see the comparison below,
and note that Google's hosted server has a *better* answer to scoping than either of us. What
is not reasonable is running both and believing the allowlist means something.

### Scoping what it may touch

Three independent bounds, all plain environment variables, so they can be set wherever your MCP
client declares the server — a shell, `.mcp.json`, or Claude Desktop's config.

**How the other two servers compare here is worth being precise about**, because "we have a
feature they lack" would be the wrong summary. Google's server reaches this outcome by a
different and arguably better route: it authorizes with **`drive.file`**, so Google itself limits
it to files the user explicitly picked — allowlisting enforced upstream, where it cannot be
misconfigured. And its only writes *create new files*, so there is nothing to scope. It has no
knobs because it does not need them.

The claude.ai connector is the one that differs in substance: full `drive` access, plus
`update_file`, `trash_file` and `share_file`, with no way to narrow any of it. This server has
those three as well — the difference is that each is off until an operator names it, and refuses
for any file the modify allowlist does not list.

This library needs full `drive` scope by design — it opens arbitrary files the user names, which
`drive.file` cannot reach (`SECURITY.md`, *Scope breadth*). Having given up Google's upstream
enforcement, it owes you an equivalent, and these are it.

**Everything is on out of the box; narrowing is what you configure.** That is deliberate, and
the reason it is coherent rather than a shrug: **a capability enabled here is not a permission
granted.** Every call still runs as you, against Google's own ACLs — `organizer` on a file where
you are merely a Commenter still cannot edit it, because the API returns 403 and nothing here
changes that. This is a ceiling *below* Drive's, never an expansion of it, so "everything on"
means *subtract nothing; let Drive decide*.

| Variable | Bounds | Unset | Narrow it when |
|---|---|---|---|
| `CSA_GW_ALLOWLIST_READ` | which files may be **read** | **every file** | you want the agent seeing less than you can — a project, a working set |
| `CSA_GW_ALLOWLIST_MODIFY` | which files may be **changed, added to or deleted** | **every file** | almost always. This is the one worth a short explicit list — see below |
| `CSA_GW_PROFILE` | **what kind** of mutation, by name — see the table below | everything on | you want an unattended run acting as a commenter rather than as yourself |
| `CSA_GW_CAPABILITIES` | the same, as an explicit list. Overrides the profile | see profile | a profile is nearly right and you need one capability off |
| `CSA_GW_READ_ONLY=1` | the blunt one — no writes, and narrower OAuth scopes | writes are **on** | you want the narrowest possible posture in one variable |
| `CSA_GW_LOCAL_READ` / `CSA_GW_LOCAL_WRITE` | whether registers may be read from and written to **this machine** | on | your data-handling policy says review material stays inside the client. **Not a disclosure control** — the content is in the model's context either way |
| `CSA_GW_FLAVOUR` | which **tool surface** to publish — `full` (default), `google`, `claude` | `full` | you want a drop-in for one of the vendor servers: those tools and no others, **advertised as well as allowed** |
| `CSA_GW_LOG_LEVEL` | how much goes to stderr — `DEBUG`…`CRITICAL` | `WARNING` | you are reproducing a problem. **There is no log-file setting**: your MCP client already persists our stderr — see below |

A **malformed** list is refused loudly and the server will not start. Unset is an operator who
has not narrowed anything; malformed is one who tried and failed, and widening that to every
file would hand them the opposite of what they wrote.

**On logs.** Turn `CSA_GW_LOG_LEVEL` up and the output goes to stderr, which your MCP client
already captures and files — Claude Code keeps per-connection JSONL with a session id under
`~/Library/Caches/claude-cli-nodejs/`, Claude Desktop keeps
`~/Library/Logs/Claude/mcp-server-csa-google-workspace.log`. That copy survives this process
crashing, which one written here would not, so there is deliberately no log-file setting.

Raising the level raises detail about the **operation** — which tool, which file id, what was
refused, how long it took — and never about **content**. No document or comment text is logged at
any level, which matters precisely because that capture lands somewhere outside your retention
policy and nobody is watching it.

**The two allowlists are not symmetrical, and should not be set symmetrically.** Widening the
read list exposes *content to a model*; widening the modify list exposes *your documents to
whatever that model then decides to do*. Prompt injection through document text is this
project's named primary risk (`SECURITY.md`), and it converts the first into the second — a
comment in a file you read is the attacker's input, and the modify allowlist is what bounds
the blast radius. `READ="*"` with a short, explicit `MODIFY` is a coherent posture. The reverse
is not, and `*` on both is the configuration this section exists to talk you out of.

**Profiles**, so "what may this install do?" has a short answer:

**These are Google Drive's own roles, named as the Drive API names them** — so the word in your
configuration is the word `get_file_permissions` returns, and you are not holding two models.

| Profile | Google's interface calls it | May |
|---|---|---|
| `reader` | Viewer | nothing — read and report only. May still obtain copies, exactly as Drive's Viewer may download |
| `commenter` | Commenter | comment, reply, resolve. All additive, and resolve leaves a visible reply |
| `writer` | Editor · Contributor | the above, plus edit content, create files, rename/move, and trash |
| `fileOrganizer` | Content manager | the above, plus edit and delete comments — **"may destroy comment history, may never share"** |
| `organizer` | Manager | everything, including share |

`editor` and `full` still work, as aliases of `writer` and `organizer` with identical capability
sets. Google's *interface* labels are **not** accepted — `CSA_GW_PROFILE=manager` fails and tells
you to use `organizer`, because one accepted spelling is worth more than two.

**Within the ladder, the order is drawn on one question: can this be undone?** Not on how
alarming the verb sounds, which is where it used to be drawn and which had it backwards. Drive
agrees on the part that matters: its Writer cannot share either.

| Operation | Recoverable? | How |
|---|---|---|
| edit document content | **yes** | Drive revision history, restorable in the UI |
| resolve / reopen a thread | **yes** | reversible, and either way it posts a visible reply |
| create a file | n/a | nothing that already exists is touched |
| rename or move | **yes** | rename it back |
| **trash a file** | **yes — 30 days** | Drive's bin. The owner can see it and restore it |
| edit a comment | **no** | Google keeps no visible edit history. The previous text is gone |
| delete a comment | **no** | the soft delete strips content *and* author. Gone |
| share a file | **no, in effect** | the grant is revocable; a copy the recipient took is not |

"Content edits are versioned, so editing is safe" is true of **document content** and false of
**comments** — and the old grouping encoded the wrong half of that. Until v0.21.0 the default
profile permitted both irreversible comment operations and forbade trashing, so an agent could
destroy a comment thread beyond recovery but could not tidy up a scratch file it had just
created. Withholding a reversible capability produced irreversible litter in real Drives.

There is **no permanent delete** anywhere in this library and no capability that empties the
trash. The worst a `full` install can do to a file is put it in a bin its owner controls.

Profiles cover **capabilities only**. The allowlists are deliberately not profiled: which
documents a deployment may touch is specific to that deployment, and a named default for it
would be a named default for *"which of your files an agent may change"*.

Each is a ceiling and none can widen another: a capability that is off cannot be reached by
listing a file, and a file outside `MODIFY` cannot be reached by enabling a capability.

**Nothing is required.** Install it and it works, with the same reach you have. If that is what
you want, there is no configuration section for you.

**A worked example of narrowing**, for an unattended job that should comment on two documents
and change nothing else:

```jsonc
{ "mcpServers": { "csa-google-workspace": {
  "command": "csa-google-workspace-mcp",
  "env": {
    "CSA_GW_ALLOWLIST_MODIFY": "https://docs.google.com/document/d/AAA…/edit  # CCM mapping\nhttps://docs.google.com/spreadsheets/d/BBB…/edit  # AICM tracker",
    "CSA_GW_PROFILE": "commenter"
  }
} } }
```

Reads are left wide here on purpose: the agent already sees whatever your credentials see, so the
thing worth bounding is what it can **break**. That is also what Google's and Anthropic's servers
do — they simply have no way to narrow it.

The right reason to write any of this is *"I want this agent doing less than I can"* — scoping a
project, bounding an unattended run, keeping an experiment away from production documents. It is
**not** *"this is how my data is secured"*: anyone who can edit this configuration can also call
the Drive API directly. See [`SECURITY.md`](./SECURITY.md).

There is also a plainly practical reason: **a smaller world is a cleaner context.** Fewer
irrelevant search hits, less chance of the model reaching for the neighbouring document because
the name was similar, less window spent on things that were never relevant.

**The list lives in the configuration — there is no allowlist file.** That is a deliberate
restriction, not a missing feature: the client config is the artifact you control and can *see*,
so reading it tells you exactly what the agent may touch. A path would add an indirection whose
target can change without the config changing, put the real policy somewhere nobody looks, and
make the path itself a thing that can be mistyped or redirected. The cost is that a long list is
less pleasant in JSON than in a file. That is the trade.

Each variable is either `*`, or the document URLs themselves — newlines (`\n` in JSON) or commas
separating them, `#` starting a comment:

```bash
CSA_GW_ALLOWLIST_READ='*'
CSA_GW_ALLOWLIST_MODIFY='https://docs.google.com/document/d/AAA…/edit  # CCM mapping
https://docs.google.com/spreadsheets/d/BBB…/edit  # AICM tracker'
```

The comment is the *reason*, so a `git diff` of your config shows both what was granted and why.
A value of just `*` means every file, and logs a warning each time it is read, because
unrestricted access should be visible.

**Formatting is yours to choose.** Indentation, tabs, alignment and blank lines are all
insignificant, so line the reasons up into a column if that reads better. Whole-line comments
can be indented too. The *reason* is free text — apostrophes, quotes and further `#`s are fine
in it (whatever holds the value, JSON or a shell, has its own quoting rules to satisfy, and that
is a separate layer). A comment starts at a `#` that begins the line or **follows whitespace**,
which is what lets a URL keep an `#gid=0` or `#heading=h.x` fragment.

One thing it will *not* do quietly: a comment runs to the end of its line, so a second URL after
a comment — or two URLs on one line — is an **error**, not a dropped entry:

```
https://…/AAA/edit # tracker, https://…/BBB/edit # also    ← error: BBB is not being allowlisted
https://…/AAA/edit, https://…/BBB/edit  # both             ← error: only AAA would be listed
```

A policy with fewer files than its author believes fails closed, which is safe, but silently,
which is not good enough.

**Three outcomes, and the third one is the point.** A value is either `*` (everything), a set of
document URLs, or **unusable** — and unusable always means *nothing permitted*, never "ignore the
setting". Because "unusable" covers a lot of ground, the server says which kind it hit rather
than "invalid value":

| What you set | What you are told |
|---|---|
| nothing at all | `CSA_GW_ALLOWLIST_MODIFY is not set. It holds the list itself — there is no file to create.` |
| an empty value | `set but empty — which is not the same as unset. If it came from a config template or an unexpanded shell variable, that is the thing to fix.` |
| `…/document/d/` | `the URL stops after '/d/', so the file id is missing.` |
| `…/document/d/AAA…/edit` | `it contains '…', so it looks like a placeholder copied from documentation rather than a real link.` |
| a bare file id | `that looks like a bare file id rather than a URL … a link can be opened and checked by whoever reviews it.` |
| a folder URL | `folders are not supported in the allowlist yet. List the individual document URLs inside it instead.` |
| `https://example.com/x` | `the host is 'example.com', which is not a Google Docs or Drive address.` |
| a file path | `that looks like a file path. The allowlist is set in the environment, not read from a file.` |

Those texts arrive on stderr at startup **and** in the error from any tool that was refused — so
the model can relay the specific problem instead of "permission denied". The diagnosis itself is
deterministic rather than inferred, so it cannot be wrong about what it found.

Five more things worth knowing:

- **Unset means every file** — and *malformed* is what fails closed. Those are two different
  operators: unset is somebody who has not narrowed anything, malformed is somebody who **tried
  and failed**, and only the second can be detected. A bad URL, or a list whose every line is a
  comment, refuses and the server does not start; widening that to "everything" would hand them
  the opposite of what they wrote. The server still starts in the unset case — a startup crash
  reaches you as an opaque "server failed to start" — and warns on stderr that `*` grants access
  to every file the credentials can reach.
- **There is no file, and a path-shaped value says so** rather than being read or silently
  ignored.
- **Matching is by file id**, so every URL form for one document is one entry, and a **copy** of
  an allowlisted document has a different id and is *not* included. Entries survive renames and
  moves.
- **`search_files` results are filtered** to the read scope, not just made unopenable. A file
  outside it must not be *named* either, or search becomes a way to enumerate what the policy
  excludes.
- **An attempted-but-broken list fails closed.** One bad line, or a list with no usable entries,
  is a hard error and never a quiet fallback to unrestricted access. This is the narrow, true form
  of the "fails closed" claim; it does **not** extend to an unset variable — see the first bullet.
  *(Both of these bullets asserted the pre-v0.31.0 model until 2026-09-01, RR-003.)*
- **Folders are not supported yet** and a folder URL is rejected loudly rather than silently
  matching nothing. The reasons are involved enough to be written down — see `TODO.md`,
  *"Folders in the allowlist"*.

**Editing a spreadsheet is destructive, and no capability separates that out.** `update_cells`
overwrites whatever was in the range, `clear_cells` empties it, and `replace_text` with an empty
replacement blanks text — all under **`content.write`**. That is deliberate rather than an
oversight: blanking a cell is a fundamental editing operation, and withholding it does not prevent
the destruction, it makes somebody write `-` or `TBD` or `0` instead — which is worse, because a
blank cell is obviously empty and a placeholder looks like data. `clear_cells` exists precisely so
that does not happen: writing `""` leaves a cell *containing* an empty string, which anything
reading the sheet can tell apart from a cleared one.

So `content.delete` is a bound on **structural** destruction, not on destruction generally. What
bounds content destruction is **`CSA_GW_ALLOWLIST_MODIFY`** — by file, which is the honest control
here. And all of it is recoverable by a **human** through Drive revision history; what an agent
lacks is any undo it can reach itself.

*(This table previously grouped `clear_cells` under "Destroy content — `content.delete`, separate
from `content.write` so editing can be allowed and destruction refused". The gate was always
`content.write`, and the promise could not have been kept anyway, since `update_cells` destroys
just as thoroughly. Raised by audit 2026-09-01-02 as F2's sibling; the resolution was to correct
the claim rather than move the gate.)*

**`csa-google-workspace-mcp configure` writes this file for you**, with the absolute path
Desktop needs and your current `CSA_GW_*` variables carried across. It merges rather than
replaces, keeps a timestamped backup, and refuses rather than overwriting if the file does not
parse. `configure --print` shows the JSON without writing it.

**Claude Desktop has no shell**, so whatever is in its `claude_desktop_config.json` `env` block
*is* the server's entire environment — there is nowhere else for these to come from. Claude Code
takes them the same way, or via `claude mcp add -e KEY=VALUE`. Either way, ask the server what
it ended up with rather than guessing: read `csa-gw://config`, or call
`describe_configuration`.

**This is a first, deliberately simple control** — capability gating plus flat lists of
documents. It is not the last word: a broader model is being researched. What is here is meant
to be concrete and honest rather than complete.

<a id="why-an-isolated-install"></a>
**Why an isolated install (`uv tool` or `pipx`), not plain `pip`.** This is a CLI you run, not a
library you import, so it wants its own environment. `pip` into a shared or default virtualenv
works until another project disagrees about a dependency — `mcp>=2.1` here versus something else
pinning `mcp<2.0` is a conflict people actually hit.

Both isolating installers also make the console script **launchable from a GUI app** (see Claude
Desktop in the troubleshooting table), which a `pip install` into an activated virtualenv does
not: a GUI launches with neither your shell's `PATH` nor its `VIRTUAL_ENV`. They get there
differently — `pipx` writes an absolute Python shebang, while `uv` writes a `/bin/sh` trampoline
that `exec`s an absolute interpreter path — and both were checked here by running the installed
script under an **empty environment**, which is the property that actually matters.

Use `pip` when you are embedding the *library* in your own application, where you want it in your
environment.

Requires an **installed/desktop-app** OAuth client from your own Google Cloud project, with
the Drive, Docs, Sheets, and Slides APIs enabled — the same prerequisites as Google's own
Python quickstart. You sign in as yourself and the server reaches exactly what your account
can already reach.

**The server explains its own configuration.** Two resources and a tool, so nobody has to
guess — and so the model can explain a refusal instead of retrying it:

| | |
|---|---|
| `csa-gw://config` | the **effective** policy right now: what may be read, what may be changed, which mutation kinds are on, and — when something permits nothing — the diagnosis of why |
| `csa-gw://help/configuration` | the reference: every variable, the accepted forms, what each kind of mistake looks like, and the limits worth knowing before you hit them |
| `describe_configuration` | the same facts as structured output, for clients that do not surface resources — plus the version, OS, architecture, Python and install route. Needs no credentials, so it answers even when nothing else does |
| `report_a_problem` | assembles a bug report — version, OS, Python, install route, active policy — with **no file ids, titles or paths**, so it can be pasted into a public issue. The opposite choice from `describe_configuration`, which does list ids: same facts, different destination |

Allowlist *reasons* are deliberately absent from all three: they are written for whoever
reviews the configuration and may name people or unannounced work.

**Tools** — 58, each with structured output and read-only/destructive annotations
(`tests/test_readme_tools.py` keeps this list equal to what the server actually registers):

| | |
|---|---|
| **Find** | `search_files` · `list_recent_files` · `get_file_metadata` · `get_file_permissions` · `export_file_inventory` — the last one is the *work-handoff* question: a dated table of every file one person edited or commented on |
| **Read** | `read_file_content` · `read_range` · `download_file_content` · `list_slides` · `comments_by_cell` · `list_suggestions` · `list_notes` — the last one is a *different annotation type*: no author, no thread, not repliable, not resolvable |
| **Introspection** | `describe_configuration` · `describe_output_contract` — the second reports the **shape** results take: both result vocabularies (**open**, and they gain members), the export column list, and which of the two text renderings each tool returns. Call it before pinning anything about a payload, and again after upgrading |
| **Google-side controls** (read-only) | `list_protected_ranges` · `get_file_restrictions` · `get_shared_drive` — **what Google will refuse**, as against what this server is configured not to do. A protected range, `writersCanShare=false` or `driveMembersOnly` binds *every* client; our own gates bind only our own calls. Read-only by construction: there is no write counterpart and no capability that enables one |
| **Comment** | `list_comments` · `get_comment` · `create_comment` · `reply_comment` · `resolve_comment` · `reopen_comment` · `edit_comment` · `delete_comment` · `export_comments` · `apply_comment_actions` |
| **Write content** | `replace_text` · `append_text` · `insert_text` · `insert_slide_text` · `update_cells` · `append_rows` · `clear_cells` — all `content.write`, and **all destructive to what was there**; see above |
| **Tabs** | `list_tabs` · `add_tab` (Sheets) · `list_document_tabs` · `add_document_tab` (Docs) — different resources, deliberately different names |
| **Destroy structure** 🔒 | `delete_range` · `delete_tab` · `delete_document_tab` — `content.delete`. Separate from `content.write` because these reach what editing cannot: removing a tab or a Docs range. **Not a general "destruction" bound** — see the note below |
| **Create** | `create_file` · `copy_file` |
| **File lifecycle** 🔒 | `update_file` · `trash_file` · `share_file` · `update_file_permission` · `unshare_file` — each **on by default**, each still needing its capability *and* the file in the modify allowlist |
| **Access requests** | `list_access_proposals` · `resolve_access_proposal` 🔒 — answering "can I have access?"; approving is sharing, so it costs `file.share` |
| **Classification** | `list_labels` — Drive labels resolved to names. **Read-only by construction**: the write scope is never requested |
| **The server itself** | `describe_configuration` · `preview_allowlist` · `read_server_resource` · `authenticate` · `auth_status` · `whoami` · `report_a_problem` · `demonstration_plan` |

The find-and-read names and parameters match Google's Drive MCP server and the claude.ai Drive
connector, so habits transfer; `fileId` also accepts a share URL, which neither of theirs does.

**Authorizing without a terminal.** In a client that supports MCP URL elicitation (Claude Code
v2.1.76+), just ask for a document: the tool reports missing credentials, the model calls
`authenticate`, and you get a consent link in the conversation. `login` remains the path for
clients without elicitation — Claude Desktop today — and both clients share one token file, so
authorizing in either covers both.

**Environment:** `CSA_GW_TOKEN` (token cache, default `~/.csa_google_workspace/token.json`),
`CSA_GW_READ_ONLY=1` (refuse writes), `CSA_GW_CLIENT_SECRETS` (needed by `login` only, and
only to override the default `~/.csa_google_workspace/client_secret.json` — a cached token
carries its own client id and secret, so the running server never needs it).

`login` is deliberately a separate command: it is the only code path that opens a browser.
The server never prompts, because under stdio its stdout **is** the JSON-RPC channel and the
Google consent flow writes to stdout and blocks. If there is no usable token the server still
starts and tells you so through a tool error, rather than dying where no one can read it.

## Troubleshooting

| What you see | What it means |
|---|---|
| `Error 403: org_internal` — *"can only be used within its organization"* | The OAuth client is **Internal** to a Google Workspace organization and you signed in with an account outside it. Either pick an account in that organization (easy to get wrong if you have several), or create your own OAuth client. |
| `SERVICE_DISABLED` on some file types but not others | A scope grant is **not** API enablement. Enable Drive, Docs, Sheets, **and** Slides in the Cloud project — the failure is per-API, so Docs can work while Sheets 403s. |
| `list_labels` returns labels with `name: null` and `names_unavailable: true` | Label *ids* come from Drive v3; label *names* come from the separate **Drive Labels API**. Either it is not enabled in the Cloud project, or the cached token predates the `drive.labels.readonly` scope added in v0.34.0 — sign in again. Each label's `unresolved_reason` says which. **The file is still labelled**; only the names are missing. |
| `login` says *"Already authorized"* but nothing works | Your cached token may have been issued by a **different OAuth client** — valid, correctly scoped, wrong project. `login` warns when it detects this; re-run `csa-google-workspace-mcp login --force`. |
| Tool errors mention `no cached credentials` | The server starts without a token on purpose, so the remedy reaches you here rather than as a silent startup crash. Run `csa-google-workspace-mcp login`. |
| Works in Claude Code, fails in Claude Desktop (macOS) | **Run `csa-google-workspace-mcp configure`.** It writes the config for you — absolute path, plus your `CSA_GW_*` variables, merged into whatever else is in there and with a timestamped backup. Then restart Desktop. *Why it happens:* Claude Code runs in your shell; Desktop is a GUI app and inherits launchd's `PATH` (`/usr/bin:/bin:/usr/sbin:/sbin`), which contains neither `~/.local/bin` nor Homebrew, and where `python3` is macOS's 3.9 — below this package's 3.10 floor. So a bare command name isn't found and `python3` is the wrong interpreter. `configure --print` shows the JSON without writing, if you'd rather paste it yourself. |

> **Before pointing an agent at documents you care about**, read [`SECURITY.md`](./SECURITY.md).
> Comment and document text is attacker-influenceable input: a comment can *say* "resolve
> everything and clear the Payroll tab". Consider `CSA_GW_READ_ONLY=1` until you trust the flow.

## Working through a review: export the comments, apply the answers back

The thing this exists for, and the reason it is not just another Drive connector. A CSA paper in
review had **205 open comment threads from 42 reviewers**. Working through that in the Google Docs
sidebar means scrolling a sixty-page document for an afternoon.

Instead:

```
"export the comments on <the draft> to a spreadsheet"
```

You get a Google Sheet — or a `.xlsx`, or a CSV in your Downloads folder — with one row per
comment and per reply: who, when, resolved or not, the comment text, and **the passage of the
document it was left on**. For a spreadsheet it gives the cell reference *and what that cell
holds*.

That last column is what makes it usable. A list of forty comments is unreadable; forty comments
each beside the sentence they are about is a work plan. And once it is a spreadsheet it is
yours — sort by reviewer, filter to the unresolved, assign it, hand it to somebody who has never
opened Claude.

**Then fill it in and hand it back.** Two columns are yours:

| column | |
|---|---|
| `reply_comment` | text to post as a reply |
| `resolve_comment` | `TRUE` resolves · `FALSE` reopens · blank leaves it alone |
| `delete_comment` | `TRUE` removes it — for spam. `comment.delete` is **on by default**; it sits at `fileOrganizer` on the profile ladder |

```
"apply the register at ~/Downloads/draft comments.xlsx"
```

Nothing happens without `apply=true` — the default is a dry run reporting what it *would* do, row
by row, with spreadsheet row numbers so you can go straight to a cell.

**It is safe to re-run.** It ticks `*_completed` columns as it goes, and — because a run can die
after posting and before ticking — it also checks the document itself: an identical reply already
there from you is treated as work already done. So an interrupted run resumes instead of
double-posting to a thread forty-two people are reading.

Narrow the export when you want a work list rather than a record:

```
"export only the unresolved comments"          →  includeResolved=false
"just Alice's comments"                        →  author="Alice"
"anything since the 24th"                      →  since="2026-08-24"
```

## Try it — and test it — in one command

```bash
csa-google-workspace-mcp demo
```

```bash
csa-google-workspace-mcp demo --auto
```

The first narrates each step and waits; the second runs unattended.

It creates a dated folder in your Drive, then for **each** of a Doc, a Sheet and a deck:
creates the file, adds text, edits it, removes it, comments, replies, edits the comment,
resolves it, reopens it, deletes it, exports it, reads its permissions, copies it, renames it
and shares it — then searches for what it made and clears up after itself.

Every operation against every file type, on purpose: comments are one uniform Drive API across
the three, and content is three separate ones. That seam is where the bugs live.

**The demonstration is also this project's end-to-end test.** It runs against the in-memory
backend in CI on every commit, so it cannot rot between releases, and against real Google when
you run it. Coverage is computed from the server's own tool registry rather than a maintained
list, so "it exercises everything" stays true as tools are added:

```
74 steps ok, 1 skipped, 0 failed.
Tools exercised: 29 of 30 (30/30 counting the ones that cannot be automated).
```

Its first three real runs found four bugs that 660 unit tests had not: a successful
`delete_comment` reporting failure, `trash_file` refusing folders, a Drive 400 arriving with its
message suppressed, and a cleanup step that demonstrated tidying up without doing it.

At the end it asks what you thought, and can file that as a public GitHub issue labelled
`automated-feedback` — shown to you in full first, and never including a document name, link or
id. Skipping is one keypress.

**Two labels, because there are two kinds of report.** `automated-feedback` is a demonstration
run commenting on itself: unprompted, nobody blocked, and the signal is in the aggregate — twenty
runs skipping the same step is a design problem. `assisted-report`, from the `report_a_problem`
tool, means a person hit something and a model helped them describe it: somebody is stuck, and
those get read first.

## How this compares to the other Drive MCP servers

There are **many** other ways to reach Google Drive from an AI client, and **for many people
they are the better choice.** These tables exist so you can tell which one fits, not to argue
for this one.

The first comparison is against the two servers whose *tool names this project deliberately
matches* — Google's own and the claude.ai connector — because those are the ones a person
might swap this in for. [The wider field](#the-wider-field--every-drivedocs-mcp-server-we-could-find)
follows, and two of those community servers are **larger than this one**.

### Environment

| | [Google's Drive MCP](https://developers.google.com/workspace/drive/api/reference/mcp) | Claude's built-in Drive connector | **csa-google-workspace** |
|---|---|---|---|
| **Setup** | none — hosted | none — built in | `pipx install`, your own OAuth client, `login` |
| **Works with** | any MCP client | Claude | any MCP client (local stdio) |
| **OAuth scope** | `drive.file` / `drive.readonly` | — | **full `drive`** |
| **Runs on** | Google's servers | Anthropic's | your machine |

### Where this actually stands

Counting rather than claiming, because the table below is long enough to be miscounted:

| | Google's server | Claude's connector | **csa-google-workspace** |
|---|---|---|---|
| MCP tools | 8 | 11 | **58** |
| **Of their tools, we have** | **8 of 8** | **11 of 11** | — |
| Tools they do not have | — | — | **47** |

**Every tool either of them ships is here**, under the same name and the same argument shapes.
The twenty-three they do not have: **eleven** comment tools, five content-write tools,
`list_slides` and `list_suggestions`, four in which the server accounts for itself
(`describe_configuration`, `read_server_resource`, `authenticate`, `auth_status`, `whoami`,
`report_a_problem`), and
`demonstration_plan`.

**Counting tools is the wrong way to compare these three**, though, and that row is here mainly
to retire the question. The three that actually distinguish them are the ones Google
deliberately declines to offer — `update_file`, `share_file`, `trash_file`: the mutating, the
exfiltrating, the destructive. They exist here, and **each is off until an operator turns it on
by name**, with the file also listed for modify
([#82](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/82)). *Having* a
tool and *being permitted to call it* are separate facts in this server, and that is the
difference a tool count cannot show.

**Discovery landed 2026-08-25**, which was the gap that actually cost users something: a session
no longer has to begin with a pasted URL.

**What is genuinely further here** is depth on one axis rather than breadth. Neither of the
others can create, reply to, resolve or reopen a comment — Claude's connector can *inline*
comments into text it reads, which is a read, not a write. Ours are structured objects with
ids, authors, resolved state, replies, and the Sheets cell a comment is about. And of these
three, this is the only one that can **edit an existing document's content** — through the MCP
server as well as the library, since v0.13.0.

That last claim is about **these three servers**, and Google ships more than one. See the next
section, which bounds it properly.

### The wider field — every Drive/Docs MCP server we could find

**Surveyed 2026-08-31**, star counts and last-push dates read from the GitHub API, tool lists and
comment support read from each project's own tool reference or source — not from its README's
claims. `research/server-landscape.md` has the longer write-up.

| server | ★ | lang | last push | tools | comments |
|---|---|---|---|---|---|
| [taylorwilsdon/google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp) | 3095 | Python | 2026-08-30 | 12+ services | create · reply · resolve |
| [piotr-agier/google-drive-mcp](https://github.com/piotr-agier/google-drive-mcp) | 209 | TS | 2026-08-21 | **115** | Docs only: list · get · add · reply · delete |
| [a-bonus/google-docs-mcp](https://github.com/a-bonus/google-docs-mcp) | 649 | TS | 2026-08-10 | Docs·Sheets·Drive·Gmail·Cal | full CRUD, Docs **and** Sheets |
| [aaronsb/google-workspace-mcp](https://github.com/aaronsb/google-workspace-mcp) | 171 | TS | 2026-08-31 | Gmail·Cal·Drive | — |
| [isaacphi/mcp-gdrive](https://github.com/isaacphi/mcp-gdrive) | 283 | TS | **2025-05-07** | read + Sheets write | — |
| [felores/gdrive-mcp-server](https://github.com/felores/gdrive-mcp-server) | 72 | JS | **2025-11-07** | search · list · read | — |
| **csa-google-workspace** | — | Python | — | **40** | **full lifecycle + Sheets cell mapping** |

Smaller or single-purpose, listed so the survey is complete rather than flattering:
[dbuxton/google-docs-mcp](https://github.com/dbuxton/google-docs-mcp) (7★, Python, Apr 2026),
[phact/mcp-google-docs](https://github.com/phact/mcp-google-docs) (11★, stale Feb 2025),
[stanislawherjan1/gdocs-comments-mcp](https://github.com/stanislawherjan1/gdocs-comments-mcp)
(3★), [us-all/google-drive-mcp-server](https://github.com/us-all/google-drive-mcp-server) (0★).
Hosted platforms — **Composio, Klavis AI, Pipedream, Zapier** — wrap the same Drive API and expose
**file-level** comments only.

**Two of these are bigger than this project, and it is worth saying which.**
`taylorwilsdon` covers 12+ Google services with 3095★ and enterprise auth (service accounts,
Streamable HTTP). `piotr-agier` ships **115 tools** against this project's 58 — Shared Drives,
revisions, Sheets formatting, Slides authoring, PDF ingestion, Calendar. If you want breadth,
those are the answer and this is not.

**What is actually only here**, checked against each of the above rather than assumed:

- **A Sheets comment mapped to the cell it is about.** No MCP server can *create* a cell-anchored
  comment — the ceiling is Google's Drive API, not the servers, and `experiments/anchor-probe/`
  proved the anchor is an opaque `workbook-range` id. This project maps it anyway on the read
  side, by exporting XLSX and parsing `threadedComments`. `a-bonus` is the only other project
  that seriously engineers around the gap (deep-links plus native cell *notes*), and its
  read-side anchor parser does not match what real UI comments return.
- **The full comment lifecycle.** `resolve` **and** `reopen`, plus edit and soft-delete.
  `piotr-agier` has no resolve; `taylorwilsdon` has resolve but not edit, delete or reopen —
  its issues [#487](https://github.com/taylorwilsdon/google_workspace_mcp/issues/487) and
  [#788](https://github.com/taylorwilsdon/google_workspace_mcp/issues/788) are both still open.
- **`export_comments`** — a review register as a Google Sheet or CSV, with the passage or *cell
  contents* each comment is about. Nobody else has an equivalent.
- **A policy layer.** Eleven named capabilities, two file allowlists, `preview_allowlist`, and a
  **flavour switch** that publishes another vendor's exact tool surface. No other server here
  has anything comparable — most are all-or-nothing on your whole Drive.
- **A stated injection posture** — redacting `__repr__`s, untrusted-content rules in every tool
  description, and `THREAT_MODEL.md`.

None of that makes this the right pick for someone who wants Gmail and Calendar. It makes it the
right pick for **comment triage on documents**, which is what it was built for.

### Google ships eight of these now, not one

**Verified against Google's own documentation on 2026-08-27.** The comparison above is with
Google's **Drive** server, which is the right comparison for a Drive tool — but reading it as
*"Google cannot edit documents"* would be wrong, and increasingly so.

Google's Workspace MCP servers, all in the
[Developer Preview Program](https://developers.google.com/workspace/guides/configure-mcp-servers):

| Server | Endpoint | Edits existing content? |
|---|---|---|
| Drive | `drivemcp.googleapis.com` | **no** — 8 tools; read, search, create, copy. No comment tools |
| **Docs** | `docsmcp.googleapis.com` | **yes** — `update_doc` |
| **Sheets** | `sheetsmcp.googleapis.com` | **yes** — `update_values`, `update_formulas`, `insert_dimension` |
| **Slides** | `slidesmcp.googleapis.com` | **yes** — `update_presentation` |
| Gmail · Calendar · Chat · People | `gmailmcp` · `calendarmcp` · `chatmcp` · `people` | out of scope here |
| Universal | `workspacemcp.googleapis.com` | a combined surface over the above |

So **content editing is no longer a differentiator against Google as a whole** — only against its
Drive server. What is still not offered by any of them, as of the date above:

- **comments in any form** — not read as structured data, not written, on any of the eight
- **bulk comment export and apply-back**
- **suggestions**
- **a library underneath**, so the tool list is not the ceiling
- **configurable per-file and per-capability scoping** — theirs is bounded by OAuth scope instead,
  which is a different and often better trade (see *Environment* above)

**This table is the thing most likely to go stale in this README**, because it describes somebody
else's product. It carries a verification date for that reason, and the endpoints are canonical
so re-checking is mechanical rather than a research exercise. If you are reading this well after
the date above, assume it has moved.

### Tool-by-tool comparison

Where all three do the same thing they should use the same tool name and argument shapes, so
prompts and habits transfer. Verified against live schemas: Google's and Claude's shared tools
are identical in name *and* parameters; Claude's descriptions add model-facing guidance.

Every shared tool now uses the shared name and the shared parameters, so a prompt written
against Google's server or the claude.ai connector works here unchanged — with `fileId` also
accepting a share URL, which neither of theirs does.

| Tool | What it does | Google | Claude | Ours |
|---|---|---|---|---|
| `search_files` | Find files by Drive query | ✅ | ✅ | ✅ |
| `list_recent_files` | Recently touched files | ✅ | ✅ | ✅ |
| `get_file_metadata` | Name, type, owner, times, content snippet | ✅ | ✅ | ✅ |
| `get_file_permissions` | Who it is shared with, and at what role | ✅ | ✅ | ✅ ¹ |
| `read_file_content` | A file's text | ✅ | ✅ | ✅ ² |
| `download_file_content` | Raw bytes as base64, converted on the way out | ✅ | ✅ | ✅ |
| `create_file` | Create or upload a **new** file | ✅ | ✅ | ✅ ⁶ |
| `copy_file` | Duplicate a file | ✅ | ✅ | ✅ |
| `update_file` | Rename and move. **Metadata only** | ✗ | ✅ | ✅ ⁷ |
| `share_file` | Grant an address `reader`/`commenter`/`writer` | ✗ | ✅ | ✅ ⁷ |
| `update_file_permission` | Change a grant's role — usually a **downgrade** | ✗ | ✗ | ✅ ⁷ |
| `unshare_file` | Revoke a grant. Neither Google server can take a share back | ✗ | ✗ | ✅ ⁷ |
| `trash_file` | Move to trash. Not a permanent delete | ✗ | ✅ | ✅ ⁷ |
| `list_access_proposals` | Who has **asked** for access and is still waiting | ✗ | ✗ | ✅ |
| `resolve_access_proposal` | Approve or refuse a request. Approving **is** sharing | ✗ | ✗ | ✅ ⁷ |
| `list_labels` | **Classification** — Drive labels, resolved to names | ✗ | ✗ | ✅ |
| `preview_allowlist` | What the configured allowlists point at, **by name**, and what has died | ✗ | ✗ | ✅ |
| `list_tabs` · `add_tab` · `delete_tab` | Spreadsheet tabs — enumerate, create, destroy | ✗ | ✗ | ✅ |
| `list_document_tabs` · `add_document_tab` · `delete_document_tab` | **Google Docs tabs**, which nest | ✗ | ✗ | ✅ |
| `read_range` · `clear_cells` | One range in, one range emptied — without pulling the workbook | ✗ | ✗ | ✅ |
| `insert_text` · `delete_range` | Insert at a position; delete a span. Not the same as replace | ✗ | ✗ | ✅ |
| `list_comments`, `get_comment` | Comments as **structured objects** — ids, authors, resolved state, replies, cell | ✗ | *inline text only* | ✅ |
| `create_comment` | Post a comment | ✗ | ✗ | ✅ |
| `reply_comment` | Reply to a thread | ✗ | ✗ | ✅ |
| `resolve_comment`, `reopen_comment` | Close or reopen a thread | ✗ | ✗ | ✅ |
| `edit_comment` · `delete_comment` | Change or remove a comment — **the two Google gives no way to undo**, so both sit at `fileOrganizer` | ✗ | ✗ | ✅ |
| `list_slides` | A deck's slides, with speaker notes and shape ids | ✗ | ✗ | ✅ |
| `comments_by_cell` | Map a Sheets comment to **the cell it is about** | ✗ | ✗ | ✅ |
| `export_comments` | Every comment as **flat rows for a spreadsheet or another tool** — with the passage or the cell's contents | ✗ | ✗ | ✅ |
| `export_file_inventory` | A **dated snapshot of one person's document footprint** for a work handoff — every file they edited or commented on, with empty columns for your own summary and tags | ✗ | ✗ | ✅ |
| `apply_comment_actions` | Fill the register in and **apply it back** — bulk replies and resolves, safe to re-run | ✗ | ✗ | ✅ |
| `read_file_content(includeComments)` | Fold threads into the text where they were left | ✗ | ✅ | ✅ |
| `replace_text` · `append_text` · `update_cells` · `append_rows` · `insert_slide_text` | **Edit an existing** Doc, Sheet or deck | ✗ | ✗ | ✅ |
| `list_suggestions` · `read_file_content(suggestions=)` | Read suggestions, and preview a Doc as if they were accepted/rejected | ✗ | ✗ | ✅ ⁸ |
| `describe_configuration` + resources | The server explaining its own limits | ✗ | ✗ | ✅ |
| `report_a_problem` | A bug report that assembles itself, safe to publish | ✗ | ✗ | ✅ |
| `authenticate` | Browser consent from inside the MCP client | n/a *hosted* | n/a *built in* | ✅ |
| `auth_status` · `whoami` | Is this logged in, completely, and as whom — without a Google call | ✗ | ✗ | ✅ |
| — | Scope which files may be **read** | ⚠️ ³ | ✗ | ✅ |
| — | Scope which files may be **changed** | ⚠️ ⁴ | ✗ | ✅ |
| — | Turn individual **mutation kinds** off | ⚠️ ⁵ | ✗ | ✅ |

¹ Plus `public` / `writers` roll-ups.
² Reads Google Docs, Sheets and Slides — and does more with them than either of theirs, taking
`tab`, `suggestions` and `includeComments`. Metadata and raw bytes work on **any** file type.
Text extraction from uploaded PDF and Office files is on the roadmap — see *Formats* below.
³ Not configurable, but bounded by the **`drive.file`** scope, so Google enforces the
equivalent upstream — where it cannot be misconfigured.
⁴ Not configurable, but its only writes create *new* files, so there is nothing to scope.
⁵ Not configurable, but enforced instead by the tools it does not ship.
⁶ Creates Google-native files — Doc, Sheet, deck or folder — with an optional **Markdown** body
that Drive converts into real headings, lists and tables. Not arbitrary media upload: Google's
`drive.files.create` takes bytes, and this does not.
⁷ Present, and **on by default** — narrowing is what an operator configures (v0.31.0). Each needs
its own capability (`file.update`, `file.share`) *and* the file listed for modify, so an allowlist
bounds them even when the capability is on.

Where they sit on the profile ladder follows **recoverability**, not how alarming the verb sounds:
`file.update` (rename/move) and `file.trash` are reversible — a rename can be renamed back, and
Drive's bin holds a trashed file for 30 days for its owner to restore — so both are available from
**`writer`** upward. `file.share` is not, in effect: the grant is revocable but a copy the
recipient took is not, so it is **`organizer`** only. Drive draws the same line — its own Editor
cannot share either.

*(This footnote said "off in every profile but `full`" and that the "default `editor` profile
cannot rename, share or trash anything". All three parts were wrong by v0.31.0: nothing is off by
default, there is no default profile, and `writer` may rename and trash. It also contradicted the
profile table above it in this same file.)*
⁸ `list_suggestions` returns them as objects; `read_file_content(suggestions="accepted")`
renders what the document would say. **Neither accepts nor rejects** — the Docs API has no
endpoint for either, which is a Google limitation rather than a scoping decision, and the only
thing here reserved for a future UI-automation backend.

### The same table, by underlying API

Worth capturing separately, because the mapping is genuinely interesting: how little of Drive
any of the three servers touches, and how much of one capability lives in a single method.

| Tool | Google API |
|---|---|
| `search_files` | `drive.files.list` (`q=`) |
| `list_recent_files` | `drive.files.list` (`orderBy=`) |
| `get_file_metadata` | `drive.files.get` |
| `get_file_permissions` | `drive.permissions.list` |
| `read_file_content` | `drive.files.export` + `docs.documents.get` / `sheets.spreadsheets.values.get` / `slides.presentations.get` (+ `drive.comments.list` for `includeComments`) |
| `download_file_content` | `drive.files.export` (Google-native) · `drive.files.get(alt=media)` (uploaded) |
| `create_file` | `drive.files.create` + media upload |
| `copy_file` | `drive.files.copy` |
| `update_file` | `drive.files.update` (`name`, `parents`) |
| `share_file` | `drive.permissions.create` |
| `list_access_proposals` | `drive.accessproposals.list` |
| `list_labels` | `drive.files.listLabels` + `drivelabels.labels.get` (a **second API**) |
| `preview_allowlist` | `drive.files.get` per allowlist entry (no Google call when unrestricted) |
| `list_tabs` · `add_tab` · `delete_tab` | `sheets.spreadsheets.get` · `batchUpdate` (`addSheet` / `deleteSheet`) |
| `list_document_tabs` · `add_document_tab` · `delete_document_tab` | `docs.documents.get(includeTabsContent)` · `batchUpdate` (`addDocumentTab` / `deleteTab`) |
| `read_range` · `clear_cells` | `sheets.spreadsheets.values.get` · `.clear` |
| `insert_text` · `delete_range` | `docs.documents.batchUpdate` (`insertText` / `deleteContentRange`) |
| `resolve_access_proposal` | `drive.accessproposals.resolve` |
| `trash_file` | `drive.files.update` (`trashed=true`) |
| `list_comments`, `get_comment` | `drive.comments.list` / `.get` |
| `create_comment` | `drive.comments.create` |
| `reply_comment` | `drive.replies.create` |
| `resolve_comment`, `reopen_comment` | `drive.replies.create` — an **action reply**, never a PATCH |
| `comments_by_cell` | `drive.files.export` (XLSX) → parse `threadedComments` XML → A1 |
| Edit an existing Doc | `docs.documents.batchUpdate` |
| Edit an existing Sheet | `sheets.spreadsheets.values.update` / `.append` / `.clear` |
| Edit an existing deck | `slides.presentations.batchUpdate` |
| Suggestions preview | `docs.documents.get(suggestionsViewMode=…)` |
| `authenticate` | OAuth loopback + MCP URL elicitation |
| `auth_status` | none — reads the local token cache, no API call |
| `whoami` | `drive.about.get(fields=user)` |
| The three scoping controls | none — enforced in this library, before the API call |

Two things fall out of reading that column. **`drive.files.list` does the work of two tools** —
discovery is one method with different parameters. And **`drive.replies.create` is both replying
and resolving**, because resolve is an *action reply* rather than a state change; that quirk is
probe-verified, and it is why the capability gate for it has to inspect the call's arguments
rather than its name.

On footnote ², and on `includeComments`. Our `read_file_content` reaches **Google-native types
only** — Docs, Sheets, Slides — not their 13 mime types. Drive *will* convert a PDF or a PNG
into a Doc by OCR, but doing that **creates a file**, so it is not a read and does not belong
behind a read-only tool; reaching those types honestly needs local extraction. And
`includeComments` anchors a thread by **unique quoted-text match**, because the Drive comment
anchor is an opaque range id with no decodable position — a quote appearing twice, or not at
all, is reported unanchored rather than guessed.

**Neither of the others can edit an existing file's content.** `create_file` uploads a *new*
file; `update_file` only renames or moves. Read down the `batchUpdate` rows — that is the
difference, and it is structural rather than a matter of tool count.

### Formats: Google-native today, more on the way

**This server is built for the documents teams actually draft in — Google Docs, Sheets and
Slides — and on those it goes considerably further than either alternative:** comments as
structured objects with authors and resolved state, bulk export and apply-back, content editing,
suggestions review, Sheets cell mapping, and a policy that can scope every bit of it.

Uploaded files are handled too: **`get_file_metadata` and `download_file_content` work on any
file type** — a PDF, a `.docx`, an image, a folder. Extracting *text* from those is Google-native
for now, and is a **1.0.0** item. Python has mature readers for all of it; the reason it is being
sequenced rather than simply switched on is that the risk differs sharply by format:

| | how | risk |
|---|---|---|
| **`.docx` · `.xlsx` · `.pptx` · `.odt`** | zip + XML, via `python-docx` / `openpyxl` / `python-pptx` | **lowest, and already precedented here** — `_cellmap.py` parses XLSX today with `defusedxml` plus caps on member size, total size and member count. The pattern exists; this reuses it |
| **Convert in Drive, then read** | `files.copy` with a Google-native target mime | **no parsing at all** — Google does it. Costs a created file, so it needs `file.create`, and Drive's OCR covers PDF and images too |
| **PDF text in-process** | `pypdf` / `pdfplumber` / PyMuPDF | **highest.** A complex binary format with embedded streams and a long CVE history in every parser. This is the one `SECURITY.md`'s primary-risk argument is really about |
| **OCR for images** | `pytesseract` + a Tesseract binary | out of scope — a native dependency and variable output |

The likely shape: Office formats in-process behind the hardening already proven in
`_cellmap.py`, PDF and images through Drive's own conversion where nothing is parsed here at all,
and in-process PDF parsing argued separately on its merits. Tracked as **C5** in
[`TODO.md`](./TODO.md).

### Markdown out, Markdown in

A Google Doc exports as `text/markdown` — `download_file_content(exportMimeType="markdown")`,
or `Doc.as_markdown()` in the library. It is Drive's own conversion, so headings, lists, tables
and links survive, unlike `as_text()`, which is text runs only.

That turns a Doc into a usable *source* for a Markdown toolchain rather than a dead end. CSA's
internal **`document-pipeline`** plugin already consumes exactly this: Markdown → tagged
**PDF/UA-1**, with a design-rule preflight, composition review, citations and CSA brand styling.
**A public version is planned.** Drive also *imports* `text/markdown` back into a Doc, so the
loop closes:

```
Google Doc --export markdown--> document-pipeline --> branded, accessible PDF/UA-1
     ^                                                              |
     +------- import markdown (create_file content=) <-- revised ---+
```

Draft and review where the comments are, typeset where the brand rules are, put the result back
where it can be reviewed again. **Both halves ship today**: out through
`download_file_content(exportMimeType="markdown")`, back in through `create_file(content=…)`,
which hands Drive Markdown and gets a Doc with real structure rather than one long text run.

**Formats differ by file type**, and the table is probed rather than assumed
([`experiments/export-formats/RESULTS.md`](./experiments/export-formats/RESULTS.md)):

| Type | Exports as |
|---|---|
| **Docs** | `markdown` · `pdf` · `docx` · `odt` · `html` · `rtf` · `epub` · `txt` · `zip` |
| **Sheets** | `csv` · `tsv` · `xlsx` · `ods` · `pdf` · `zip` |
| **Slides** | `pdf` · `pptx` · `odp` · `txt` — **no Markdown, no HTML** |

Ask for one a file cannot produce and the error names the ones it can, rather than becoming a
400 from Google.

### Planned — capabilities no server exposes yet

The Google APIs reach considerably further than **any** server in the field currently does —
see [the wider field](#the-wider-field--every-drivedocs-mcp-server-we-could-find) for who else is
in it. These are the ones worth building, in the same format, with the tool names they would ship
under.
Sequencing is in [`TODO.md`](./TODO.md); the two tables together are the roadmap.

| Tool | What it does | Google API | Google | Claude | Our tool |
|---|---|---|---|---|---|
| `list_approvals` | Approvals open on a file, with reviewers and state | `drive.approvals.list` / `.get` | ✗ | ✗ | ✗ *planned* |
| `start_approval` | Ask named reviewers to approve a document, with a due date | `drive.approvals.start` | ✗ | ✗ | ✗ *planned* |
| `respond_to_approval` | Approve, decline, or comment on an approval as a reviewer | `drive.approvals.approve` / `.decline` / `.comment` | ✗ | ✗ | ✗ *planned* |
| `reassign_approval` | Hand a review to someone else; cancel one you started | `drive.approvals.reassign` / `.cancel` | ✗ | ✗ | ✗ *planned* |
| `list_revisions` | Version history — who changed what, when | `drive.revisions.list` / `.get` | ✗ | ✗ | ✗ *planned* |
| `read_revision` | The text of an earlier version, so two can be compared | `drive.revisions.get` (+ export) | ✗ | ✗ | ✗ *planned* |
| `pin_revision` | Mark a version `keepForever` so autocleanup cannot drop it | `drive.revisions.update` | ✗ | ✗ | ✗ *planned* |
| `list_changes` | What changed across a Drive since a token — a sweep that reads only the delta | `drive.changes.list` + `getStartPageToken` | ✗ | ✗ | ✗ *planned* |
| `get_slide_image` | Render a slide to a PNG, so a model can actually *see* a deck | `slides…pages.getThumbnail` | ✗ | ✗ | ✗ *planned* |
| `find_named_range` · `annotate_range` | Durable anchors that survive edits, instead of fragile A1 ranges and character offsets | `docs` named ranges · `sheets…developerMetadata` | ✗ | ✗ | ✗ *planned* |
| **Docs structure & formatting** | Tables, styles, headers/footers, footnotes, bullets, images, page breaks, tabs, smart chips — **37 of `batchUpdate`'s 40 request types are unused by anybody** | `docs.documents.batchUpdate` | ✗ | ✗ | ✅ 3 of 40 |

That last row is the largest gap in the whole comparison, and the most direct answer to "help
me get work done".

**Correction, 2026-08-31.** This used to read *"today no MCP server can add a table to a
document"*. That is **no longer true**, and it was the kind of claim that ages badly without
anyone noticing: `piotr-agier/google-drive-mcp` ships `insertTable`, `editTableCell`,
`insertImageFromUrl`, `applyTextStyle`, `applyParagraphStyle` and `createParagraphBullets`, read
from its own `docs/tools.md`. The `batchUpdate` surface is still mostly unused across the field,
and it is still the biggest gap **here** — but the field has moved and this project has not moved
with it.

**Waiting on a hosted variant.** `drive.files.watch` and `changes.watch` deliver *push*
notifications — react the moment a comment appears, rather than polling for it. They require a
publicly reachable HTTPS endpoint on a verified domain, which a local stdio process behind NAT
cannot be. So this is **planned for a hosted MCP server**, which is itself on the roadmap and
is a substantial piece of work in its own right: multi-user OAuth, per-user Google token
custody, and a public attack surface all arrive with it. See `TODO.md`. `list_changes` polling
covers the same ground locally in the meantime.

**Shipped since this table was written.** `list_labels` (v0.34.0) reads Drive labels, resolving
them to real names through the separate Drive Labels API — so the labels row left this table
rather than staying in it as a plan.

**Deliberately refused, not merely unplanned: `set_file_labels`.** This library never requests the
`drive.labels` write scope, only `.readonly`, so there is no configuration in which a model can
change a classification. Labels are what DLP and retention policies key on — setting one is not an
edit to a document, it is a claim about how the organisation must treat it, and unlike a bad edit
nobody sees a diff.

**Not planned at all.** Shared-drive administration (`drives.*`), permanent deletion
(`files.delete`, `emptyTrash` — both Google's and Claude's stop at trash, and that is a considered
line), and client-side-encryption tokens. None of them help anyone review a document.

**Use Google's or Claude's if** you want zero setup, you are reading rather than editing, you
need PDFs/images/Office files, or you would rather not hand a local tool full-Drive scope.
Google's takes only `drive.file`, which means it can reach *only* files you explicitly pick —
a genuinely stronger safety property than anything this library can offer itself.

**Use this one if** you need to *change* documents or *work* comments: reply, resolve, reopen,
map a Sheets comment back to its cell, or preview a Doc with suggestions applied. Neither of
the others can edit an existing file's content at all — and that, rather than tool count, is
the difference.

They are complementary. Running Google's connector for discovery and this one for editing is a
perfectly sensible arrangement, and a planned *flavour* switch will let this server restrict
itself to either of their capability sets when you want one predictable surface.

Details, including per-tool behaviour read from live schemas:
[`research/drive-mcp-servers-and-api-surface.md`](./research/drive-mcp-servers-and-api-surface.md).

## Why this exposes everything the API can do

**A design goal, not an oversight: this project aims to expose every capability the Google
Workspace APIs offer.** People adopt AI tooling to get work done, and the tool has to be able to
do the work.

That is not in tension with the security posture, for a reason worth being explicit about:
**withholding a capability does not prevent the action.** Every action here is one the
authorizing user can already perform in a browser or in fifty lines of their own Python against
the same API. Leaving a method out does not stop anybody — it sends them to a client with no
policy layer, no allowlist, no tool annotations and no logging. Capability withheld is utility
lost and risk unchanged.

What this *does* add is a **decision path**: a third party who can leave a comment can influence
what an agent does with authority that was never theirs. That is real, it is the reason the
controls exist, and it is the part we own. See [`SECURITY.md`](./SECURITY.md) — including why the
profiles are best understood as a **privilege simulator** (let the agent act as a less-privileged
user than you are) rather than as a fence, and where the industry-level gap sits: access control
today authenticates *identity* and authorizes *actions*, and has no concept of *intention* or of
*which tool is acting*.

## What "full API coverage" means here — and where it stops

**The commitment: 100% of the API endpoints we can *see and test* from our own Google tenant.**
That tenant is not an enterprise-tier account, so **some things will be missing** — and rather
than leave that as a vague disclaimer, the rest of this section says exactly what kind of missing.

**"This cannot do that" should never be a technical answer.** The intended answer is *"that is
risky, so it is gated off and disabled by default — and it can be switched on."* Whether to let
an AI do something is a business and risk decision, and a missing implementation makes that
decision silently, on your behalf, while looking like a fact about the world.

### Coverage has layers, and only one of them is knowable from here

| layer | how you would find out |
|---|---|
| **published** | the discovery document — **static**, byte-identical with and without credentials, so it describes the API and never *your* account |
| **reachable by us** | try it and read the refusal. This is what we cover |
| **exists but invisible to us** | only by clearing the layer above first |

The third is real: Google's **native comment APIs are absent from every discovery document** and
were found only by sending candidate request names and reading the difference between *"No
request set"* (accepted, dispatch disabled) and *"Unknown name"* (not a field).

And **the first barrier masks the rest.** `driveactivity`, `admin.directory`, `vault` and
`cloudidentity` all refuse identically — `403 PERMISSION_DENIED, insufficient authentication
scopes` — so whether an **admin** or an **edition** is *also* required cannot be known until the
scope is held. We therefore do not claim to know which gaps are enterprise-only. We know what we
can reach.

### Want enterprise-tier coverage? Please open an issue — and here is how to make it actionable

We cannot write coverage we cannot verify, and the blocker is **verification, not code**.

1. **[Open an issue](https://github.com/CloudSecurityAlliance/csa-google-workspace/issues/new)**
   saying what you need and what tier you are on.
2. **Run `python scripts/report_api_reach.py` and paste the output.** It reports what *your*
   tenant can reach — method names and refusal codes only. **No file ids, no titles, no email
   addresses, no paths**, the same rule `report_a_problem` follows, because it is written to be
   pasted into a public tracker.
3. If you can run a probe against your own tenant, that measurement is worth more than any
   amount of our reasoning — this project has been wrong three times about what Google's
   documentation says, and right every time it measured.

Untested coverage may also ship **explicitly marked as untested**, rather than being withheld:
not working, not broken, *unknown* — and never reported as the first.

### The genuine limits today, and whose they are

| | |
|---|---|
| **Accepting or rejecting a suggestion** | **Google's, and gated rather than impossible.** `acceptSuggestion` / `rejectSuggestion` exist and are gated behind Google's **Developer Preview Program** (measured 2026-09-02). We are not enrolled. `Doc.suggestions` and `as_text(suggestions=…)` read and preview. *(This README previously said Google exposed no endpoint and a `PlaywrightBackend` was required. That was true of the published surface when written and stopped being true without anybody noticing.)* |
| **Cell-anchored comment creation** | **Google's, on the GA surface.** An anchor sent through Drive is stored verbatim and then treated as *un-anchored* by the editors — it appears to work and does not (measured 2026-07-09). Sheets `insertComment.coordinate` is real and preview-gated. `create_comment(cell=…)` posts a file-level comment with a `#gid=…&range=…` deep link. **Nuance measured 2026-09-03:** a Docs comment *reusing* a real `kix.*` anchor from an existing comment **is** honoured — minting fails, reuse works. |
| **Changing a file's or drive's access settings** | **Ours, and being reconsidered.** `writersCanShare`, `copyRequiresWriterPermission` and shared-drive restrictions are now **readable** (`get_file_restrictions`, `get_shared_drive`) and not writable. These are *meta-permissions* — policy about who may set policy — and the write side is **proposed** to arrive behind a `drive.admin` capability that would ship switched off, because a mistake there is not recoverable by Drive's trash or its revision history. Not built yet. |
| **Making something public** | **Ours, deliberately, today.** `type="anyone"` is unreachable — `permissions.py` requires an email address — as a control against inducing a permission grant to an attacker-chosen address. **Proposed** to become a `share.public` capability that would ship switched off, because *re-restricting is not un-publishing*. Not built yet. |
| **Writing Drive labels** | **Ours, and structural.** The `drive.labels` write scope is never requested, so no configuration permits relabelling. Unlike the rows above, a capability gate would **not** be equivalent: a gate binds this library's calls and does nothing for a stolen token, so the narrow scope is the control. |

The programme, its sequencing and the reversals it involves:
[`docs/superpowers/specs/2026-09-03-full-api-coverage-and-admin-capabilities.md`](docs/superpowers/specs/2026-09-03-full-api-coverage-and-admin-capabilities.md).

## Using it on a user's behalf (production)

This library is a building block for MCP servers / agents / automations acting **on a user's behalf** with a full-Drive token. Before deploying, read [`SECURITY.md`](./SECURITY.md) — prompt injection through document/comment content is the primary risk. In short:

- **Credential seam:** the line is *whose machine holds the token*, not CLI-vs-server. Local single-user use — a CLI, or the bundled MCP server over stdio — is fine with `from_oauth` + `token.json` (`0o600`). **Hosted, multi-user is not:** `run_local_server()` can't run headless and one file can't isolate many users. There the host runs its own OAuth, keeps per-user tokens in a secret store, and passes ready credentials via **`Workspace.from_credentials(creds)`**.
- **Concurrency:** one `Workspace` per request/user; never share a `Workspace` (or its backend) across threads — `googleapiclient` clients aren't thread-safe. The stack is synchronous; wrap calls in `asyncio.to_thread(...)` from async code.
- **Isolation & least authority:** a `Workspace` binds one user's credentials — never reuse it across users. Default to `read_only=True` and escalate to a write-capable `Workspace` deliberately, per operation.

## Documents

| Document | What it is |
|----------|------------|
| [`API-STABILITY.md`](./API-STABILITY.md) | **What will not break.** The MCP tool surface is the contract; the Python API is best-effort. SemVer as applied here, what is deliberately unstable, and what you are owed when something changes. |
| [`docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md`](./docs/superpowers/specs/2026-07-20-csa-google-workspace-design.md) | **The design spec.** Scope, two-axis architecture, API surface, error model, phasing. |
| [`docs/superpowers/plans/`](./docs/superpowers/plans/) | The six phased, TDD implementation plans (foundations · comments · content read · cell-mapping · content write · suggestions read). |
| [`research/google-drive-comments-reference.md`](./research/google-drive-comments-reference.md) | Canonical reference on how Drive/Sheets comments actually work: the 10 API methods, fields, resolution/deletion models, OAuth scopes, and the hard truth about the `anchor` field. |
| [`research/docs-suggestions-reference.md`](./research/docs-suggestions-reference.md) | How Docs **suggestions** behave: readable (incl. accepted/rejected previews), but **no accept/reject endpoint** and no author exposed. |
| [`research/server-landscape.md`](./research/server-landscape.md) | Source-verified survey of prior-art servers that handle Google comments. |
| [`docs/superpowers/specs/2026-07-23-mcp-server-design.md`](./docs/superpowers/specs/2026-07-23-mcp-server-design.md) | **The MCP server spec** (phase 2). Transport, tool surface, config, error mapping, security posture. |
| [`research/mcp-server-design.md`](./research/mcp-server-design.md) · [`research/mcp-protocol-notes.md`](./research/mcp-protocol-notes.md) | **Superseded** by the spec above — earlier MCP design + protocol notes, kept for history only. |
| [`docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md`](./docs/superpowers/specs/2026-08-25-library-structure-for-the-roadmap.md) | **Shape review before growth.** The library has one axis (per-file); the roadmap adds a second (account-scoped). Where each planned item lands, and what must not happen. |
| [`research/drive-mcp-servers-and-api-surface.md`](./research/drive-mcp-servers-and-api-surface.md) | What Google's and the claude.ai connector's tools **actually** do, read from live schemas, plus the full Drive v3 / Docs v1 method inventory. |
| [`experiments/`](./experiments/) | Runnable **empirical probes** (with dated `RESULTS.md`): `anchor-probe`, `comment-lifecycle`, `docs-suggestions`, `sheets-cellmap`, `export-formats`. Probe beats docs. |
| [`docs/superpowers/specs/2026-09-05-conformance-rig.md`](./docs/superpowers/specs/2026-09-05-conformance-rig.md) | **The dedicated test machine.** What CI cannot run and why that matters — every comment write was broken for five releases under green CI. Setup is [`Setup-test-machine.sh`](./Setup-test-machine.sh), running it is [`Run-full-test-suite.sh`](./Run-full-test-suite.sh), and the quickstart is [above](#a-dedicated-conformance-machine). |
| [`CHANGELOG.md`](./CHANGELOG.md) | What changed in each refresh, and why. Headings say which versions were actually published. |
| [`PROVENANCE.md`](./PROVENANCE.md) | Who built this and how, how to verify a release's attestation yourself, the yank policy, and what the secret scanners say about the history. |
| [`docs/DECISIONS.md`](./docs/DECISIONS.md) | An index of decisions — when each was settled, what evidence settled it, and which earlier belief it replaced. |

## Why comment retrieval is trickier than it looks

If you have tried to build comment tooling against Google Workspace and it did not work properly,
**that is the expected outcome, and it is not your fault.** The obvious approach fails in ways
that look like success — which is the worst failure mode, because nothing errors.

This section is the short version. Every claim here is either **measured** against live Google or
sourced, and the long version lives in
[`research/google-drive-comments-reference.md`](./research/google-drive-comments-reference.md),
[`research/comments-apis-2026-09.md`](./research/comments-apis-2026-09.md) and the runnable probes
in [`experiments/`](./experiments/). Where Google's documentation and a probe disagree, the probe
wins.

### The anchor is a key, not a coordinate — except on Slides

On two of the three editors an anchor tells you *that* a comment is attached to something,
without telling you **where**. On the third it tells you exactly where, and that asymmetry is
easy to miss because the field has one name.

- **Docs**: `kix.ce7ypxwipivp` — an opaque id, not JSON, carrying no position (measured 2026-09-02)
- **Sheets**: `{"type":"workbook-range","uid":0,"range":"1453957822"}` — structured, but `range` is
  an opaque internal id and **not** decodable to `B11` (measured 2026-07-09)
- **Slides**: `{"type":"shape","subtype":"text","page":"p","targets":["zooShape1"]}` — **resolvable.**
  `targets` names real object ids that appear verbatim in `presentations.get` (measured 2026-09-05)

Two traps in the Slides one, both measured. **`page` names the SLIDE, not the page the target
lives on** — a comment on the speaker notes still reports `"page": "p"`, and only resolving
`targets` reveals it belongs to `p:notes`, so code that trusts `page` reports a note about the
narration as a note about the deck. And **a comment in a table cell anchors to the table**, with
no row or column anywhere; the quoted word is the only cell-level signal there is.

**Google's own published example does not match what the editors produce.** The guide shows
`{"region": {"kind": "drive#commentRegion", "line": <n>, "rev": "head"}}` — a real position. No UI
comment we have ever seen looks like that. Code written from the documentation will parse
something that never arrives.

Google also states plainly that anchors are immutable and *"position relative to content cannot be
guaranteed between revisions"* — so the anchor is documented as a **hint**, not ground truth.

### Writing an anchor appears to work and does not

You can send an anchor with a comment. Drive **stores it verbatim** and returns it to you intact —
so a round-trip test passes. But the editors treat a custom anchor as **unanchored**: in the UI the
comment lands on A1, or floats free.

Google says so — *"Google Workspace editor apps treat these comments as un-anchored comments"* —
and it is measured in [`experiments/anchor-probe/`](./experiments/anchor-probe/). This is the trap
that has defeated several other implementations, because the API gives no error at all.

### So which cell is a Sheets comment on? Export the spreadsheet and parse it

There is no API that tells you. The reliable route is: export as `.xlsx`, unzip, parse
`xl/threadedComments/threadedComment*.xml`, and read the `ref` — which **is** real A1 notation.

This library does that for you (`comment.location`, `sheet.comments_by_cell()`), and three things
inside it are worth knowing before anyone reimplements it:

- to learn **which tab** a comment is on you must walk `workbook.xml` →
  `_rels/workbook.xml.rels` → each sheet's rels → its `threadedComments` part;
- **`r:id` is not sequential** — a real Google export numbers the *first* sheet `rId5`, so
  guessing the mapping gives you the wrong tab;
- relationship `Target`s are **relative**, and a sheet with no comments has no relationship at all.

It degrades asymmetrically on purpose: a damaged graph costs you the *tab*, never the *cell*, and
an unresolved tab stays empty rather than defaulting to the first sheet.

### Four different things arrive as a comment, and `quoted_text` distinguishes none of them

Anchor presence and quoted-text presence are **independent**, so there are four combinations —
and most code looks at the quoted text, which separates none of them:

| situation | `anchor_state` | `anchored` | `quoted_text` | made by |
|---|---|---|---|---|
| a comment on the **whole file** | `file` | `false` | empty | editor or API |
| attached to a **non-text object** — an image, a cell | `object` | `true` | empty | editor |
| attached to text | `text` | `true` | the text | editor |
| **a quote with no anchor** | `quote_only` | `true` | **the text** | **API only** |

Conflating the first two turns *"look here, carefully"* into *"there is nothing to look at."*
Drive **omits** absent fields rather than sending `null`, so absence has exactly one form.

**The fourth one is the trap, and it is not rare.** A consumer measured 4 of 90 threads on one
real document in this state, one carrying a 244-character quotation. It exists because
`comments.create` accepts a quote with no anchor — and because an API-supplied anchor is stored
and then ignored by the editors, a tool that knows this drops the anchor and keeps the quote.
**So it appears on any file another tool has written to.** Read it as file-level and you skip
exactly the comments somebody quoted at length.

`anchored` here answers *"is there a passage?"*, and `anchor_state` says which of the four.
*(`anchored` was raw anchor presence until v0.43.0, which reported `false` on those 244
characters — the bug this table now exists to prevent.)*

### The editor quietly fixes sloppy selections, which helps

Measured 2026-09-02: comment with **nothing selected** and Docs expands the anchor to the
enclosing **word**. Try to comment on an empty paragraph and Docs **refuses** — no comment box
appears at all.

So there is no "anchored but nothing selected" state for text, and quoted text is available
wherever text is. That is what makes `context=true` possible at all.

### But a short quote may not be placeable

Because the anchor carries no position, a comment can only be located by finding its quoted text —
and if that text occurs **more than once**, there is no tiebreaker. A one-word quote is ambiguous
almost immediately: in a **nine-paragraph** test document, the word a caret snapped to occurred
four times.

So the comments that most need context are the ones most at risk of not getting any. This library
reports that as `context_kind: "ambiguous"` with the **candidate locations**, rather than picking
one — a marker in the wrong place is worse than no marker, because it is not visibly wrong.

### Notes are not comments, and a file full of notes reports zero comments

A Sheets **note** has no author, no thread, and cannot be replied to or resolved. The Drive
comments API **does not see notes at all** — measured: a file carrying a note returns *zero*
comments.

A tool that reports "no comments" on a sheet covered in notes is telling the truth and giving
exactly the wrong impression. Use `list_notes`, and `export_comments` will tell you in `caveats`
when it is not showing them.

### Other measured behaviours that break naive code

- **`resolved` is absent** on a comment that was never resolved — not `false`. Read a missing
  field as unresolved, or every open thread looks broken.
- **Soft delete strips the content *and* the author.** A deleted comment is a tombstone: the id
  and timestamps survive, the rest does not. Models have to allow it.
- **Resolve and reopen are replies**, not a `PATCH` — an "action reply" that may carry no text at
  all. A blank reply is a state change, not a mistake.
- **`author.email` is usually absent even when you request it**, so "everything Bob said" is
  really "everything by this display name" — which is neither unique nor stable.
- **`mentionedEmailAddresses` and `assigneeEmailAddress` exist but only if you ask.** Omit them
  from the field mask and structured @mentions look like they do not exist. We concluded exactly
  that in an early probe and were wrong.
- **Every comments method requires an explicit `fields` spec**, and `replies` alone returns
  replies *empty* — the sub-fields have to be named.

### And there is no cross-file comment search

`comments.list` is a sub-resource of a single file. There is no `/comments` collection, and
`files.list`'s query language has no comment predicate. *"Show me everything Bob said across these
forty documents"* requires iterating files and joining locally — which is **absent by
construction**, not merely missing. Google could not ship it in their own server without building
the same thing.

## Three things worth knowing

1. **Comments are a Google Drive API v3 concern — not the Sheets/Docs/Slides APIs** (those handle content). One comment API serves all three file types. (Sheets *notes* are separate and out of scope.) *(As of 2026-09 the editor APIs **do** have native comment surfaces, in Developer Preview — see [`research/comments-apis-2026-09.md`](./research/comments-apis-2026-09.md). This statement describes what this library uses, which is Drive, deliberately.)*
2. **You cannot anchor a comment to a specific Sheets cell via the API.** Google treats API-created anchors as unanchored; the real anchor is a `workbook-range` with an opaque id. Mapping a comment back to a cell requires exporting the sheet as XLSX and parsing the comment XML — the central hard problem, which the library solves (best-effort) via `comment.location` / `sheet.comments_by_cell()`.
3. **The space isn't greenfield, so the value is in the hard parts** — reliable read-side cell mapping and clean Docs/Sheets/Slides coverage — not merely "supporting comments." See [`server-landscape.md`](./research/server-landscape.md).

## Development

```bash
pip install -e ".[dev]"       # from a clone; src/ layout, Python >=3.10
pytest -q                      # unit suite: no network, no credentials (in-memory FakeBackend)
ruff check src tests && mypy   # lint + type-check (the CI `lint` job)
```

Everything above runs offline and gates CI. Two **opt-in** suites exercise real Google and
are skipped unless their env vars are set:

```bash
# Live API suite — real Docs/Sheets/Slides/Drive. Needs OAuth client secrets; a cached token
# avoids re-consent, otherwise the first run opens a browser to log in:
CSA_GW_INTEGRATION=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/integration/

# Interactive OAuth suite — the login flow itself (token caching, file permissions, read-only
# contract). Separate because it needs a human at a browser + touches the sensitive token:
CSA_GW_OAUTH=1 CSA_GW_CLIENT_SECRETS=path/to/client_secret.json pytest tests/oauth/
```

The client secret must be an **installed/desktop-app** OAuth client, and Drive, Docs, Sheets,
and Slides must be enabled in its Cloud project (a scoped token still 403s until each API is
enabled). `client_secret.json` and `token*.json` are gitignored — never commit them.
Releasing is documented in [`RELEASING.md`](./RELEASING.md).

### A dedicated conformance machine

Those two opt-in suites are the ones that catch what CI cannot, and being opt-in is exactly why
they rot. Every comment write in this library was broken from v0.47.0 to v0.51.0 — five releases,
green CI throughout — and `tests/integration/` would have caught it on its **first** test. It had
not been run in five releases, and when it finally was, it turned out to be broken itself.

So there is a rig: a dedicated Mac that installs **the current PyPI release**, proves it is
testing that wheel and not a checkout, runs the live layers, and files one issue per failure.

**Start with [CSA DesktopSetup](https://github.com/CloudSecurityAlliance/DesktopSetup).**
**Required if you are at CSA**; recommended for everyone else, because it installs the whole
toolchain this rig assumes — Claude Code, `gh`, Python, git, pipx — in one step instead of five.
The setup script below checks for those tools and, if any are missing, points you here rather
than listing separate installs.

```bash
# macOS
bash -c "$(curl -fsSL -H 'Cache-Control: no-cache' \
  https://raw.githubusercontent.com/CloudSecurityAlliance/DesktopSetup/HEAD/scripts/macos-ai-tools.sh)"
```

Windows needs a one-time PowerShell step first and is documented in that repo — but note the rig
itself is **macOS only** (the editor layer is `⌘`-based), so Windows is for the surrounding
tooling, not for running the suite.

**Then, standing the rig up from nothing:**

```bash
# 1. The OAuth client, first — a DESKTOP-APP client. Google's API ToS forbid shipping developer
#    credentials in an open-source project, so it lives in the private CSA-Plugins repo.
#    Setup will not proceed without it.
mkdir -p ~/.csa_google_workspace
cp /path/to/client_secret.json ~/.csa_google_workspace/client_secret.json

# 2. Clone. Both scripts run FROM the checkout: the live suites, the zoo builders and the
#    helper scripts are not in the PyPI sdist, only in git.
git clone https://github.com/CloudSecurityAlliance/csa-google-workspace
cd csa-google-workspace

# 3. Once. Opens a browser TWICE — read-write, then read-only. That is the design, not a
#    glitch: the read-only posture caches separately and a read-write token does not satisfy it.
./Setup-test-machine.sh

# 4. Verify, then run. Measured 2026-09-05: about 2-4 minutes for the unattended layers once
#    everything is installed. The FIRST run also downloads and installs, so allow longer.
./Run-full-test-suite.sh --check
./Run-full-test-suite.sh
```

**When something goes wrong, produce a report rather than describing it.** `--report` writes a
shareable file naming every prerequisite, both versions, and what is missing — and `--debug`
stops the installs swallowing their own output, which is where the useful error usually is:

```bash
./Run-full-test-suite.sh --check --report     # works even when nothing "failed"
./Run-full-test-suite.sh --debug              # verbose installs, whole run kept in a log
```

The report carries no Drive file ids, document text, or usernames — home directories and
`/Users/<name>` are both collapsed — so it is safe to attach to a public issue. The raw run log
is **not**: paste the report, link the log only if asked.

**A failure against `latest` may already be fixed.** The rig tests the *published release*, and
`main` is usually ahead of it — so re-run the same layers with `--version tree` before filing.
Fails on both, it is live; fails only on `latest`, it is fixed and waiting for a release. That
distinction is the first thing anyone triaging will want, and it costs one command:

```bash
./Run-full-test-suite.sh --version tree --layers 2
```

`Setup-test-machine.sh --check` reports what is missing and changes nothing, which is the safe
thing to run first on a machine you are unsure about. If tooling is missing it points at **CSA
DesktopSetup** rather than listing five separate installs.

Three things about it are not obvious, and each is a trap somebody would otherwise hit:

* **It tests the published wheel, not your checkout.** `pyproject.toml` sets
  `pythonpath = ["src"]`, so a plain `pytest` imports the working tree *even with a wheel
  installed* — the naive rig reports "tested 0.51.1 from PyPI: PASS" having tested your local
  edits. Every invocation passes `-o pythonpath=` and the runner **asserts what it imported**
  before any layer runs.
* **The live suites are not on PyPI.** The sdist ships the offline tests and neither
  `tests/integration/` nor `tests/oauth/`, so the rig pairs a PyPI **wheel** with a git
  **checkout at the matching tag**.
* **Two Google consents, deliberately.** `CSA_GW_READ_ONLY=1` caches separately and a
  read-write token does not satisfy it. That separation is the thing the read-only layer tests,
  so it is the mechanism rather than an inconvenience.

Test files go in `csa-google-workspace-YYYYMMDDHHMM` in My Drive, created fresh per run and
trashed at the end; `--folder <id|url>` uses a standing folder instead, and a run **never**
trashes a folder it did not create.

**The claude.ai Google Drive connector is denied for sessions in this repo**
([`.claude/settings.json`](./.claude/settings.json)) — a second Drive client can answer a
question meant for this server, so the run goes green having never exercised the library, and it
defeats the policy ceiling described above, which binds *this* library's calls and not another
client's.

**When something fails, it writes the issue for you.** A run that fails leaves a draft at
`~/.csa_gw_rig/issue-report.md` naming the version tested, **proving what was actually
imported** (site-packages or the checkout), the environment, and the command to reproduce —
because *"which version?"* and *"are you sure that was the release?"* are the first two replies
otherwise.

```bash
gh issue create --repo CloudSecurityAlliance/csa-google-workspace \
    --title '<layer>: <what broke>' --body-file ~/.csa_gw_rig/issue-report.md
```

Search first, and if it is already open say it reproduced on that version rather than opening a
second. And **do not paste the raw run log in**: a live test's output can carry a Drive file id,
a document title or comment text, and a file id in a public issue is a working link to the
document. The draft contains none of that by construction, and no filesystem paths either.

Design and the full layer list: [`docs/superpowers/specs/2026-09-05-conformance-rig.md`](./docs/superpowers/specs/2026-09-05-conformance-rig.md).

## License

Licensed under the [Apache License, Version 2.0](./LICENSE).
