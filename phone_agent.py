import os
import json
import base64
import asyncio
import re
import audioop
import httpx
import google.generativeai as genai
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from dotenv import load_dotenv
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

def deep_clean_speech(text):
    """Remove all markdown, code blocks, and special characters for clean TTS."""
    if not text: return ""
    # Remove code blocks and backticks
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`", "", text)
    # Remove bold/italic stars and hashtags
    text = re.sub(r"[\*\#\_]", "", text)
    # Remove bullet points and numbered lists
    text = re.sub(r"^\s*[\-\+\•]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.M)
    # Final cleanup
    text = text.replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text)
from dotenv import load_dotenv
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)
import httpx
import google.generativeai as genai

load_dotenv()

# Configuration
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NGROK_URL = os.getenv("NGROK_URL")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    "gemini-2.5-flash-lite",
    system_instruction="You are a fast phone assistant. Be extremely concise. Keep your response to 1 or 2 short sentences maximum. No lists. Use natural spoken language."
)

app = FastAPI()

# Force IPv4 to fix macOS DNS stalls
class IPv4Transport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        if not hasattr(self, "_pool"):
            from httpcore import AsyncConnectionPool
            self._pool = AsyncConnectionPool(local_address="0.0.0.0", http2=True)
        return await super().handle_async_request(request)

# Global HTTP clients for Gemini and TTS
try:
    transport = IPv4Transport(http2=False)
    http_client = httpx.AsyncClient(transport=transport, timeout=10.0)
    tts_client = httpx.AsyncClient(timeout=5.0) # Global client for TTS speed
except Exception:
    http_client = httpx.AsyncClient(http2=False, timeout=10.0)
    tts_client = httpx.AsyncClient(timeout=5.0)

# ---------------------------------------------------------------------------
# TWILIO WEBHOOKS
# ---------------------------------------------------------------------------

@app.post("/voice")
async def voice(request: Request):
    """Handle incoming calls and connect to Media Stream."""
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f"wss://{NGROK_URL}/media-stream")
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")

# ---------------------------------------------------------------------------
# MEDIA STREAM HANDLER
# ---------------------------------------------------------------------------

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Bridge Twilio Audio <-> Deepgram <-> Gemini."""
    await websocket.accept()
    print("\n>>> PHONE CALL CONNECTED")

    # Initialize Deepgram
    dg_client = DeepgramClient(DEEPGRAM_API_KEY)
    dg_connection = dg_client.listen.asyncwebsocket.v("1")

    # Call-Specific Conversation History
    history = []

    stream_sid = None
    llm_task = None
    is_agent_speaking = False

    async def on_message(self, result, **kwargs):
        nonlocal llm_task, is_agent_speaking
        transcript = result.channel.alternatives[0].transcript.strip()
        if not transcript: return

        # 1. BARGE-IN: If user speaks while agent is talking, stop playback
        if is_agent_speaking:
            print(f"\n[BARGE-IN]: {transcript}")
            is_agent_speaking = False
            if llm_task: llm_task.cancel()
            # Send 'clear' to Twilio if needed, but stopping the send loop is usually enough
            return

        print(f"[USER]: {transcript}")
        
        # 2. TRIGGER LLM
        if llm_task: llm_task.cancel()
        llm_task = asyncio.create_task(process_llm_and_tts(transcript))

    async def process_llm_and_tts(text):
        nonlocal is_agent_speaking, stream_sid
        try:
            print(f">>> TRIGGERING GEMINI FOR: {text}")
            
            # Use chat with history (Keep last 10 turns)
            chat = model.start_chat(history=history[-10:])
            
            full_response = ""
            sentence_buffer = ""
            
            response = await chat.send_message_async(
                text,
                stream=True,
                generation_config={"max_output_tokens": 100, "temperature": 0.7}
            )

            async for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    sentence_buffer += chunk.text
                    
                    # 1. SMART SENTENCE SPLITTING
                    sentences = re.findall(r'[^.!?]+[.!?](?=\s|$)', sentence_buffer)
                    for sentence in sentences:
                        if re.search(r'\b(e\.g\.|i\.e\.|etc\.)\s*$', sentence, re.I):
                            continue
                            
                        cleaned = deep_clean_speech(sentence)
                        if cleaned:
                            print(f"DEBUG: Speaking: {cleaned}")
                            asyncio.create_task(speak_to_phone(cleaned))
                        sentence_buffer = sentence_buffer.replace(sentence, "", 1)
            
            if sentence_buffer.strip():
                full_response += sentence_buffer
                cleaned_final = deep_clean_speech(sentence_buffer)
                if cleaned_final:
                    asyncio.create_task(speak_to_phone(cleaned_final))
            
            # Update history
            history.append({"role": "user", "parts": [text]})
            history.append({"role": "model", "parts": [full_response]})
                
        except Exception as e:
            print(f"LLM Error: {e}")
        except asyncio.CancelledError:
            print("LLM Interrupted")

    async def speak_to_phone(text):
        nonlocal is_agent_speaking, stream_sid
        if not text or not stream_sid: return
        is_agent_speaking = True
        
        text = deep_clean_speech(text)
        print(f"[AGENT]: {text}")

        tts_url = "https://api.deepgram.com/v1/speak?model=aura-asteria-en&encoding=linear16&sample_rate=8000"
        headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}", "Content-Type": "application/json"}
        
        try:
            import time
            start_tts = time.time()
            response = await tts_client.post(tts_url, headers=headers, json={"text": text})
            
            if response.status_code == 200:
                print(f"DEBUG: TTS Latency: {time.time() - start_tts:.3f}s")
                audio_payload = response.content
                mulaw_audio = audioop.lin2ulaw(audio_payload, 2)
                base64_audio = base64.b64encode(mulaw_audio).decode("utf-8")
                
                message = {
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": base64_audio}
                }
                await websocket.send_text(json.dumps(message))
        except Exception as e:
            print(f"TTS Error: {e}")
        finally:
            is_agent_speaking = False

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

    dg_options = LiveOptions(
        model="nova-2", language="en-US", encoding="linear16",
        channels=1, sample_rate=16000, endpointing=300
    )

    if await dg_connection.start(dg_options) is False:
        print("STT Failed")
        return

    try:
        while True:
            data = await websocket.receive_text()
            packet = json.loads(data)

            if packet['event'] == 'start':
                stream_sid = packet['start']['streamSid']
                print(f"Stream Started: {stream_sid}")

            elif packet['event'] == 'media':
                # Decode Twilio's 8kHz Mulaw to 16kHz PCM for Deepgram
                mulaw_data = base64.b64decode(packet['media']['payload'])
                pcm_data = audioop.ulaw2lin(mulaw_data, 2)
                # Resample 8kHz to 16kHz
                pcm_16k, _ = audioop.ratecv(pcm_data, 2, 1, 8000, 16000, None)
                
                await dg_connection.send(pcm_16k)

            elif packet['event'] == 'stop':
                print("Call Ended")
                break

    except Exception as e:
        print(f"WebSocket Error: {e}")
    finally:
        await dg_connection.finish()
        print(">>> AGENT OFFLINE")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
