"""
Provider-neutral lesson generation engine for Muallim AI.
Supports OpenAI and Anthropic through optional official SDKs.
The app never silently claims that AI output is verified: each lesson carries source references and review status.
"""
from __future__ import annotations
import json
import os
from typing import Any

SYSTEM_PROMPT = """أنت مؤلف تعليمي دقيق. حوّل النص المصدري المعطى إلى درس عربي واضح ومفصل.
قواعد إلزامية:
1) لا تنسب إلى المصدر معلومة غير موجودة فيه.
2) ميّز بين مقتطفات المصدر والشرح الإضافي.
3) إذا كان النص غير كافٍ، صرّح بذلك ولا تخترع تتمة.
4) أرفق أرقام الصفحات لكل فكرة أساسية كلما توفرت.
5) أنشئ أسئلة متنوعة لا تكرر السؤال نفسه بصياغة مختلفة.
6) لا تدّع أن المراجعة العلمية البشرية تمت.
7) أخرج JSON صالحًا فقط وفق المخطط المطلوب.
"""

LESSON_SCHEMA_DESCRIPTION = {
    "title": "string",
    "source_summary": "string",
    "learning_objectives": ["string"],
    "key_concepts": [{"concept": "string", "explanation": "string", "source_pages": ["integer"]}],
    "lesson_sections": [{"heading": "string", "explanation": "string", "source_pages": ["integer"]}],
    "original_examples": [{"example": "string", "analysis": "string", "source_pages": ["integer"]}],
    "additional_examples": [{"example": "string", "why_it_helps": "string", "needs_subject_review": True}],
    "common_misunderstandings": ["string"],
    "exercises": [{"type": "recall|application|analysis|true_false|multiple_choice", "question": "string", "choices": ["string"], "answer": "string", "explanation": "string", "source_pages": ["integer"]}],
    "coverage_gaps": ["string"],
    "review_status": "ai_draft_needs_human_review"
}

def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("لم يرجع النموذج كائن JSON صالحًا.")
    result = json.loads(text[start:end + 1])
    if not isinstance(result, dict):
        raise ValueError("يجب أن تكون نتيجة النموذج كائن JSON.")
    return result

def validate_lesson(data: dict[str, Any]) -> list[str]:
    issues = []
    required = ["title", "learning_objectives", "lesson_sections", "exercises", "review_status"]
    for key in required:
        if key not in data:
            issues.append(f"حقل مفقود: {key}")
    if not isinstance(data.get("learning_objectives", []), list):
        issues.append("learning_objectives يجب أن تكون قائمة.")
    if not isinstance(data.get("lesson_sections", []), list) or not data.get("lesson_sections"):
        issues.append("لا توجد أقسام شرح في الدرس.")
    if not isinstance(data.get("exercises", []), list) or len(data.get("exercises", [])) < 3:
        issues.append("يجب إنشاء ثلاثة تدريبات على الأقل.")
    seen = set()
    for i, q in enumerate(data.get("exercises", []), start=1):
        question = " ".join(str(q.get("question", "")).casefold().split())
        if not question:
            issues.append(f"التدريب {i} بلا نص سؤال.")
        elif question in seen:
            issues.append(f"تكرار حرفي في السؤال {i}.")
        seen.add(question)
        if not q.get("answer"):
            issues.append(f"التدريب {i} بلا إجابة.")
    data["review_status"] = "ai_draft_needs_human_review"
    data["validation_issues"] = issues
    data["ready_to_publish"] = False
    return issues

def _build_user_prompt(title: str, pages: list[dict[str, Any]], desired_exercises: int) -> str:
    source = []
    for p in pages:
        source.append(f"[رقم الصفحة: {p['page']}]\n{p['text']}")
    return f"""أنشئ مسودة درس بعنوان: {title}
عدد التدريبات المطلوب: {desired_exercises}
استخدم النص التالي فقط بوصفه المصدر الأساسي. اذكر الفجوات بدل تخمين المحتوى.
المخطط المطلوب:
{json.dumps(LESSON_SCHEMA_DESCRIPTION, ensure_ascii=False)}
النص المصدر:
{chr(10).join(source)}
"""

def generate_lesson(title: str, pages: list[dict[str, Any]], desired_exercises: int = 8,
                    provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    if not pages or not any(str(p.get("text", "")).strip() for p in pages):
        raise ValueError("لا يوجد نص مصدر صالح.")
    provider = (provider or os.getenv("AI_PROVIDER", "openai")).lower()
    user_prompt = _build_user_prompt(title, pages, max(3, min(desired_exercises, 30)))
    if provider == "openai":
        data = _call_openai(user_prompt, model or os.getenv("OPENAI_MODEL", "gpt-4.1"))
    elif provider == "anthropic":
        data = _call_anthropic(user_prompt, model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"))
    else:
        raise ValueError("مزود غير مدعوم. استخدم openai أو anthropic.")
    validate_lesson(data)
    data["source_page_range"] = sorted({int(p["page"]) for p in pages if "page" in p})
    data["provider"] = provider
    data["model"] = model or (os.getenv("OPENAI_MODEL") if provider == "openai" else os.getenv("ANTHROPIC_MODEL"))
    return data

def _call_openai(user_prompt: str, model: str) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("لم يتم ضبط OPENAI_API_KEY في متغيرات البيئة.")
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError("ثبّت حزمة openai باستخدام pip install openai") from e
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
    )
    return _extract_json(response.choices[0].message.content or "")

def _call_anthropic(user_prompt: str, model: str) -> dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("لم يتم ضبط ANTHROPIC_API_KEY في متغيرات البيئة.")
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise RuntimeError("ثبّت حزمة anthropic باستخدام pip install anthropic") from e
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=7000,
        temperature=0.2,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "\n".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    return _extract_json(text)
