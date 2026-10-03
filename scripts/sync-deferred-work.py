#!/usr/bin/env python3
"""Register deferred-work entries as GitHub issues and reconcile their lifecycle.

`_bmad-output/implementation-artifacts/deferred-work.md` is a BMAD-owned,
append-only ledger. BMAD skills may only append entries and are explicitly told
never to modify existing ones, so the file itself never records that an entry
was completed or cancelled. This script keeps GitHub as the *status* carrier
and the ledger as the *intake* carrier:

    BMAD appends an entry  ->  this script opens one issue per new entry
    an issue is closed     ->  this script reports the entry as needing a
                               `retired:` record appended to the ledger
    a `retired:` record    ->  this script closes the mapped issue

The ledger is never rewritten. Retirement is expressed by appending a
`retired:` record, which preserves BMAD's append-only contract, and the script
propagates it to GitHub so both sides converge.

Identity: BMAD's entry format carries no id, so one is derived from the entry
content. `source_spec` alone is not unique (one spec produced 11 entries), and
`summary` is prose that a human may reword. An unknown id is therefore ALWAYS
treated as new work: suppressing creation is never safe, because the failure is
invisible. When a new entry shares a source spec with mapped entries the script
warns, so a human can spot a genuine duplicate, but it still creates the issue.

Entry shapes seen in the wild, all of which parse:
  - `bmad-build`:   `- source_spec: ...` / `  summary: ...` / `  evidence: ...`
                    with an optional `note:`, and unbackticked source specs
                    (the split-goal path writes `source_spec: none`).
                    `source_plan` is tolerated as an alias for the first field:
                    one BMAD revision renamed it, and that revision did not
                    land, but the alias keeps a future rename from silently
                    hiding new entries.
  - `bmad-code-review`: `## Deferred from: ...` heading followed by bullets.

The derived id uses the first field's VALUE, never its key name, so the same
source maps to one issue whichever key was written.

Retirement records, also append-only:
  - `retired: <entry_id>` / `  reason: completed|not_planned|superseded` /
    `  issue: <number>`
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPOSITORY_ROOT / "_bmad-output/implementation-artifacts/deferred-work.md"
MAPPING_PATH = REPOSITORY_ROOT / ".github/deferred-sync-map.json"

DEFAULT_REPOSITORY = "blue126/IaC"
DEFAULT_LABEL = "enhancement"

ALLOWED_RETIRE_REASONS = ("completed", "not_planned", "superseded")
# GitHub only accepts two close reasons; the ledger keeps the finer distinction.
CLOSE_REASON = {
    "completed": "completed",
    "not_planned": "not planned",
    "superseded": "not planned",
}

SOURCE_LINE = re.compile(r"^- source_(?:spec|plan):\s*(?P<raw>.+?)\s*$")
RETIRED_LINE = re.compile(r"^- retired:\s*`?(?P<entry_id>[0-9a-fA-F]{12})`?\s*$")
RETIRED_ANY = re.compile(r"^\s*- retired:")
FIELD_LINE = re.compile(r"^\s+(?P<key>summary|evidence|note|reason|issue):\s*(?P<value>.*)$")
REVIEW_HEADING = re.compile(r"^##\s+Deferred from:\s*(?P<title>.+?)\s*$")
BULLET = re.compile(r"^[-*]\s+(?P<body>.*)$")
ISSUE_URL = re.compile(r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)")


class SyncError(RuntimeError):
    """Raised when the ledger or the GitHub interaction cannot be trusted."""


@dataclass
class Entry:
    entry_id: str
    source_spec: str
    summary: str
    evidence: str = ""
    note: str = ""
    kind: str = "build"

    def issue_title(self) -> str:
        return self.summary.rstrip("。.")


@dataclass
class Ledger:
    entries: list[Entry] = field(default_factory=list)
    retired: dict[str, dict[str, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def make_entry_id(source_spec: str, summary: str) -> str:
    """Derive a stable 12-hex id from the fields BMAD always writes."""
    payload = f"{source_spec}\x00{summary}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def _unquote(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1].strip()
    return value


def _mapping_issue(entry_id: str, record: dict[str, Any]) -> int:
    """Read a mapping record's issue number, or fail with our own error.

    A hand-edited or partially written mapping must produce the script's
    `blocked:` message rather than an uncaught KeyError/ValueError traceback.
    """
    raw = record.get("issue")
    try:
        number = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise SyncError(
            f"mapping record for {entry_id} has an unusable issue number: {raw!r}"
        ) from error
    if number <= 0:
        raise SyncError(f"mapping record for {entry_id} has an invalid issue: {raw!r}")
    return number


def _looks_like_repo_path(source_spec: str) -> bool:
    """True for source specs that name a file or directory in this repository.

    BMAD also writes prose and the literal `none`, which are not paths and must
    not be reported as stale.
    """
    if not source_spec or source_spec == "none":
        return False
    if source_spec.startswith(("http://", "https://")):
        return False
    return "/" in source_spec or source_spec.endswith(".md")


def parse_ledger(text: str) -> Ledger:
    """Parse every entry shape and every retirement record.

    A line-driven state machine is used instead of one large multi-line regex:
    fields are optional and may appear in any order, and an entry's `note:` must
    bind to that entry rather than to a window of following characters.
    """
    ledger = Ledger()
    lines = text.replace("\r\n", "\n").split("\n")

    current: dict[str, str] | None = None
    review_title: str | None = None

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        if "__retired__" in current:
            # A retirement record is not an entry; nothing to emit.
            current = None
            return
        source = current.get("source_spec", "")
        summary = current.get("summary", "").strip()
        if not source:
            ledger.warnings.append("entry without a source_spec was skipped")
        elif not summary:
            ledger.warnings.append(
                f"entry under {source!r} has no summary and cannot become an issue"
            )
        else:
            ledger.entries.append(
                Entry(
                    entry_id=make_entry_id(source, summary),
                    source_spec=source,
                    summary=summary,
                    evidence=current.get("evidence", "").strip(),
                    note=current.get("note", "").strip(),
                    kind="build",
                )
            )
        current = None

    last_field: str | None = None

    for raw_line in lines:
        line = raw_line.rstrip()

        heading = REVIEW_HEADING.match(line)
        if heading:
            flush()
            review_title = heading.group("title").strip()
            last_field = None
            continue

        if line.startswith("#"):
            # Any other heading ends the current review section and entry.
            flush()
            review_title = None
            last_field = None
            continue

        retired = RETIRED_LINE.match(line)
        if retired:
            flush()
            entry_id = retired.group("entry_id").lower()
            if entry_id in ledger.retired:
                ledger.warnings.append(f"duplicate retired record for {entry_id}")
            ledger.retired[entry_id] = {"reason": "", "issue": ""}
            current = {"__retired__": entry_id}
            last_field = None
            continue

        if RETIRED_ANY.match(line):
            # `- retired:` with a malformed or indented id. Report it instead of
            # dropping the line silently; a silently ignored retirement leaves a
            # stale issue open forever.
            ledger.warnings.append(
                f"malformed retired record (expected '- retired: <12-hex id>' at "
                f"column 0): {line.strip()!r}"
            )
            continue

        source = SOURCE_LINE.match(line)
        if source:
            flush()
            current = {"source_spec": _unquote(source.group("raw"))}
            last_field = None
            continue

        field_match = FIELD_LINE.match(line)
        if field_match and current is not None:
            key = field_match.group("key")
            value = field_match.group("value").strip()
            if "__retired__" in current:
                if key in ("reason", "issue"):
                    ledger.retired[current["__retired__"]][key] = value
                else:
                    ledger.warnings.append(
                        f"unexpected field {key!r} in retired record "
                        f"{current['__retired__']}"
                    )
            else:
                current[key] = value
                last_field = key
            continue

        bullet = BULLET.match(line)
        if bullet and review_title is not None:
            flush()
            summary = re.sub(r"^\[[ xX]\]\s*", "", bullet.group("body").strip()).strip()
            if summary:
                ledger.entries.append(
                    Entry(
                        entry_id=make_entry_id(review_title, summary),
                        source_spec=review_title,
                        summary=summary,
                        kind="review",
                    )
                )
            last_field = None
            continue

        if not line.strip():
            # A blank line ends a wrapped value but not the entry itself.
            last_field = None
            continue

        if current is not None and "__retired__" not in current and last_field:
            if line[:1].isspace():
                if last_field == "summary":
                    # `summary` feeds the derived id, so quietly extending it
                    # would mint a new id and duplicate the issue on the next
                    # run. Report instead, and keep the entry's identity stable.
                    ledger.warnings.append(
                        "ignored a wrapped continuation after summary (it would "
                        f"change the derived id): {line.strip()[:60]!r}"
                    )
                    continue
                # A wrapped continuation of evidence/note carries no identity
                # risk, so keep the text rather than dropping it.
                current[last_field] = (current.get(last_field, "") + " " + line.strip()).strip()
                continue

        # Anything else ends the current entry.
        flush()
        last_field = None

    flush()

    for entry_id, record in sorted(ledger.retired.items()):
        reason = record.get("reason", "").strip()
        issue = record.get("issue", "").strip()
        if reason not in ALLOWED_RETIRE_REASONS:
            ledger.warnings.append(
                f"retired record {entry_id} has an unsupported reason "
                f"{reason!r} (expected one of {', '.join(ALLOWED_RETIRE_REASONS)})"
            )
            record["reason_valid"] = "no"
        else:
            record["reason_valid"] = "yes"
        if not issue.isdigit():
            ledger.warnings.append(
                f"retired record {entry_id} has no valid issue number ({issue!r})"
            )

    # Two identical entries derive the same id. Keep the first and report it:
    # aborting the whole run would block every unrelated entry over one
    # duplicated line.
    deduplicated: list[Entry] = []
    seen: set[str] = set()
    for entry in ledger.entries:
        if entry.entry_id in seen:
            ledger.warnings.append(
                f"duplicate entry (same source and summary) ignored: {entry.summary[:60]}"
            )
            continue
        seen.add(entry.entry_id)
        deduplicated.append(entry)
    ledger.entries = deduplicated
    return ledger


def load_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "version": 1,
            "repository": DEFAULT_REPOSITORY,
            "routes": [],
            "entries": {},
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SyncError(f"mapping file is unreadable: {path}") from error
    data.setdefault("version", 1)
    data.setdefault("repository", DEFAULT_REPOSITORY)
    data.setdefault("routes", [])
    data.setdefault("entries", {})
    return data


def route_repository(mapping: dict[str, Any], source_spec: str) -> str:
    """Resolve the target repository for one entry.

    Components can move to another repository while their ledger entry stays in
    this one (qwen3-tts moved to llm-ops). A route matches on a source-spec
    substring; anything unmatched goes to the default repository.
    """
    for route in mapping.get("routes", []):
        needle = route.get("match", "")
        if needle and needle in source_spec:
            return route.get("repository", mapping["repository"])
    return mapping["repository"]


def save_mapping(path: Path, mapping: dict[str, Any]) -> None:
    """Write atomically so a crash cannot leave a truncated mapping."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        mode = 0o644
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # mkstemp creates 0600; keep whatever mode the file already had.
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def gh(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["gh", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SyncError(f"gh {' '.join(arguments[:2])} failed: {detail[:300]}")
    return result


def issue_state(repository: str, number: int) -> str:
    result = gh(
        ["issue", "view", str(number), "--repo", repository, "--json", "state"]
    )
    try:
        return json.loads(result.stdout)["state"]
    except (json.JSONDecodeError, KeyError) as error:
        raise SyncError(f"unexpected gh output for issue #{number}") from error


def find_issue_by_marker(repository: str, entry_id: str) -> int | None:
    """Recover an issue created by an earlier run whose mapping write failed."""
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repository,
            "--state",
            "all",
            "--search",
            f"deferred-work:{entry_id} in:body",
            "--json",
            "number,body",
            "--limit",
            "5",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        candidates = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    marker = f"<!-- deferred-work:{entry_id} -->"
    for candidate in candidates:
        if marker in candidate.get("body", ""):
            return int(candidate["number"])
    return None


def create_issue(repository: str, entry: Entry, label: str) -> int:
    result = gh(
        [
            "issue",
            "create",
            "--repo",
            repository,
            "--title",
            entry.issue_title(),
            "--body",
            render_body(entry),
            "--label",
            label,
        ]
    )
    match = ISSUE_URL.search(result.stdout)
    if match:
        return int(match.group("number"))
    # The issue exists but its URL was not in the expected shape. Look it up by
    # the marker in the body instead of leaving an orphaned, unmapped issue.
    recovered = find_issue_by_marker(repository, entry.entry_id)
    if recovered is not None:
        return recovered
    raise SyncError(
        "an issue was created but its number could not be determined; "
        f"search {repository} for marker deferred-work:{entry.entry_id}"
    )


def close_issue(repository: str, number: int, reason: str) -> None:
    gh(
        [
            "issue",
            "close",
            str(number),
            "--repo",
            repository,
            "--reason",
            CLOSE_REASON.get(reason, "not planned"),
        ]
    )


def render_body(entry: Entry) -> str:
    lines = [
        f"<!-- deferred-work:{entry.entry_id} -->",
        f"> 由 `deferred-work.md` 同步生成 · 条目 ID `{entry.entry_id}` · 类型 `{entry.kind}`",
        "",
        entry.summary,
    ]
    if entry.evidence:
        lines += ["", f"**证据**：{entry.evidence}"]
    if entry.note:
        lines += ["", f"**备注**：{entry.note}"]
    lines += ["", "**来源**", f"- `{entry.source_spec}`"]
    return "\n".join(lines)


class Lock:
    """Prevent two concurrent runs from clobbering the mapping.

    The pid is written after the exclusive create, so a process killed in that
    window leaves a lock with no readable pid. A stale lock is reclaimed
    automatically rather than wedging the script until a human deletes it.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.acquired = False

    def _holder_alive(self) -> bool:
        try:
            raw = self.path.read_text(encoding="ascii").strip()
        except OSError:
            return False
        if not raw.isdigit():
            return False
        pid = int(raw)
        if pid == os.getpid():
            # This process already holds the lock; acquiring it twice is a bug,
            # so report it as held rather than silently reclaiming.
            return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def __enter__(self) -> "Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(2):
            try:
                descriptor = os.open(
                    self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644
                )
            except FileExistsError as error:
                if attempt == 0 and not self._holder_alive():
                    # Reclaim a lock whose holder is gone.
                    try:
                        self.path.unlink()
                    except OSError:
                        pass
                    continue
                raise SyncError(
                    f"another sync is running ({self.path}); "
                    "remove the file only if no sync process exists"
                ) from error
            os.write(descriptor, str(os.getpid()).encode("ascii"))
            os.close(descriptor)
            self.acquired = True
            return self
        raise SyncError(f"could not acquire the sync lock at {self.path}")

    def __exit__(self, *_: object) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except OSError:
                pass


def sync(
    *,
    repository: str,
    mapping_path: Path,
    ledger_path: Path,
    apply: bool,
    label: str,
) -> int:
    if not ledger_path.exists():
        raise SyncError(f"ledger not found: {ledger_path}")

    ledger = parse_ledger(ledger_path.read_text(encoding="utf-8"))
    for warning in ledger.warnings:
        print(f"WARN  {warning}", file=sys.stderr)

    mapping = load_mapping(mapping_path)
    entries: dict[str, Any] = mapping["entries"]
    retired_ids = set(ledger.retired)

    # A new id is ALWAYS new work. The only safe suppression is an explicit
    # retirement record; guessing from the source spec silently loses work.
    to_create = [
        e for e in ledger.entries if e.entry_id not in entries and e.entry_id not in retired_ids
    ]

    # Advisory only: a new entry that shares a source spec with mapped entries
    # may be a reworded duplicate, but suppressing it would be unsafe.
    possible_duplicates: list[tuple[Entry, int]] = []
    mapped_sources: dict[str, int] = {}
    for entry_id, record in entries.items():
        source = record.get("source_spec")
        if source:
            # Use the same guarded read as the reconcile loop: one corrupt
            # record must not abort the whole run before validation runs.
            try:
                mapped_sources.setdefault(source, _mapping_issue(entry_id, record))
            except SyncError as error:
                print(f"WARN  {error}", file=sys.stderr)
    for entry in to_create:
        known = mapped_sources.get(entry.source_spec)
        if known is not None:
            possible_duplicates.append((entry, known))

    # Read state in BOTH modes: it is a read-only call, and a dry run that
    # cannot see a closed issue cannot reconcile anything.
    closed_but_active: list[tuple[Entry, int]] = []
    retired_but_open: list[tuple[str, int, str]] = []
    invalid_retirements: list[str] = []
    unresolved: list[tuple[str, str]] = []
    mismatched_issue: list[tuple[str, int, str]] = []
    unreachable: list[tuple[str, str]] = []
    for entry in ledger.entries:
        record = entries.get(entry.entry_id)
        if record is None:
            continue
        # One unreachable or corrupt reference must not abort the run: new
        # entries elsewhere still deserve their issue. A mapped issue can be
        # deleted, transferred, or live in a repository this token cannot read
        # (the routes here point one entry set at blue126/llm-ops).
        try:
            target = record.get("repository") or mapping["repository"]
            number = _mapping_issue(entry.entry_id, record)
            if entry.entry_id in retired_ids:
                retirement = ledger.retired[entry.entry_id]
                recorded = retirement.get("issue", "")
                if recorded.isdigit() and int(recorded) != number:
                    mismatched_issue.append((entry.entry_id, number, recorded))
                if retirement.get("reason_valid") != "yes":
                    # An unsupported reason must not silently become a GitHub
                    # close: `completed` and `not planned` differ in history.
                    invalid_retirements.append(entry.entry_id)
                    continue
                state = issue_state(target, number)
                record["state"] = state
                if state == "OPEN":
                    retired_but_open.append(
                        (entry.entry_id, number, retirement.get("reason", ""))
                    )
                continue
            state = issue_state(target, number)
            record["state"] = state
            if state == "CLOSED":
                closed_but_active.append((entry, number))
        except SyncError as error:
            unreachable.append((entry.entry_id, str(error)))

    # Retired ids that map to nothing at all: either a typo or an entry that
    # was removed before it was ever registered.
    for entry_id, record in sorted(ledger.retired.items()):
        if entry_id not in entries:
            unresolved.append((entry_id, record.get("issue", "")))

    # A source spec that no longer exists usually means a rename moved the file
    # (a directory restructure invalidated two paths here). The entry still
    # syncs by id; this only tells a reader that the trail has gone cold.
    stale_sources = sorted(
        {
            entry.source_spec
            for entry in ledger.entries
            if _looks_like_repo_path(entry.source_spec)
            and not (REPOSITORY_ROOT / entry.source_spec).exists()
        }
    )

    print(f"ledger entries       : {len(ledger.entries)}")
    print(f"retired records      : {len(ledger.retired)}")
    print(f"mapped in ledger     : {len(entries)}")
    print(f"new entries          : {len(to_create)}")
    print(f"closed but active    : {len(closed_but_active)}")
    print(f"retired but open     : {len(retired_but_open)}")
    print(f"invalid retirements  : {len(invalid_retirements)}")
    print(f"unresolved retired   : {len(unresolved)}")
    print(f"issue number mismatch: {len(mismatched_issue)}")
    print(f"unreachable issues   : {len(unreachable)}")
    print(f"stale source specs   : {len(stale_sources)}")

    if unreachable:
        print("\n-- mapped issues that could not be read (skipped, run continues) --")
        for entry_id, detail in unreachable:
            print(f"   {entry_id}  {detail[:90]}")
        print("   fix the mapping or restore access to that repository")

    if invalid_retirements:
        print("\n-- retired records with an unusable reason (left open) --")
        for entry_id in invalid_retirements:
            print(f"   {entry_id}  reason={ledger.retired[entry_id].get('reason')!r}")
        print("   fix the reason to completed|not_planned|superseded, then re-run")

    if mismatched_issue:
        print("\n-- ledger issue number differs from the mapping (mapping wins) --")
        for entry_id, number, recorded in mismatched_issue:
            print(f"   {entry_id}  mapping=#{number}  ledger={recorded}")

    if stale_sources:
        print("\n-- source specs that no longer resolve in this repository --")
        for source in stale_sources:
            print(f"   {source}")
        print("   entries still sync by id; the recorded path is provenance only")

    if possible_duplicates:
        print("\n-- new entries sharing a source spec with a mapped issue --")
        for entry, number in possible_duplicates:
            print(f"   {entry.entry_id}  (same spec as #{number})  {entry.summary[:64]}")
        print("   these are still registered; close one and retire it if duplicated")

    if closed_but_active:
        print("\n-- closed on GitHub, not retired in the ledger --")
        for entry, number in closed_but_active:
            print(f"   #{number}  {entry.entry_id}  {entry.summary[:64]}")
        print("   append to deferred-work.md:")
        for entry, number in closed_but_active:
            print(f"     - retired: {entry.entry_id}")
            print("       reason: <completed|not_planned|superseded>")
            print(f"       issue: {number}")

    if retired_but_open:
        print("\n-- retired in the ledger, still open on GitHub --")
        for entry_id, number, reason in retired_but_open:
            print(f"   #{number}  {entry_id}  reason={reason or '?'}  -> will be closed")

    if unresolved:
        print("\n-- retired ids with no matching entry or issue --")
        for entry_id, issue in unresolved:
            print(f"   {entry_id}  issue={issue or '?'}  (check the id for a typo)")

    if not apply:
        print("\ndry-run: no GitHub writes performed")
        return 0

    created = 0
    for entry in to_create:
        target = route_repository(mapping, entry.source_spec)
        number = create_issue(target, entry, label)
        entries[entry.entry_id] = {
            "issue": number,
            "repository": target,
            "source_spec": entry.source_spec,
            "summary": entry.summary,
            "title": entry.issue_title(),
            "label": label,
            "state": "OPEN",
        }
        print(f"created {target}#{number}  {entry.entry_id}  {entry.summary[:60]}")
        created += 1
        save_mapping(mapping_path, mapping)

    closed = 0
    for entry_id, number, reason in retired_but_open:
        target = entries[entry_id].get("repository") or mapping["repository"]
        close_issue(target, number, reason)
        entries[entry_id]["state"] = "CLOSED"
        print(f"closed {target}#{number}  {entry_id}  reason={reason or 'not_planned'}")
        closed += 1

    if not mapping.get("repository"):
        mapping["repository"] = repository
    elif mapping["repository"] != repository:
        print(
            f"note: the mapping's default repository stays "
            f"{mapping['repository']!r} (--repository {repository!r} applies to "
            "new routes only)"
        )
    save_mapping(mapping_path, mapping)
    print(
        f"\ncreated {created} issue(s), closed {closed} issue(s); "
        f"mapping written to {mapping_path.name}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    parser.add_argument("--mapping", type=Path, default=MAPPING_PATH)
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the plan (including issue state) without writing anywhere",
    )
    arguments = parser.parse_args(argv)
    lock_path = arguments.mapping.with_suffix(arguments.mapping.suffix + ".lock")
    try:
        with Lock(lock_path):
            return sync(
                repository=arguments.repository,
                mapping_path=arguments.mapping,
                ledger_path=arguments.ledger,
                apply=not arguments.dry_run,
                label=arguments.label,
            )
    except SyncError as error:
        print(f"deferred-sync: blocked: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"deferred-sync: blocked: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
