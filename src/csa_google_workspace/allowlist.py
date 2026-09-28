"""The file allowlists: which documents may be read, and which may be changed.

**Configured entirely through the environment. There is no file to read.**
`CSA_GW_ALLOWLIST_READ` and `CSA_GW_ALLOWLIST_MODIFY` hold the lists themselves, so they live
in the same place the MCP server is declared — a shell, `.mcp.json`, Claude Desktop's config.

That is a deliberate restriction rather than a missing feature. The client configuration is
the artifact an operator controls and can *see*: reading it tells them exactly what the agent
may touch. A path adds an indirection whose target can change without the config changing,
puts the real policy somewhere nobody looks, and makes the path itself a thing that can be
mistyped or redirected. The cost is that a long list is less pleasant in JSON than in a file;
that is the trade, and it is accepted knowingly.

**Deliberately the simplest thing that works: a flat list of document URLs.** No folders, no
patterns, no wildcards beyond `*`. Folders are the interesting design problem and they are
*not* solved here — see `TODO.md`, "Folders in the allowlist", for why folder-as-rule is
harder and more dangerous than it looks. Until that is settled, a folder URL is a **loud
error**, not a silently-inert entry.

Enforcement is by **file id**, not by URL string. Every URL form for the same document
normalises to the same id, so a pasted `/edit?tab=t.0` link is the same entry as a
`?usp=sharing` one — and a *copy* of an allowlisted document has a different id and is
therefore not allowlisted, which is the correct default.

**Three outcomes, and the third one is the point.** A value is either `*` (everything), a set
of document URLs, or **unusable** — and unusable always means *nothing permitted*, never
"ignore the setting". Because "unusable" covers a lot of ground, `diagnose_url` and
`diagnose_setting` say which kind it is.

Format — one URL per entry, newlines or commas separating them, `#` starting a comment. In a
JSON `env` block, `\n` gives you the multi-line form and keeps the reasons:

    https://docs.google.com/document/d/1oW1BM…/edit?tab=t.0   # CCM v5 mapping, per WG lead
    https://docs.google.com/spreadsheets/d/1abc…/edit          # AICM tracker

Leading, trailing and interior whitespace is insignificant, so entries can be indented and
aligned however reads best — tabs included. Blank lines and whole-line comments are ignored
anywhere. A comment starts at a `#` that begins the line or **follows whitespace**, which is
what lets a URL keep an `#gid=0` or `#heading=h.x` fragment. The reason itself is free text:
quotes, apostrophes and further `#`s in it are fine here — though whatever holds the value,
JSON or a shell, has its own quoting rules to satisfy.

Per-capability scoping — "this file may be commented on but not edited" — would need a
structured format. That is a deliberate later decision, noted in `TODO.md`.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from . import exceptions as exc

log = logging.getLogger(__name__)

# The one entry that means "no restriction". A literal, because unrestricted access should be
# something a person typed into a reviewed file rather than a default nobody noticed.
ALL = "*"
# Accepted as a synonym so the v0.8.1 spelling keeps working.
ALL_SYNONYMS = frozenset({ALL, "any", "all"})

# `/d/<id>` covers docs.google.com/{document,spreadsheets,presentation}/d/<id> and
# drive.google.com/file/d/<id>.
_ID_IN_PATH = re.compile(r"/d/([a-zA-Z0-9_-]{10,})")
# The older `?id=` / `&id=` form, still produced by some Drive UI paths.
_ID_IN_QUERY = re.compile(r"[?&]id=([a-zA-Z0-9_-]{10,})")
# What we must refuse rather than misread.
_FOLDER = re.compile(r"/drive/(?:u/\d+/)?folders/([a-zA-Z0-9_-]+)")
# A comment starts at a `#` that begins the line or follows whitespace. The whitespace
# requirement is what lets a URL keep its fragment: `…/edit#gid=0` and `…/edit#heading=h.x`
# are ordinary Drive links, and treating their `#` as a comment delimiter turned the anchor
# into the "reason" and threw the real reason away.
_COMMENT = re.compile(r"(?:^|(?<=\s))#")


class AllowlistError(exc.CsaWorkspaceError):
    """The allowlist is configured but unusable. Never degrades to "no restrictions"."""


@dataclass(frozen=True)
class Listing:
    """A parsed allowlist: either "everything", or a specific set of documents.

    `all_files` is not just `entries == ()`; the two are different answers. An empty listing
    is a configuration error (indistinguishable from a typo), whereas `all_files` is a
    deliberate, logged decision.
    """
    all_files: bool
    entries: tuple[Entry, ...] = ()

    @property
    def file_ids(self) -> frozenset[str]:
        return frozenset(e.file_id for e in self.entries)

    def __repr__(self) -> str:
        return ("Listing(all_files=True)" if self.all_files
                else f"Listing(files={len(self.entries)})")


@dataclass(frozen=True)
class Entry:
    file_id: str
    url: str
    reason: str | None
    line: int

    def __repr__(self) -> str:
        # The reason may name people or projects; the id is what an audit needs.
        return f"Entry(file_id={self.file_id!r}, line={self.line}, has_reason={self.reason is not None})"


PLACEHOLDER_MARKS = ("…", "...", "<", ">", "[", "]", "{", "}", "xxx", "AAA", "BBB")
# The complete set of hosts a Google document URL is served from, matched by EQUALITY - see
# `_is_google_host`. Each is here because somebody can genuinely paste it:
#
#   docs.google.com     Docs, Sheets and Slides all live here in practice
#                       (/document/d/, /spreadsheets/d/, /presentation/d/)
#   drive.google.com    file and folder links (/file/d/, /open?id=)
#   sheets.google.com   redirect hosts. They bounce to docs.google.com, but a person who
#   slides.google.com   typed one by hand should not have their entry refused for it.
#
# Adding to this list is a deliberate act, reviewed like any other change. That is the point
# of an exact list over a pattern: the friction is where it belongs.
GOOGLE_HOSTS = ("docs.google.com", "drive.google.com", "sheets.google.com",
                "slides.google.com")


def _is_google_host(host: str) -> bool:
    """Is `host` EXACTLY one of the hosts Google serves documents from?

    An allowlist of hostnames, matched by equality. Not a suffix rule, and not a subdomain
    rule either - both of those answer "does this look like Google?" when the question is
    "is this one of the four addresses a document URL actually comes from?"

    Two rejected approaches, in the order they were tried and found wanting:

      `host.endswith("docs.google.com")`   accepts evildocs.google.com. This is the
                                           incomplete-substring family CodeQL flags as
                                           py/incomplete-url-substring-sanitization.
      `host == g or host.endswith("." + g)` closes that, and still accepts any subdomain -
                                           so a hostname Google has never served a document
                                           from is trusted on the strength of its parent.

    Equality has no such edge. Google adding a host is then a one-line change to a list
    somebody reviews, which is the right amount of friction for something that decides what a
    write-allowlist entry is permitted to name.

    A trailing dot is stripped first: `docs.google.com.` is the fully-qualified spelling of
    the same host, not a different one.
    """
    return host.lower().rstrip(".") in GOOGLE_HOSTS


def diagnose_url(text: str) -> str | None:
    """Why `text` is not a usable document URL — or `None` if it is fine.

    Deliberately a ladder of specific cases rather than one "invalid URL". Every rung here
    corresponds to a mistake somebody actually makes, and the difference between "invalid
    value" and "the URL stops after /d/, so the file id is missing" is the difference between
    a support conversation and a fix. Deterministic, so it is testable and cannot be wrong
    about its own diagnosis; the model reading the tool error is what relays it in prose.
    """
    candidate = text.strip()
    if not candidate:
        return "the value is empty"

    if _FOLDER.search(candidate):
        return ("it is a folder, and folders are not supported in the allowlist yet. List the "
                "individual document URLs inside it instead. (Folder support needs the "
                "traversal, shortcut and TOCTOU questions settled first — see TODO.md, "
                "'Folders in the allowlist')")

    # The host is checked BEFORE extraction, and that ordering was wrong until now: extraction
    # returned "usable" for any URL containing a `/d/<id>/` segment, so the host rung below was
    # unreachable and `https://evil.example.com/document/d/<real-id>/edit` was accepted.
    #
    # Not an escalation - the id extracted is a real Drive id, so the entry granted exactly
    # what listing that id would have granted. The cost is that a documented check never fired:
    # somebody pasting a lookalike domain, a link-tracker wrapper, or a URL from an unrelated
    # system with the same path shape had it silently blessed, and a reviewer reading the
    # config saw a non-Google URL that the tool had apparently approved.
    #
    # Safe to hoist because the host rung has no false positives to worry about: a bare id and
    # a filesystem path both parse to an empty netloc and fall through to their own rungs.
    host = (urlparse(candidate).netloc or "").lower()
    if host and not _is_google_host(host):
        return (f"the host is {host!r}, which is not a Google Docs or Drive address. Expected "
                f"one of: {', '.join(GOOGLE_HOSTS)}")

    # Extraction is attempted *before* the placeholder check, and that order is also
    # load-bearing: a genuine 44-character Drive id is random base64url and will occasionally
    # contain a sequence like "AAA". Diagnosing a working URL as a placeholder would be worse
    # than any message it replaced.
    if _ID_IN_PATH.search(candidate) or _ID_IN_QUERY.search(candidate):
        return None                                    # usable

    lowered = candidate.lower()
    for mark in PLACEHOLDER_MARKS:
        if mark.lower() in lowered:
            return (f"it contains {mark!r}, so it looks like a placeholder copied from "
                    f"documentation rather than a real link. Open the document and copy the "
                    f"URL from your browser's address bar")

    if _looks_like_a_path(candidate):
        return ("that looks like a file path. The allowlist is set in the environment, not "
                "read from a file — put the document URLs in the variable itself, separated "
                "by newlines or commas")

    if "://" not in candidate and "/" not in candidate:
        return ("that looks like a bare file id rather than a URL. The allowlist needs the "
                "full URL — a link can be opened and checked by whoever reviews it, and a "
                "bare id cannot be told apart from a typo")

    if _is_google_host(host):
        if re.search(r"/d/?$", candidate):
            return ("the URL stops after '/d/', so the file id is missing. It should look "
                    "like .../document/d/<long-id>/edit")
        return ("it is a Google URL but has no '/d/<id>' segment. Copy the whole address "
                "from your browser while the document is open")
    # A non-Google host was already rejected above, so anything still here has no host at all.
    return ("it is not a Google document URL. Expected something like "
            "https://docs.google.com/document/d/<id>/edit")


def _looks_like_a_path(candidate: str) -> str | bool:
    """Path-shaped, and therefore a mistake worth naming rather than a mystery.

    Checked *after* URL extraction, so a real URL is never mistaken for a path."""
    if "://" in candidate:
        return False
    return (candidate.startswith(("/", "./", "../", "~"))
            or bool(re.match(r"^[A-Za-z]:[\\/]", candidate))       # C:\... or C:/...
            or candidate.endswith((".txt", ".list", ".conf", ".cfg", ".json", ".yaml", ".yml")))


def diagnose_setting(variable: str, value: str | None) -> str:
    """Why a whole configuration field yields nothing — the fail-closed case.

    Distinguishing "unset" from "set but empty" matters: they look identical in behaviour and
    have completely different fixes. One means nobody configured it; the other usually means a
    template was filled in with a blank, or a shell expanded an undefined variable to nothing.
    """
    if value is None:
        return (f"{variable} is not set. It holds the list itself — there is no file to "
                f"create.")
    if not value.strip():
        return (f"{variable} is set but empty — which is not the same as unset. If it came "
                f"from a config template or an unexpanded shell variable, that is the thing "
                f"to fix rather than this.")
    return f"{variable} yielded no usable entries."


def parse_document_url(text: str) -> str:
    """A pasted Drive/Docs URL -> file id.

    Raises `AllowlistError` for anything not a single document, **including folders**. A
    folder URL cannot be treated as an opaque id: it would never match any file, so the
    entry would protect nothing while looking in the file like protection. That silent
    no-op is the exact failure #82 calls dead-entry detection.

    A **bare file id is rejected**, unlike `Workspace.open()`, which accepts one. Two
    reasons, both about review rather than convenience. A bare id cannot be distinguished
    from a typo — Drive ids are unstructured base64url, so `some-long-dashed-name` and a
    real id are the same shape, and an early version of this parser accepted both. And a URL
    in a reviewed config file is *clickable*: someone approving the entry can open it and
    see what they are granting.
    """
    problem = diagnose_url(text)
    if problem is not None:
        raise AllowlistError(f"{text.strip()!r}: {problem}")
    found = _ID_IN_PATH.search(text) or _ID_IN_QUERY.search(text)
    if found is None:
        # Unreachable while `diagnose_url` and the two patterns agree — but not an `assert`:
        # under `python -O` an assert vanishes and this becomes an AttributeError on None,
        # which is a worse failure than the one it was guarding against. Marked rather than
        # tested for the same reason it is not an assert: reaching it means the two have
        # already drifted, and a test that forced them apart would be asserting the drift.
        raise AllowlistError(                                   # pragma: no cover
            f"{text.strip()!r}: no file id could be extracted, though it passed validation. "
            f"This is a bug in the allowlist parser, not in your configuration.")
    return found.group(1)


def parse_allowlist(text: str, *, source: str = "<string>") -> Listing:
    """Parse the allowlist format. Every malformed line is reported, not just the first.

    Reporting all of them matters: an operator fixing a curated list of thirty URLs should
    not have to run the server thirty times to find the thirty typos.

    A line of `*` means *every file*, and short-circuits the rest. It logs a warning, because
    the whole point of this file is that unrestricted access should be visible.
    """
    entries: list[Entry] = []
    problems: list[str] = []
    seen: dict[str, int] = {}

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        marker = _COMMENT.search(line)
        url = line[:marker.start()] if marker else line
        reason = (line[marker.end():].strip() or None) if marker else None

        # A comment runs to the end of the line, so a URL inside one is *not* being
        # allowlisted. Almost always this is a separator mistake — `a # one, b # two` looks
        # like two entries and parses as one — and the consequence is a policy with fewer
        # files than its author believes. Fail closed *and* loudly; failing closed quietly is
        # how somebody spends an afternoon wondering why their document is read-only.
        if reason and (_ID_IN_PATH.search(reason) or _ID_IN_QUERY.search(reason)):
            problems.append(
                f"  {source}:{number}: the comment contains what looks like another document "
                f"URL, so that document is NOT being allowlisted — a comment runs to the end "
                f"of the line. Put each document on its own line (in a JSON value, separate "
                f"them with \\n). If you genuinely meant to mention a document in a comment, "
                f"refer to it by name rather than by URL.")
            continue

        if url.strip().lower() in ALL_SYNONYMS:
            log.warning("allowlist %s:%d grants access to EVERY file the credentials can "
                        "reach (%r)%s", source, number, url.strip(),
                        f": {reason}" if reason else "")
            return Listing(all_files=True)

        # More than one document on a line is the same silent-drop mistake wearing different
        # clothes: `a, b  # both` splits on newlines once comments are in play, and
        # `parse_document_url` would return the *first* id and discard the rest.
        found = len(_ID_IN_PATH.findall(url)) + len(_ID_IN_QUERY.findall(url))
        if found > 1:
            problems.append(
                f"  {source}:{number}: this line contains {found} document URLs, and only the "
                f"first would be allowlisted. Once any comment is present, entries are "
                f"separated by newlines only — put each document on its own line (in a JSON "
                f"value, separate them with \\n).")
            continue

        try:
            file_id = parse_document_url(url)
        except AllowlistError as e:
            problems.append(f"  {source}:{number}: {e}")
            continue
        if file_id in seen:
            # Not an error — a duplicate is harmless — but worth saying, because it usually
            # means two URLs someone believed were different documents.
            log.warning("allowlist %s:%d repeats the file already listed on line %d",
                        source, number, seen[file_id])
            continue
        seen[file_id] = number
        entries.append(Entry(file_id=file_id, url=url.strip(), reason=reason, line=number))

    if problems:
        raise AllowlistError(
            f"{len(problems)} unusable line(s) in the allowlist:\n" + "\n".join(problems))
    if not entries:
        raise AllowlistError(
            f"the allowlist at {source} contains no usable entries. Refusing to run with an "
            f"empty allowlist, because that is indistinguishable from a typo. Use a line "
            f"containing just `*` if unrestricted access is genuinely what you want.")
    return Listing(all_files=False, entries=tuple(entries))


def parse_setting(value: str, *, variable: str) -> Listing:
    """Parse one allowlist environment variable.

    Newlines separate entries and keep the `# reason` comments — a JSON `env` value writes
    that as `\n`. Commas, semicolons and whitespace also separate entries **when the value
    contains no `#`**; that condition is what stops a separator and a comment fighting over
    the same character, so the ambiguous case is unreachable rather than merely unlikely.
    """
    text = value if "#" in value else re.sub(r"[,;\s]+", "\n", value.strip())
    return parse_allowlist(text, source=variable)


# --- preview: what does this configuration actually point at? -----------------------------
#
# **A4's two remaining #82 items, and they turned out to be one feature.** "Dry-run" and
# "dead-entry detection" were tracked separately; resolving each entry against Drive answers
# both, because a dead entry is what a dry-run finds. Two tools would each have walked the list
# and called Drive to compute the same thing.
#
# Kept here, beside the parser, and given a `fetch` callable rather than a `Backend`: this
# module has no backend dependency and should not grow one. Parsing a list and resolving it are
# different jobs, and only one of them needs the network.
#
# NOT built, deliberately - see TODO.md, "Folders, drives and deny rules": folder membership is
# a live property (a file can be moved), so a folder rule means walking parents on EVERY access,
# at one `files.get` per level, uncacheable because caching authorization is how a revoked grant
# keeps working. That is a latency tax on every call for a control Drive's ACLs already
# back-stop, which is why it is post-1.0.0.

OK, TRASHED, UNREACHABLE = "ok", "trashed", "unreachable"

_MIME_TO_TYPE = {
    "application/vnd.google-apps.document": "document",
    "application/vnd.google-apps.spreadsheet": "spreadsheet",
    "application/vnd.google-apps.presentation": "presentation",
    "application/vnd.google-apps.folder": "folder",
}


@dataclass
class PreviewedEntry:
    """One allowlist entry, resolved against Drive.

    `name` and `reason` are deliberately separate and never merged. `reason` is the operator's
    own `#` comment - an *unverified claim sitting next to a permission*, since pasting the
    wrong URL under the right label is a mistake nothing else catches. `name` is what Drive
    actually calls the file. Collapsing them would hide precisely the mismatch worth seeing.
    """
    file_id: str
    url: str
    reason: str | None            # what the operator typed
    line: int
    status: str                   # ok | trashed | unreachable
    name: str | None = None       # what Drive says, absent when nothing was fetched
    type: str | None = None       # document | spreadsheet | presentation | folder | None
    detail: str | None = None     # why unreachable

    @property
    def dead(self) -> bool:
        return self.status != OK

    def __repr__(self) -> str:
        # Redacted for two reasons, not one. `reason` may name people or unannounced work -
        # `Entry.__repr__` already withholds it and this must not undo that. And the document
        # NAME is content: "Q3 layoffs planning" leaks exactly what the bare id concealed.
        return (f"PreviewedEntry(file_id={self.file_id!r}, line={self.line}, "
                f"status={self.status!r}, named={self.name is not None})")


@dataclass
class Preview:
    """The resolved listing. `unrestricted` is not "every entry passed"."""
    unrestricted: bool
    entries: tuple[PreviewedEntry, ...] = ()

    @property
    def ok(self) -> int:
        return sum(1 for e in self.entries if not e.dead)

    @property
    def dead(self) -> int:
        return sum(1 for e in self.entries if e.dead)

    @property
    def has_dead_entries(self) -> bool:
        return self.dead > 0


def preview(listing: Listing, fetch: Callable[[str], dict]) -> Preview:
    """Resolve every entry in `listing`, one fetch per distinct file id.

    `fetch(file_id) -> metadata` is expected to raise `NotFoundError` (deleted, or never
    existed) or `AccessError` (real, but not visible to these credentials). Both become
    `unreachable`, with `detail` saying which - they need different fixes.

    **Anything else propagates.** `unreachable` means Drive answered "no"; a network failure or
    a rate limit is not a fact about the entry, and reporting it as one would turn an outage
    into a report that the operator's list is broken.

    **`*` enumerates nothing and makes no calls.** "Everything your account can reach" is not a
    list; faking one would be slow, incomplete, and a different answer than the truth.
    """
    if listing.all_files:
        return Preview(unrestricted=True)

    resolved: dict[str, tuple[str, str | None, str | None, str | None]] = {}
    out = []
    for entry in listing.entries:
        if entry.file_id not in resolved:
            resolved[entry.file_id] = _resolve(entry.file_id, fetch)
        status, name, type_, detail = resolved[entry.file_id]
        out.append(PreviewedEntry(
            file_id=entry.file_id, url=entry.url, reason=entry.reason, line=entry.line,
            status=status, name=name, type=type_, detail=detail))
    return Preview(unrestricted=False, entries=tuple(out))


def _resolve(file_id: str, fetch: Callable[[str], dict]):
    try:
        meta = fetch(file_id)
    except exc.NotFoundError as e:
        return UNREACHABLE, None, None, f"not found: {e}"
    except exc.AccessError as e:
        return UNREACHABLE, None, None, f"no permission: {e}"
    name = meta.get("name") or None
    type_ = _MIME_TO_TYPE.get(meta.get("mimeType", ""))
    # A trashed file still resolves by id, so nothing else in this system would ever notice.
    # Still named: knowing WHICH entry died is the actionable part.
    status = TRASHED if meta.get("trashed") else OK
    return status, name, type_, None
