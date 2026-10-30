import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from curriculum import split_into_chunks, suggest_lessons
from ai_engine import validate_lesson

def test_chunk_keeps_source_pages():
    pages = [{"page": 1, "text": "فقرة أولى.\n\nفقرة ثانية."}, {"page": 2, "text": "فقرة ثالثة."}]
    chunks = split_into_chunks(pages, max_chars=100)
    assert chunks
    assert all("text" in c and "pages" in c for c in chunks)
    assert {p["page"] for c in chunks for p in c["pages"]} == {1, 2}

def test_heading_suggestions():
    pages = [{"page": 7, "text": "الدرس الأول: الجملة المفيدة\nشرح الدرس"}]
    result = suggest_lessons(pages)
    assert result and "الجملة المفيدة" in result[0]["title"]

def test_validation_flags_duplicate_questions():
    lesson = {
        "title": "اختبار",
        "learning_objectives": ["فهم"],
        "lesson_sections": [{"heading": "شرح", "explanation": "نص"}],
        "exercises": [
            {"question": "ما القاعدة؟", "answer": "القاعدة"},
            {"question": "ما القاعدة؟", "answer": "القاعدة"},
            {"question": "اذكر مثالًا", "answer": "مثال"}
        ],
        "review_status": "x"
    }
    issues = validate_lesson(lesson)
    assert any("تكرار" in issue for issue in issues)
    assert lesson["ready_to_publish"] is False
