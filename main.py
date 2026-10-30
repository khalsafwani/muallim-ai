from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import fitz
import re
import os
from typing import List

from curriculum import suggest_lessons, split_into_chunks
from ai_engine import generate_lesson

app = FastAPI(title="Muallim AI API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict before production.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PageText(BaseModel):
    page: int
    text: str

class ExtractResponse(BaseModel):
    filename: str
    page_count: int
    extracted_pages: int
    text_chars: int
    scanned_or_empty_pages: List[int]
    pages: List[PageText]
    suggested_lessons: list[dict] = []

class GenerateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    pages: list[PageText]
    desired_exercises: int = Field(default=8, ge=3, le=30)
    provider: str | None = None
    model: str | None = None

@app.get("/")
def health():
    return {"status": "ok", "service": "Muallim AI API", "version": "0.2.0",
            "capabilities": ["pdf_text_extraction", "lesson_outline_suggestions", "ai_lesson_generation"]}

@app.post("/api/extract", response_model=ExtractResponse)
async def extract_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="يرجى رفع ملف PDF فقط.")
    data = await file.read()
    max_mb = int(os.getenv("MAX_UPLOAD_MB", "40"))
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"الحد الأقصى لحجم الملف {max_mb} ميغابايت.")
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise HTTPException(status_code=400, detail="تعذر قراءة الملف. تأكد أنه PDF صالح.")
    pages, empty, total = [], [], 0
    for idx, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        if len(text) < 30:
            empty.append(idx)
        total += len(text)
        pages.append(PageText(page=idx, text=text))
    doc.close()
    page_dicts = [p.model_dump() for p in pages]
    return ExtractResponse(
        filename=file.filename, page_count=len(pages),
        extracted_pages=len(pages)-len(empty), text_chars=total,
        scanned_or_empty_pages=empty, pages=pages,
        suggested_lessons=suggest_lessons(page_dicts)
    )

@app.post("/api/plan")
def plan_chunks(req: GenerateRequest):
    page_dicts = [p.model_dump() for p in req.pages]
    chunks = split_into_chunks(page_dicts)
    return {
        "title": req.title,
        "chunk_count": len(chunks),
        "chunks": [{"index": i+1, "source_pages": sorted({p["page"] for p in c["pages"]}),
                    "characters": len(c["text"]), "preview": c["text"][:350]}
                   for i, c in enumerate(chunks)],
        "lesson_suggestions": suggest_lessons(page_dicts),
        "notice": "هذه خريطة أولية مقترحة؛ راجع عناوين الدروس قبل التوليد."
    }

@app.post("/api/generate-lesson")
def create_lesson(req: GenerateRequest):
    try:
        lesson = generate_lesson(
            title=req.title,
            pages=[p.model_dump() for p in req.pages],
            desired_exercises=req.desired_exercises,
            provider=req.provider,
            model=req.model
        )
        return lesson
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        # Avoid returning provider secrets or full internals to clients.
        raise HTTPException(status_code=502, detail=f"تعذر إنشاء الدرس. راجع إعدادات المزود والسجل المحلي. ({type(e).__name__})")

@app.post("/api/demo-lesson")
def demo_lesson(req: GenerateRequest):
    clean_pages = [p.model_dump() for p in req.pages if p.text.strip()]
    if not clean_pages:
        raise HTTPException(status_code=400, detail="لا يوجد نص كافٍ لإنشاء درس.")
    return {
        "title": req.title,
        "notice": "عرض تجريبي دون استدعاء نموذج ذكاء اصطناعي.",
        "source_page_range": [p.page for p in clean_pages],
        "source_excerpt": "\n\n".join(p.text for p in clean_pages)[:2200],
        "review_status": "demo_not_ready_to_publish",
        "ready_to_publish": False
    }
