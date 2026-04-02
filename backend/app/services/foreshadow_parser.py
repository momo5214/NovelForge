from __future__ import annotations

import re
from typing import Any


FORESHADOW_ID_RE = re.compile(r"([A-Z]{2,3}\d{3})")
FORESHADOW_DUE_RE = re.compile(r"[（(]\s*第\s*(\d+)\s*章前必须回收\s*[）)]")
FORESHADOW_PREFIX_RE = re.compile(r"^\s*([A-Z]{2,3}\d{3})(?:\(([^)]*)\))?")
FORESHADOW_SPLIT_RE = re.compile(r"\s*[-—–:：]\s*")

FORESHADOW_TYPE_MAP = {
    "MF": "goal",
    "CF": "person",
    "YF": "item",
    "AF": "item",
    "SF": "other",
}

FORESHADOW_LABEL_MAP = {
    "MF": "主线伏笔",
    "CF": "人物伏笔",
    "YF": "一般伏笔",
    "AF": "支线伏笔",
    "SF": "悬念伏笔",
}


def _normalize_text(value: Any) -> str:
    return str(value or "").replace("\u3000", " ").strip()


def infer_foreshadow_type(foreshadow_id: str | None) -> str:
    prefix = str(foreshadow_id or "").strip().upper()[:2]
    return FORESHADOW_TYPE_MAP.get(prefix, "other")


def infer_foreshadow_label(foreshadow_id: str | None) -> str:
    prefix = str(foreshadow_id or "").strip().upper()[:2]
    return FORESHADOW_LABEL_MAP.get(prefix, "伏笔")


def parse_foreshadow_entry(entry: Any) -> dict[str, Any]:
    raw = _normalize_text(entry)
    if not raw:
        return {}

    line = re.sub(r"^[\-\*\d\.\)、\s]+", "", raw).strip()
    match = FORESHADOW_PREFIX_RE.match(line)
    foreshadow_id = match.group(1).strip() if match else ""
    inline_label = _normalize_text(match.group(2)) if match and match.group(2) else ""

    due_match = FORESHADOW_DUE_RE.search(line)
    due_chapter_number = int(due_match.group(1)) if due_match else None
    line_wo_due = FORESHADOW_DUE_RE.sub("", line).strip()

    if match:
        line_wo_due = line_wo_due[match.end():].strip()
        line_wo_due = re.sub(r"^[\-—–:：\s]+", "", line_wo_due).strip()

    parts = [part.strip() for part in FORESHADOW_SPLIT_RE.split(line_wo_due) if part.strip()]
    display_title = parts[0] if parts else ""
    action = parts[1] if len(parts) > 1 else ""
    description = " - ".join(parts[2:]) if len(parts) > 2 else ""
    summary_text = " ".join([action, description]).strip()

    status = "resolved" if ("已回收" in line or "-回收-" in line or "状态:已回收" in line) else "open"

    if not display_title and foreshadow_id:
        display_title = infer_foreshadow_label(foreshadow_id)

    return {
        "foreshadow_id": foreshadow_id or None,
        "display_title": display_title,
        "foreshadow_type": infer_foreshadow_type(foreshadow_id),
        "label": inline_label or infer_foreshadow_label(foreshadow_id),
        "action": action,
        "description": description,
        "summary_text": summary_text,
        "due_chapter_number": due_chapter_number,
        "status": status,
        "raw_text": raw,
    }


def normalize_foreshadow_plan(items: Any) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    source_items = items if isinstance(items, list) else []

    for item in source_items:
        if isinstance(item, dict):
            parsed = parse_foreshadow_entry(item.get("raw_text") or item.get("title") or item.get("display_title") or "")
            foreshadow_id = _normalize_text(item.get("foreshadow_id")) or parsed.get("foreshadow_id") or ""
            if not foreshadow_id:
                continue
            display_title = _normalize_text(item.get("display_title")) or parsed.get("display_title") or infer_foreshadow_label(foreshadow_id)
            description = _normalize_text(item.get("description")) or parsed.get("description") or ""
            action = _normalize_text(item.get("action")) or parsed.get("action") or ""
            due_value = item.get("due_chapter_number", parsed.get("due_chapter_number"))
            try:
                due_chapter_number = int(due_value) if due_value not in (None, "") else None
            except Exception:
                due_chapter_number = parsed.get("due_chapter_number")
            normalized.append({
                "foreshadow_id": foreshadow_id,
                "display_title": display_title,
                "foreshadow_type": _normalize_text(item.get("foreshadow_type")) or parsed.get("foreshadow_type") or infer_foreshadow_type(foreshadow_id),
                "action": action,
                "description": description,
                "due_chapter_number": due_chapter_number,
                "status": _normalize_text(item.get("status")) or parsed.get("status") or "open",
                "raw_text": _normalize_text(item.get("raw_text")) or parsed.get("raw_text") or "",
            })
            continue

        parsed = parse_foreshadow_entry(item)
        if parsed.get("foreshadow_id"):
            normalized.append({
                "foreshadow_id": parsed["foreshadow_id"],
                "display_title": parsed.get("display_title") or infer_foreshadow_label(parsed["foreshadow_id"]),
                "foreshadow_type": parsed.get("foreshadow_type") or infer_foreshadow_type(parsed["foreshadow_id"]),
                "action": parsed.get("action") or "",
                "description": parsed.get("description") or "",
                "due_chapter_number": parsed.get("due_chapter_number"),
                "status": parsed.get("status") or "open",
                "raw_text": parsed.get("raw_text") or "",
            })

    deduped: dict[str, dict[str, Any]] = {}
    for item in normalized:
        deduped[item["foreshadow_id"]] = item
    return list(deduped.values())


def extract_foreshadow_ids(items: Any) -> list[str]:
    return [item.get("foreshadow_id", "") for item in normalize_foreshadow_plan(items) if item.get("foreshadow_id")]


def parse_foreshadow_ledger_text(ledger_text: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in _normalize_text(ledger_text).splitlines():
        parsed = parse_foreshadow_entry(line)
        if parsed.get("foreshadow_id"):
            rows.append(parsed)
    return rows


def foreshadow_lifecycle_gate(
    chapter_number: Any,
    ledger_text: Any,
    planned_items: Any,
) -> dict[str, Any]:
    try:
        current_chapter = int(chapter_number or 0)
    except Exception:
        current_chapter = 0

    planned = normalize_foreshadow_plan(planned_items)
    planned_ids = {item["foreshadow_id"] for item in planned if item.get("foreshadow_id")}
    unresolved_items = [
        item
        for item in parse_foreshadow_ledger_text(ledger_text)
        if item.get("status") != "resolved"
    ]
    overdue_items = [
        item
        for item in unresolved_items
        if item.get("due_chapter_number") is not None and int(item["due_chapter_number"]) <= current_chapter
    ]
    missing_due_items = [
        item
        for item in overdue_items
        if item.get("foreshadow_id") and item["foreshadow_id"] not in planned_ids
    ]

    return {
        "allow": len(missing_due_items) == 0,
        "planned_ids": sorted(planned_ids),
        "overdue_ids": [item["foreshadow_id"] for item in overdue_items if item.get("foreshadow_id")],
        "missing_due_ids": [item["foreshadow_id"] for item in missing_due_items if item.get("foreshadow_id")],
        "missing_due_titles": [item.get("display_title") or item.get("foreshadow_id") for item in missing_due_items],
        "message": (
            "当前章节目录未响应以下到期未回收伏笔："
            + "、".join([item.get("display_title") or item.get("foreshadow_id") or "" for item in missing_due_items])
        ) if missing_due_items else "通过伏笔生命周期门禁",
    }


def build_foreshadow_register_payload(
    foreshadow_ids_text: Any,
    report_text: Any,
    chapter_id: Any = None,
    current_chapter_number: Any = None,
) -> list[dict[str, Any]]:
    report_rows = parse_foreshadow_ledger_text(report_text)
    report_by_id = {
        item["foreshadow_id"]: item
        for item in report_rows
        if item.get("foreshadow_id")
    }
    try:
        normalized_chapter_id = int(chapter_id) if chapter_id not in (None, "") else None
    except Exception:
        normalized_chapter_id = None
    try:
        chapter_number = int(current_chapter_number) if current_chapter_number not in (None, "") else None
    except Exception:
        chapter_number = None

    payload: list[dict[str, Any]] = []
    for foreshadow_id in [line.strip() for line in _normalize_text(foreshadow_ids_text).splitlines() if line.strip()]:
        parsed = report_by_id.get(foreshadow_id) or parse_foreshadow_entry(foreshadow_id)
        payload.append({
            "foreshadow_id": foreshadow_id,
            "title": f"{foreshadow_id} {parsed.get('display_title') or infer_foreshadow_label(foreshadow_id)}".strip(),
            "display_title": parsed.get("display_title") or infer_foreshadow_label(foreshadow_id),
            "type": parsed.get("foreshadow_type") or infer_foreshadow_type(foreshadow_id),
            "note": parsed.get("raw_text") or _normalize_text(report_text)[:200],
            "chapter_id": normalized_chapter_id,
            "status": parsed.get("status") or "open",
            "due_chapter_number": parsed.get("due_chapter_number"),
            "first_chapter_number": chapter_number,
            "last_chapter_number": chapter_number,
        })
    return payload


def build_open_foreshadow_ledger(report_text: Any) -> str:
    lines = [
        line.strip()
        for line in _normalize_text(report_text).splitlines()
        if line.strip() and "已回收" not in line and "-回收-" not in line
    ]
    return "\n".join(lines).strip() or "无未回收伏笔"


def build_foreshadow_processing_vars(
    chapter_number: Any,
    chapter_id: Any,
    chapter_title: Any,
    chapter_blueprint: Any,
    chapter_text: Any,
    existing_ledger: Any,
    planned_items: Any,
) -> dict[str, Any]:
    try:
        novel_number = int(chapter_number or 0)
    except Exception:
        novel_number = 0
    try:
        normalized_chapter_id = int(chapter_id or 0)
    except Exception:
        normalized_chapter_id = 0

    normalized_plan = normalize_foreshadow_plan(planned_items)
    planned_entries = "\n".join([
        str(item.get("raw_text") or "").strip()
        for item in normalized_plan
        if str(item.get("raw_text") or "").strip()
    ]).strip()
    existing_ledger_text = _normalize_text(existing_ledger)
    combined_entries = (
        planned_entries
        + ("\n" if planned_entries and existing_ledger_text else "")
        + existing_ledger_text
    ).strip()
    fallback_entries = (
        "YF001(一般伏笔)-待提取-埋设-待提取（第6章前必须回收）\n"
        "MF001(主线伏笔)-待提取-强化-待提取（第20章前必须回收）\n"
        "CF001(人物伏笔)-待提取-触发-待提取（第15章前必须回收）"
    )
    foreshadowing_entries = combined_entries or fallback_entries
    foreshadow_ids = extract_foreshadow_ids(normalized_plan)
    if not foreshadow_ids:
        foreshadow_ids = [item.get("foreshadow_id") for item in parse_foreshadow_ledger_text(foreshadowing_entries) if item.get("foreshadow_id")]

    return {
        "novel_number": novel_number,
        "chapter_id": normalized_chapter_id,
        "chapter_title": _normalize_text(chapter_title) or f"第{novel_number}章",
        "chapter_blueprint": _normalize_text(chapter_blueprint),
        "chapter_text": _normalize_text(chapter_text),
        "existing_ledger": existing_ledger_text,
        "planned_foreshadow_entries": planned_entries,
        "foreshadowing_entries": foreshadowing_entries,
        "foreshadowing_ids": "\n".join(dict.fromkeys([fid for fid in foreshadow_ids if fid])) or "YF001\nMF001\nCF001",
    }
