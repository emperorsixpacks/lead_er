import json
import re

import httpx

from app.config import settings

SYSTEM = """You write the personalized opening of a cold B2B email.
You are given structured info about a business: name, category, city, and text scraped from its website.
Return ONLY a JSON object (no prose, no markdown, no code fences) with exactly these keys:

{
  "subject_line": "<short subject, under 40 characters, that references the business>",
  "hook": "<the opening line, 1-2 sentences, referencing something SPECIFIC about this business: what they sell, a specialty, years in business, a recent project, or a notable detail>",
  "facts": ["<concrete, verifiable fact>", "<fact>", "<fact>"],
  "contact_name": "<the founder / owner / principal's full name if the text names one, else empty string>"
}

Rules:
- 2 to 3 facts max.
- contact_name: only a real person's name found in the text (e.g. "John Smith", "Dr. Jane Doe"). Leave "" if no name is given. Never invent one.
- Never invent facts. Only use what is in the provided text.
- No generic flattery ("I love what you do", "great company").
- No assumptions about the reader's location, identity, or title.
- Write like a real person who actually looked at their site, not a marketer.
- If there is nothing to work with, return empty strings and an empty list.
"""

_KEYS = ("subject_line", "hook", "contact_name")


def _unescape(s: str) -> str:
    try:
        return s.encode().decode("unicode_escape")
    except Exception:
        return s


def _extract_json(text: str) -> dict:
    if not text:
        return {}
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Salvage: pull each field with regex if the model emitted sloppy JSON.
    out: dict = {}
    for key in _KEYS:
        m = re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
        if m:
            out[key] = _unescape(m.group(1))
    facts = re.search(r'"facts"\s*:\s*\[(.*?)\]', text, re.DOTALL)
    if facts:
        out["facts"] = [_unescape(f) for f in re.findall(r'"((?:[^"\\]|\\.)*)"', facts.group(1))]
    return out


async def personalize(
    *,
    business_name: str = "",
    category: str = "",
    city: str = "",
    site_text: str = "",
) -> dict:
    """Return {'subject_line', 'hook', 'facts'} via an OpenAI-compatible API.

    Works with Ollama (no key required — leave LLM_API_KEY empty) or any
    OpenAI-compatible provider (set LLM_BASE_URL + LLM_API_KEY + LLM_MODEL).
    """
    if not settings.llm_model:
        return {"subject_line": "", "hook": "", "facts": []}

    context = "\n".join(
        filter(
            None,
            [
                f"Business name: {business_name}",
                f"Category: {category}",
                f"City: {city}",
                "Website text:\n" + (site_text or "")[:8000],
            ],
        )
    )

    headers = {"content-type": "application/json"}
    if settings.llm_api_key:
        headers["Authorization"] = f"Bearer {settings.llm_api_key}"

    body = {
        "model": settings.llm_model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": context},
        ],
        "temperature": 0.3,
        # Gemini (and some reasoning models) require non-streaming + a max_tokens
        # or they consume the whole budget "thinking" and return nothing.
        "stream": False,
        "max_tokens": 800,
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            json=body,
            headers=headers,
            timeout=120,
        )
        r.raise_for_status()
        data = r.json()

    content = data["choices"][0]["message"]["content"]
    return _extract_json(content)
