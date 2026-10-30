"""Curriculum planning helpers; deliberately deterministic and reviewable."""
from __future__ import annotations
import re
from typing import Any

ARABIC_NUMERALS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

def split_into_chunks(pages: list[dict[str, Any]], max_chars: int = 9000) -> list[dict[str, Any]]:
    """Group adjacent pages without losing source page references."""
    chunks, current, count = [], [], 0
    for page in pages:
        text = str(page.get("text", "")).strip()
        if not text:
            continue
        # A single very large page is split at paragraph boundaries.
        pieces = re.split(r"\n\s*\n", text)
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            if current and count + len(piece) > max_chars:
                chunks.append({"pages": current, "text": "\n\n".join(x["text"] for x in current)})
                current, count = [], 0
            current.append({"page": int(page["page"]), "text": piece})
            count += len(piece)
    if current:
        chunks.append({"pages": current, "text": "\n\n".join(x["text"] for x in current)})
    return chunks

def suggest_lessons(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Suggest candidate headings; user should approve before course generation."""
    candidates = []
    seen = set()
    heading_patterns = [
        r"^\s*(?:الدرس|الفصل|الباب|الوحدة)\s*(?:[\d٠-٩一二三四五六七八九]+|الأول|الثاني|الثالث|الرابع|الخامس|السادس|السابع|الثامن|التاسع|العاشر)?\s*[:：\-–.]?\s*(.{2,100})$",
        r"^\s*(?:\d{1,2}|[٠-٩]{1,2})[.)\-–]\s*(.{3,100})$",
    ]
    for p in pages:
        for line in str(p.get("text", "")).splitlines():
            line = " ".join(line.split()).strip(" \t•*-")
            if len(line) < 4 or len(line) > 100:
                continue
            for pattern in heading_patterns:
                m = re.match(pattern, line, flags=re.IGNORECASE)
                if m:
                    title = (m.group(1) or line).strip(" :：-.")
                    title = re.sub(r"^(?:الأول|الأولى|الثاني|الثانية|الثالث|الثالثة|الرابع|الرابعة|الخامس|الخامسة)\s*[:：\-–.]?\s*", "", title)
                    key = title.casefold()
                    if key not in seen:
                        candidates.append({"title": title, "source_pages": [int(p["page"])], "status": "suggested"})
                        seen.add(key)
                    break
    return candidates
