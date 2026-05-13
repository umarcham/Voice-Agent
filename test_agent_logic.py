import os
import asyncio
import google.generativeai as genai
import re
from dotenv import load_dotenv

load_dotenv()

def deep_clean_speech(text):
    """Remove all markdown, bullet points, and special characters for clean TTS."""
    if not text: return ""
    text = re.sub(r"[\*\#\_]", "", text)
    text = re.sub(r"^\s*[\-\+\•]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.M)
    text = text.replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    "gemini-2.5-flash-lite",
    system_instruction="You are a fast phone assistant. Be extremely concise. Keep your response to 1 or 2 short sentences maximum. No lists."
)

async def test_logic():
    text = "I need a room"
    print(f"\n[TESTING LOGIC FOR]: {text}")
    print("-" * 30)

    sentence_buffer = ""
    
    try:
        response = await model.generate_content_async(
            text,
            stream=True,
            generation_config={"max_output_tokens": 100, "temperature": 0.7},
        )

        async for chunk in response:
            if chunk.text:
                sentence_buffer += chunk.text
                
                # Smart sentence splitting (matches phone_agent.py)
                sentences = re.findall(r'[^.!?]+[.!?](?=\s|$)', sentence_buffer)
                for sentence in sentences:
                    if re.search(r'\b(e\.g\.|i\.e\.|etc\.)\s*$', sentence, re.I):
                        continue
                    
                    cleaned = deep_clean_speech(sentence)
                    if cleaned:
                        print(f">>> WOULD SPEAK: {cleaned}")
                    sentence_buffer = sentence_buffer.replace(sentence, "", 1)
        
        if sentence_buffer.strip():
            cleaned_final = deep_clean_speech(sentence_buffer)
            if cleaned_final:
                print(f">>> WOULD SPEAK (Final): {cleaned_final}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_logic())
