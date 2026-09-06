# llm/translation.py
from llm.prompts import SYMPTOM_TRANSLATION_PROMPT
from llm.client import get_fast_llm_completion


async def translate_to_english(hindi_text: str) -> str:
    prompt = SYMPTOM_TRANSLATION_PROMPT.format(farmer_text=hindi_text)

    print(f"\n[DEBUG] Prompt sent to LLM:\n{prompt}\n")  # temporary

    raw_response = await get_fast_llm_completion(prompt, temperature=0.0)

    # temporary — note the !r to reveal hidden whitespace/None
    print(f"[DEBUG] Raw LLM response: {raw_response!r}")

    translated = raw_response.strip()
    return translated
