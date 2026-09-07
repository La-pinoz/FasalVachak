# llm/translation.py
from llm.prompts import SYMPTOM_TRANSLATION_PROMPT
from llm.client import get_fast_llm_completion


async def translate_to_english(hindi_text: str) -> str:
    prompt = SYMPTOM_TRANSLATION_PROMPT.format(farmer_text=hindi_text)

    raw_response = await get_fast_llm_completion(prompt, temperature=0.0)

    translated = raw_response.strip()
    return translated
