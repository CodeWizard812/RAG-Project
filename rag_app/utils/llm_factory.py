import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

# Map short names to actual Google API model strings
MODEL_REGISTRY = {
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-pro":   "gemini-2.5-pro",
}

def get_llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    """
    Returns a ChatGoogleGenerativeAI instance based on the LLM_MODEL_TYPE
    environment variable.

    Defaults to gemini-2.5-flash for speed and cost efficiency.
    Set LLM_MODEL_TYPE=gemini-2.5-pro in .env for complex reasoning tasks.

    Args:
        temperature: Sampling temperature (0.0 = deterministic, best for agents).

    Returns:
        A configured ChatGoogleGenerativeAI instance.
    """
    model_key = os.getenv("LLM_MODEL_TYPE", "gemini-2.5-flash").strip().lower()
    model_id  = MODEL_REGISTRY.get(model_key, MODEL_REGISTRY["gemini-2.5-flash"])

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Add it to your .env file."
        )

    print(f"[LLM Factory] Loaded model: {model_id}  (key='{model_key}')")

    return ChatGoogleGenerativeAI(
        model=model_id,
        google_api_key=api_key,
        temperature=temperature,
        convert_system_message_to_human=True,  # Required for Gemini
    )