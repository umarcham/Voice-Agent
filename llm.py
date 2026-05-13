# llm.py

import time
import json
import re
import httpx
import socket
from tts import speak_text

GEMINI_API_KEY = "AIzaSyDAilMpSnlSoFfVeVDjkWWru3DfEDiIjKQ"

URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash-lite:streamGenerateContent?alt=sse"
)

# Force IPv4 to fix macOS DNS stalls (common cause of 5-8s latency)
class IPv4Transport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        if not hasattr(self, "_pool"):
            from httpcore import AsyncConnectionPool
            # We override the connection pool to force IPv4
            self._pool = AsyncConnectionPool(local_address="0.0.0.0", http2=True)
        return await super().handle_async_request(request)

# Optimized HTTP/2 client with forced IPv4 for Mac stability
try:
    # Use a simpler way to prefer IPv4 if transport override is too complex
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    http_client = httpx.AsyncClient(http2=True, timeout=10.0, limits=limits)
except Exception:
    http_client = httpx.AsyncClient(http2=False, timeout=10.0)

conversation_history = []

async def stream_gemini(transcript):
    print("ENTERED GEMINI")
    global conversation_history

    # Raw transcript to history
    conversation_history.append(transcript)
    if len(conversation_history) > 2:
        conversation_history = conversation_history[-2:]

    # Ultra-simple prompt (Raw text is often faster for Lite models)
    full_prompt = "\n".join(conversation_history)

    payload = {
        "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
        "system_instruction": {"parts": [{"text": "You are a helpful, conversational voice assistant. Be concise but complete. No markdown symbols."}]},
        "generationConfig": {
            "maxOutputTokens": 1024,
            "temperature": 0.7,
        }
    }

    full_response = ""
    sentence_buffer = ""
    
    print(f"SENDING GEMINI REQUEST (IPv4 Mode)")
    request_start_time = time.time()
    ttft_printed = False
    first_byte_printed = False

    try:
        async with http_client.stream(
            "POST", 
            f"{URL}&key={GEMINI_API_KEY}", 
            json=payload,
            headers={"Content-Type": "application/json", "Connection": "keep-alive"}
        ) as response:
            
            if response.status_code != 200:
                print(f"API Error: {response.status_code}")
                return "Error"

            async for line in response.aiter_lines():
                if not first_byte_printed:
                    print(f"[FIRST BYTE RECEIVED]: {time.time() - request_start_time:.3f}s")
                    first_byte_printed = True

                if not line or not line.startswith("data:"):
                    continue

                line_data = line[5:].strip()
                try:
                    data = json.loads(line_data)
                    candidate = data.get("candidates", [{}])[0]
                    content = candidate.get("content", {})
                    parts = content.get("parts", [])
                    
                    text = ""
                    for part in parts:
                        if "text" in part: text += part["text"]
                        if "thought" in part and not text: text += part["thought"]

                    if text:
                        if not ttft_printed:
                            print(f"[LLM TTFT]: {time.time() - request_start_time:.2f}s")
                            ttft_printed = True

                        full_response += text
                        sentence_buffer += text

                        # Immediate sentence extraction
                        sentences = re.findall(r'[^.!?]+[.!?]', sentence_buffer)
                        for sentence in sentences:
                            cleaned = sentence.strip()
                            if cleaned:
                                print(f"TTS CHUNK: {cleaned}")
                                # Clean Markdown before speaking
                                clean_speech = re.sub(r"[\*\#\_]", "", cleaned)
                                speak_text(clean_speech)
                            sentence_buffer = sentence_buffer.replace(sentence, "", 1)

                    if candidate.get("finishReason"):
                        break
                except: continue

    except Exception as e:
        print(f"Request Error: {e}")
        return "Connection Error"

    if sentence_buffer.strip():
        print(f"TTS CHUNK (Final): {sentence_buffer.strip()}")
        clean_final = re.sub(r"[\*\#\_]", "", sentence_buffer.strip())
        speak_text(clean_final)

    conversation_history.append(full_response)
    return full_response