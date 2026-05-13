import asyncio
import os
import pyaudio
import time
import re
import threading
import numpy as np
from llm import stream_gemini
import tts

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024

# ---------------------------------------------------------------------------
# AUDIO HARDWARE
# ---------------------------------------------------------------------------
p = pyaudio.PyAudio()
stream = p.open(
    format=FORMAT,
    channels=CHANNELS,
    rate=RATE,
    input=True,
    frames_per_buffer=CHUNK
)

def get_mic_amplitude(data):
    audio_data = np.frombuffer(data, dtype=np.int16)
    return np.abs(audio_data).mean()

# ---------------------------------------------------------------------------
# DEEPGRAM STT ENGINE
# ---------------------------------------------------------------------------
from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveTranscriptionEvents,
    LiveOptions,
)

DEEPGRAM_API_KEY = "c106445dc82777d33e4899f29f5bf21cad38f764"

async def run_agent():
    config = DeepgramClientOptions(options={"keepalive": "true"})
    dg_client = DeepgramClient(DEEPGRAM_API_KEY, config)
    dg_connection = dg_client.listen.asyncwebsocket.v("1")

    llm_task = None

    async def on_message(self, result, **kwargs):
        nonlocal llm_task
        transcript = result.channel.alternatives[0].transcript.strip()
        if not transcript: return

        # 1. SMART INTERRUPTION (Barge-in)
        # If the agent is talking and we hear actual transcribed words, STOP the agent.
        if tts.is_speaking():
            print(f"\n[USER BARGE-IN]: {transcript}")
            tts.stop_speaking()
            if llm_task: llm_task.cancel()
            # We don't trigger a new LLM task immediately to allow the user to finish their sentence.
            return

        print(f"\n[USER]: {transcript}")
        
        # 2. TRIGGER LLM
        if llm_task: 
            llm_task.cancel()
        llm_task = asyncio.create_task(stream_gemini_wrapper(transcript))

    async def stream_gemini_wrapper(text):
        try:
            # Clean Markdown before processing
            text = re.sub(r"[\*\#\_]", "", text)
            await stream_gemini(text)
        except asyncio.CancelledError:
            print("LLM Task Cancelled (Interrupted)")
        except Exception as e:
            print(f"LLM Error: {e}")

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)

    options = LiveOptions(
        model="nova-2",
        punctuate=True,
        language="en-US",
        encoding="linear16",
        channels=1,
        sample_rate=16000,
        no_delay=True,
        endpointing=300, # Ultra-fast turn detection
    )

    print("\n[ULTRA-FLUX AGENT ONLINE]")
    print("Speak now...")

    if await dg_connection.start(options) is False:
        print("Failed to connect to STT")
        return

    try:
        while True:
            data = await asyncio.to_thread(stream.read, CHUNK, exception_on_overflow=False)
            amplitude = get_mic_amplitude(data)
            
            # 3. SMART BARGE-IN & ECHO GATE
            if tts.is_speaking():
                # Echo Gate: Strictly ignore mic while agent is talking
                # We now handle interruptions in on_message based on transcribed words
                continue
            
            # Send audio to STT
            await dg_connection.send(data)
            await asyncio.sleep(0.01)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await dg_connection.finish()

if __name__ == "__main__":
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        print("\n[OFFLINE]")