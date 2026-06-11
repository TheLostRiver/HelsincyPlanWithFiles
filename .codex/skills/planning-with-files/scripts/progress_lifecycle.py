#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import secrets
from typing import Iterable


SUMMARY_START = "<!-- PWF_COMPACT_SUMMARY_START -->"
SUMMARY_END = "<!-- PWF_COMPACT_SUMMARY_END -->"
AUTO_RECORD_PREFIX = "### Auto Record: "
ARCHIVE_HEADER = "# Progress Archive"
AUTO_RECORD_FIELDS = (
    "- Tool:",
    "- Session:",
    "- Plan-Source:",
    "- Phase:",
    "- Result:",
    "- Command:",
)
DATA_BLOCK_DELIMITER_RE = re.compile(r"^---(?:BEGIN|END) [A-Z ][A-Z ]* DATA---$")
PROGRESS_TRUNCATION_NOTE = "[planning-with-files] progress context truncated; oldest content omitted."


@dataclass(frozen=True)
class AutoRecord:
    index: int
    lines: tuple[str, ...]
    timestamp: str
    tool: str
    session: str
    plan_source: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class CompactResult:
    archived_count: int
    kept_count: int
    total_auto_records: int
    archive_path: Path
    changed: bool
    dry_run: bool
    summary: str


@dataclass(frozen=True)
class RolloverResult:
    archived_count: int
    kept_count: int
    total_auto_records: int
    archive_path: Path
    active_path: Path
    index_path: Path
    changed: bool
    dry_run: bool
    summary: str


def count_auto_records(progress_path: Path) -> int:
    if not progress_path.is_file():
        return 0
    return sum(1 for line in _read_lines(progress_path) if line.startswith(AUTO_RECORD_PREFIX))


def extract_compaction_summary(progress_path: Path, line_limit: int = 20) -> str:
    if not progress_path.is_file() or line_limit < 1:
        return ""
    lines = _read_lines(progress_path)
    start = _find_line(lines, SUMMARY_START)
    end = _find_line(lines, SUMMARY_END)
    if start is None or end is None or end <= start:
        return ""
    summary_lines = lines[start + 1 : end]
    return "\n".join(summary_lines[:line_limit]).strip()


def extract_recent_progress_context(
    progress_path: Path,
    record_limit: int,
    manual_tail_lines: int,
    max_chars: int,
) -> str:
    if not progress_path.is_file() or max_chars < 1:
        return ""

    lines = _remove_managed_summary(_read_lines(progress_path))
    if not any(line.strip() for line in lines):
        return ""

    nodes, records = _parse_nodes(lines)
    kept_record_indexes = {record.index for record in records[-max(0, record_limit) :]}
    manual_keys = _recent_manual_line_keys(nodes, max(0, manual_tail_lines))

    units: list[tuple[str, ...]] = []
    for node_index, (kind, payload) in enumerate(nodes):
        if kind == "record":
            record = payload
            if isinstance(record, AutoRecord) and record.index in kept_record_indexes:
                units.append(tuple(_record_context_lines(record, max_chars)))
            continue

        text_lines = [
            line
            for line_index, line in enumerate(payload)  # type: ignore[arg-type]
            if (node_index, line_index) in manual_keys
        ]
        if text_lines:
            units.append(tuple(text_lines))

    return _escape_data_block_content(_render_context_units_with_budget(units, max_chars))


def compact_progress(
    progress_path: Path,
    archive_path: Path,
    keep_records: int = 30,
    dry_run: bool = False,
    now: str | None = None,
) -> CompactResult:
    if keep_records < 1:
        raise ValueError("keep_records must be at least 1")

    _validate_archive_path(progress_path, archive_path)

    if not progress_path.is_file():
        return CompactResult(
            archived_count=0,
            kept_count=0,
            total_auto_records=0,
            archive_path=archive_path,
            changed=False,
            dry_run=dry_run,
            summary="",
        )

    compact_time = now or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = _remove_managed_summary(_read_lines(progress_path))
    nodes, records = _parse_nodes(lines)
    total_records = len(records)
    archived_records = records[:-keep_records]
    kept_count = min(total_records, keep_records)
    archived_count = len(archived_records)

    if archived_count == 0:
        return CompactResult(
            archived_count=0,
            kept_count=kept_count,
            total_auto_records=total_records,
            archive_path=archive_path,
            changed=False,
            dry_run=dry_run,
            summary="",
        )

    summary = _render_summary(compact_time, archive_path, archived_records, kept_count)
    if not dry_run:
        archived_indexes = {record.index for record in archived_records}
        kept_lines = _render_nodes(nodes, archived_indexes)
        updated_lines = _insert_summary(kept_lines, summary.splitlines())
        _append_archive(archive_path, compact_time, progress_path, archived_records, kept_count)
        _write_lines(progress_path, updated_lines)

    return CompactResult(
        archived_count=archived_count,
        kept_count=kept_count,
        total_auto_records=total_records,
        archive_path=archive_path,
        changed=not dry_run,
        dry_run=dry_run,
        summary=summary,
    )


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def progress_index_path(progress_path: Path) -> Path:
    return progress_path.parent / "progress-index.ndjson"


def _safe_timestamp(value: str) -> str:
    return re.sub(r"[^0-9]", "", value)[:14] or datetime.now().strftime("%Y%m%d%H%M%S")


def generated_segment_paths(progress_path: Path, session_key: str, now: str, nonce: str) -> tuple[Path, Path]:
    if not re.fullmatch(r"[0-9a-f]{12}|unavailable|[A-Za-z0-9_-]{1,64}", session_key):
        raise ValueError("invalid session key for progress rollover")
    stamp = _safe_timestamp(now)
    safe_nonce = re.sub(r"[^A-Za-z0-9_-]", "", nonce)[:16] or "segment"
    active = progress_path.parent / "progress-active" / session_key / f"active-{stamp}-{safe_nonce}.md"
    archive = progress_path.parent / "progress-archive" / session_key / f"archive-{stamp}-{safe_nonce}.md"
    return active, archive


def _create_text_exclusive(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relative_to_progress_root(progress_path: Path, target: Path) -> str:
    try:
        return target.relative_to(progress_path.parent).as_posix()
    except ValueError:
        raise ValueError("progress rollover path escaped progress directory") from None


def _read_index_events(index_path: Path) -> list[dict[str, object]]:
    if not index_path.is_file():
        return []
    events: list[dict[str, object]] = []
    for line in index_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def latest_rollover_event(progress_path: Path) -> dict[str, object] | None:
    for event in reversed(_read_index_events(progress_index_path(progress_path))):
        if event.get("event") == "rollover":
            return event
    return None


def _is_active_segment_ref(value: str) -> bool:
    parts = PurePosixPath(value).parts
    return (
        len(parts) >= 3
        and parts[0] == "progress-active"
        and all(part not in {"", ".", ".."} for part in parts)
        and parts[-1].startswith("active-")
        and parts[-1].endswith(".md")
    )


def current_active_progress(progress_path: Path) -> Path:
    for event in reversed(_read_index_events(progress_index_path(progress_path))):
        if event.get("event") != "rollover":
            continue
        new_active = event.get("new_active")
        if not isinstance(new_active, str) or not new_active:
            continue
        if not _is_active_segment_ref(new_active):
            continue
        candidate = progress_path.parent / new_active
        try:
            candidate.resolve().relative_to(progress_path.parent.resolve())
        except (OSError, ValueError):
            continue
        if candidate.is_file():
            return candidate
    return progress_path


def _render_rollover_archive(
    *,
    plan_id: str,
    session_key: str,
    source_name: str,
    source_sha256: str,
    created_at: str,
    archived_records: list[AutoRecord],
    kept_count: int,
) -> str:
    body_lines: list[str] = []
    for record in archived_records:
        body_lines.extend(record.lines)
        if body_lines and body_lines[-1].strip():
            body_lines.append("")
    return "\n".join(
        [
            "# Progress Archive",
            "",
            "- Version: 1",
            f"- Plan-ID: {plan_id}",
            f"- Session: {session_key}",
            f"- Source-Progress: {source_name}",
            f"- Source-SHA256: {source_sha256}",
            f"- Created-At: {created_at}",
            f"- Archived Auto Records: {len(archived_records)}",
            f"- Kept Recent Auto Records: {kept_count}",
            "",
            "---BEGIN ARCHIVED AUTO RECORDS---",
            "\n".join(body_lines).rstrip(),
            "---END ARCHIVED AUTO RECORDS---",
            "",
        ]
    )


def _render_rollover_active(
    *,
    plan_id: str,
    session_key: str,
    continued_from: str,
    continued_from_sha256: str,
    archive_relpath: str,
    created_at: str,
    kept_lines: list[str],
) -> str:
    return "\n".join(
        [
            "# Progress Log",
            "",
            "- Version: 1",
            f"- Plan-ID: {plan_id}",
            f"- Session: {session_key}",
            f"- Continued-From: {continued_from}",
            f"- Continued-From-SHA256: {continued_from_sha256}",
            f"- Archive: {archive_relpath}",
            f"- Created-At: {created_at}",
            "",
            "## Recent Progress",
            "",
            "\n".join(kept_lines).strip(),
            "",
        ]
    )


def rollover_progress(
    progress_path: Path,
    *,
    plan_id: str,
    session_key: str,
    keep_records: int = 30,
    dry_run: bool = False,
    now: str | None = None,
    nonce: str | None = None,
) -> RolloverResult:
    if keep_records < 1:
        raise ValueError("keep_records must be at least 1")

    created_at = now or datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    nonce_value = nonce or secrets.token_hex(6)
    active_path, archive_path = generated_segment_paths(progress_path, session_key, created_at, nonce_value)
    index_path = progress_index_path(progress_path)
    source_path = current_active_progress(progress_path)

    if not source_path.is_file():
        return RolloverResult(
            archived_count=0,
            kept_count=0,
            total_auto_records=0,
            archive_path=archive_path,
            active_path=active_path,
            index_path=index_path,
            changed=False,
            dry_run=dry_run,
            summary="",
        )

    source_text = source_path.read_text(encoding="utf-8", errors="replace")
    lines = _remove_managed_summary(source_text.splitlines())
    nodes, records = _parse_nodes(lines)
    total_records = len(records)
    archived_records = records[:-keep_records]
    kept_count = min(total_records, keep_records)
    archived_count = len(archived_records)

    if archived_count == 0:
        return RolloverResult(
            archived_count=0,
            kept_count=kept_count,
            total_auto_records=total_records,
            archive_path=archive_path,
            active_path=active_path,
            index_path=index_path,
            changed=False,
            dry_run=dry_run,
            summary="",
        )

    source_sha = _sha256_text(source_text)
    archived_indexes = {record.index for record in archived_records}
    kept_lines = _render_nodes(nodes, archived_indexes)
    archive_rel = _relative_to_progress_root(progress_path, archive_path)
    active_rel = _relative_to_progress_root(progress_path, active_path)
    source_rel = _relative_to_progress_root(progress_path, source_path)
    archive_text = _render_rollover_archive(
        plan_id=plan_id,
        session_key=session_key,
        source_name=source_rel,
        source_sha256=source_sha,
        created_at=created_at,
        archived_records=archived_records,
        kept_count=kept_count,
    )
    active_text = _render_rollover_active(
        plan_id=plan_id,
        session_key=session_key,
        continued_from=source_rel,
        continued_from_sha256=source_sha,
        archive_relpath=archive_rel,
        created_at=created_at,
        kept_lines=kept_lines,
    )
    summary = _render_summary(created_at, archive_path, archived_records, kept_count)

    if not dry_run:
        if archive_path.exists() or active_path.exists():
            raise FileExistsError("progress rollover segment already exists")
        _create_text_exclusive(archive_path, archive_text)
        _create_text_exclusive(active_path, active_text)
        event = {
            "event": "rollover",
            "version": 1,
            "created_at": created_at,
            "session": session_key,
            "old_active": source_rel,
            "archive": archive_rel,
            "new_active": active_rel,
            "source_sha256": source_sha,
            "archive_sha256": _sha256_text(archive_text),
            "new_active_sha256": _sha256_text(active_text),
            "archived_auto_records": archived_count,
            "kept_recent_auto_records": kept_count,
        }
        index_path.parent.mkdir(parents=True, exist_ok=True)
        with index_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")

    return RolloverResult(
        archived_count=archived_count,
        kept_count=kept_count,
        total_auto_records=total_records,
        archive_path=archive_path,
        active_path=active_path,
        index_path=index_path,
        changed=not dry_run,
        dry_run=dry_run,
        summary=summary,
    )


def _validate_archive_path(progress_path: Path, archive_path: Path) -> None:
    if archive_path.exists() and archive_path.is_dir():
        raise ValueError("archive path must be a file, not a directory")
    try:
        progress_resolved = progress_path.resolve()
        archive_resolved = archive_path.resolve()
    except FileNotFoundError:
        progress_resolved = progress_path.absolute()
        archive_resolved = archive_path.absolute()

    if progress_resolved == archive_resolved:
        raise ValueError("archive path must be different from progress.md")
    if archive_resolved.parent != progress_resolved.parent:
        raise ValueError("archive path must stay in the same directory as progress.md")
    if archive_resolved.suffix.lower() != ".md":
        raise ValueError("archive path must be a Markdown file")
    if archive_path.is_file():
        existing = archive_path.read_text(encoding="utf-8", errors="replace").lstrip()
        if existing and not existing.startswith(ARCHIVE_HEADER):
            raise ValueError("archive path must be empty or an existing progress archive")


def _find_line(lines: list[str], needle: str) -> int | None:
    for index, line in enumerate(lines):
        if line.strip() == needle:
            return index
    return None


def _remove_managed_summary(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == SUMMARY_START:
            skipping = True
            continue
        if skipping:
            if line.strip() == SUMMARY_END:
                skipping = False
            continue
        cleaned.append(line)
    return _collapse_extra_blank_lines(cleaned)


def _collapse_extra_blank_lines(lines: list[str]) -> list[str]:
    collapsed: list[str] = []
    blank_count = 0
    for line in lines:
        if line.strip():
            blank_count = 0
            collapsed.append(line)
            continue
        blank_count += 1
        if blank_count <= 2:
            collapsed.append(line)
    return collapsed


def _parse_nodes(lines: list[str]) -> tuple[list[tuple[str, object]], list[AutoRecord]]:
    nodes: list[tuple[str, object]] = []
    records: list[AutoRecord] = []
    text_buffer: list[str] = []
    index = 0
    line_index = 0
    while line_index < len(lines):
        line = lines[line_index]
        if not line.startswith(AUTO_RECORD_PREFIX):
            text_buffer.append(line)
            line_index += 1
            continue

        if text_buffer:
            nodes.append(("text", tuple(text_buffer)))
            text_buffer = []

        record_lines = [line]
        in_files = False
        line_index += 1
        while line_index < len(lines):
            candidate = lines[line_index]
            if candidate.startswith(AUTO_RECORD_PREFIX):
                break
            if candidate.startswith("#") and candidate.strip():
                break
            if not _is_auto_record_body_line(candidate, in_files=in_files):
                break
            record_lines.append(candidate)
            if candidate.startswith("- Files:"):
                in_files = True
            elif candidate.strip() and not candidate.startswith("  - "):
                in_files = False
            line_index += 1

        record = _make_record(index, record_lines)
        records.append(record)
        nodes.append(("record", record))
        index += 1

    if text_buffer:
        nodes.append(("text", tuple(text_buffer)))
    return nodes, records


def _is_auto_record_body_line(line: str, *, in_files: bool) -> bool:
    if not line.strip():
        return True
    if in_files and line.startswith("  - "):
        return True
    if line.startswith("- Files:"):
        return True
    return line.startswith(AUTO_RECORD_FIELDS)


def _make_record(index: int, lines: list[str]) -> AutoRecord:
    timestamp = lines[0][len(AUTO_RECORD_PREFIX) :].strip()
    tool = ""
    session = ""
    plan_source = ""
    files: list[str] = []
    in_files = False
    for line in lines[1:]:
        if line.startswith("- Tool:"):
            tool = line.split(":", 1)[1].strip()
            in_files = False
            continue
        if line.startswith("- Session:"):
            session = line.split(":", 1)[1].strip()
            in_files = False
            continue
        if line.startswith("- Plan-Source:"):
            plan_source = line.split(":", 1)[1].strip()
            in_files = False
            continue
        if line.startswith("- Files:"):
            in_files = True
            continue
        if line.startswith("- ") and not line.startswith("  - "):
            in_files = False
        if not in_files:
            continue
        match = re.search(r"`([^`]+)`", line)
        if match:
            files.append(match.group(1))
    return AutoRecord(
        index=index,
        lines=tuple(lines),
        timestamp=timestamp,
        tool=tool,
        session=session,
        plan_source=plan_source,
        files=tuple(files),
    )


def _recent_manual_line_keys(nodes: list[tuple[str, object]], limit: int) -> set[tuple[int, int]]:
    if limit < 1:
        return set()

    keys: list[tuple[int, int]] = []
    for node_index, (kind, payload) in enumerate(nodes):
        if kind != "text":
            continue
        for line_index, line in enumerate(payload):  # type: ignore[arg-type]
            if line.strip():
                keys.append((node_index, line_index))
    return set(keys[-limit:])


def _record_context_lines(record: AutoRecord, max_chars: int) -> tuple[str, ...]:
    text = "\n".join(record.lines)
    if len(text) <= max_chars:
        return record.lines
    return _safe_record_summary_lines(record)


def _safe_record_summary_lines(record: AutoRecord) -> tuple[str, ...]:
    tool = record.tool or "unknown"
    timestamp = record.timestamp or "unknown"
    file_count = len(record.files)
    lines = [
        f"{AUTO_RECORD_PREFIX}{timestamp}",
        f"- Tool: {tool}",
    ]
    if record.session:
        lines.append(f"- Session: {record.session}")
    if record.plan_source:
        lines.append(f"- Plan-Source: {record.plan_source}")
    lines.extend(
        [
            f"- Files: {file_count} paths omitted due to size",
            "- Note: oversized auto record summarized for prompt safety",
        ]
    )
    return tuple(lines)


def _render_context_units_with_budget(units: list[tuple[str, ...]], max_chars: int) -> str:
    kept = list(units)
    truncated = False
    while kept and len(_join_units(kept)) > max_chars:
        kept.pop(0)
        truncated = True

    if not kept:
        return PROGRESS_TRUNCATION_NOTE if truncated else ""

    text = _join_units(kept)
    if truncated:
        text = f"{PROGRESS_TRUNCATION_NOTE}\n\n{text}"
    return text


def _join_units(units: list[tuple[str, ...]]) -> str:
    rendered: list[str] = []
    for unit in units:
        if rendered and rendered[-1].strip():
            rendered.append("")
        rendered.extend(unit)
    return "\n".join(rendered).strip()


def _escape_data_block_content(content: str) -> str:
    escaped: list[str] = []
    for line in content.splitlines():
        if DATA_BLOCK_DELIMITER_RE.fullmatch(line.strip()):
            escaped.append(f"[escaped delimiter] {line}")
        else:
            escaped.append(line)
    return "\n".join(escaped)


def _render_nodes(nodes: list[tuple[str, object]], archived_indexes: set[int]) -> list[str]:
    rendered: list[str] = []
    for kind, payload in nodes:
        if kind == "text":
            rendered.extend(payload)  # type: ignore[arg-type]
            continue
        record = payload
        if isinstance(record, AutoRecord) and record.index not in archived_indexes:
            rendered.extend(record.lines)
    return _collapse_extra_blank_lines(rendered)


def _insert_summary(lines: list[str], summary_lines: list[str]) -> list[str]:
    if not summary_lines:
        return lines
    if lines and lines[0].startswith("# "):
        rest = list(lines[1:])
        while rest and not rest[0].strip():
            rest.pop(0)
        return [lines[0], "", *summary_lines, "", *rest]
    return [*summary_lines, "", *lines]


def _render_summary(
    compact_time: str,
    archive_path: Path,
    archived_records: list[AutoRecord],
    kept_count: int,
) -> str:
    tools = Counter(record.tool or "unknown" for record in archived_records)
    files = sorted({file for record in archived_records for file in record.files})
    timestamps = [record.timestamp for record in archived_records if record.timestamp]
    time_range = f"{timestamps[0]} to {timestamps[-1]}" if timestamps else "unknown"
    tool_text = ", ".join(f"{tool}={count}" for tool, count in sorted(tools.items())) or "none"
    lines = [
        SUMMARY_START,
        "## Compacted Progress Summary",
        "",
        f"- Last Compact: {compact_time}",
        f"- Archive: {archive_path.name}",
        f"- Archived Auto Records: {len(archived_records)}",
        f"- Archived Range: {time_range}",
        f"- Kept Recent Auto Records: {kept_count}",
        f"- Tools: {tool_text}",
        f"- Unique Files: {len(files)}",
        "- Note: Archived records are objective hook facts. Agent summaries remain interpretive and should be verified when accuracy matters.",
        SUMMARY_END,
    ]
    return "\n".join(lines)


def _append_archive(
    archive_path: Path,
    compact_time: str,
    progress_path: Path,
    archived_records: list[AutoRecord],
    kept_count: int,
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    existing = archive_path.read_text(encoding="utf-8", errors="replace") if archive_path.is_file() else ""
    header = "" if existing.strip() else "# Progress Archive\n\n"
    summary = _render_archive_summary(compact_time, progress_path, archived_records, kept_count)
    body_lines: list[str] = []
    for record in archived_records:
        body_lines.extend(record.lines)
        if body_lines and body_lines[-1].strip():
            body_lines.append("")
    batch = "\n".join(
        [
            summary,
            "",
            "---BEGIN ARCHIVED AUTO RECORDS---",
            "\n".join(body_lines).rstrip(),
            "---END ARCHIVED AUTO RECORDS---",
            "",
        ]
    )
    archive_path.write_text(existing.rstrip() + ("\n\n" if existing.strip() else "") + header + batch, encoding="utf-8", newline="\n")


def _render_archive_summary(
    compact_time: str,
    progress_path: Path,
    archived_records: list[AutoRecord],
    kept_count: int,
) -> str:
    tools = Counter(record.tool or "unknown" for record in archived_records)
    files = sorted({file for record in archived_records for file in record.files})
    timestamps = [record.timestamp for record in archived_records if record.timestamp]
    time_range = f"{timestamps[0]} to {timestamps[-1]}" if timestamps else "unknown"
    tool_text = ", ".join(f"{tool}={count}" for tool, count in sorted(tools.items())) or "none"
    return "\n".join(
        [
            f"## Compact Batch: {compact_time}",
            f"- Source: {progress_path.name}",
            f"- Archived Auto Records: {len(archived_records)}",
            f"- Archived Range: {time_range}",
            f"- Kept Recent Auto Records: {kept_count}",
            f"- Tools: {tool_text}",
            f"- Unique Files: {len(files)}",
        ]
    )
