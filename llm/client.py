import os
from dotenv import load_dotenv
from groq import AsyncGroq

load_dotenv()

groq_client = AsyncGroq(
    api_key=os.getenv("GROQ_API_KEY")
)


async def get_fast_llm_completion(prompt: str, temperature: float = 0.0) -> str:
    """
    Used for Phase 0 (Crop Classifier) and Phase 3 (Yes/No Classifier).
    Optimized for absolute minimum latency and tiny outputs.
    """
    response = await groq_client.chat.completions.create(
        messages=[
            {"role": "user", "content": prompt}
        ],
        # Note: Replace "openai/gpt-oss-120b" with the exact string expected by your endpoint.
        # Groq's standard models are usually "llama3-70b-8192" or "mixtral-8x7b-32768".
        model="openai/gpt-oss-120b",
        temperature=temperature,
    )
    return response.choices[0].message.content


async def get_reasoning_completion(prompt: str, temperature: float = 0.2) -> str:
    response = await groq_client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a helpful agricultural assistant."},
            {"role": "user", "content": prompt}
        ],
        model="openai/gpt-oss-120b",
        temperature=temperature,
    )
    return response.choices[0].message.content
