# tts.py

import queue
import threading
import numpy as np
import sounddevice as sd
import httpx
import time

# -----------------------------------
# API KEY
# -----------------------------------

DEEPGRAM_API_KEY = "a11b0ae9052d95410985f45af7a6b184addf83d1"

# -----------------------------------
# QUEUES & FLAGS
# -----------------------------------

tts_queue = queue.Queue()
audio_queue = queue.Queue()
is_playing_flag = False
recent_speech_buffer = []

stop_event = threading.Event()
worker_stop_event = threading.Event()

# -----------------------------------
# AUDIO PLAYER THREAD
# -----------------------------------

def audio_player():
    """
    Background thread that plays audio from the queue.
    """
    global is_playing_flag
    try:
        output_stream = sd.OutputStream(
            samplerate=16000,
            channels=1,
            dtype="int16"
        )
        output_stream.start()

        while True:
            try:
                # Use a small timeout to keep is_playing_flag stable between chunks
                audio_chunk = audio_queue.get(timeout=0.2)
                if audio_chunk is None: 
                    break
                
                is_playing_flag = True
                
                # Write audio chunk to stream
                output_stream.write(audio_chunk)
                
                # Check if we were told to stop
                if stop_event.is_set():
                    is_playing_flag = False
                    # Clearing handled by stop_speaking()
                    pass

            except queue.Empty:
                is_playing_flag = False
                if stop_event.is_set():
                    stop_event.clear()
                    
    except Exception as e:
        print(f"Audio Player Error: {e}")
    finally:
        try:
            output_stream.stop()
            output_stream.close()
        except:
            pass

player_thread = threading.Thread(target=audio_player, daemon=True)
player_thread.start()

# -----------------------------------
# PRODUCER
# -----------------------------------

def speak_text(text):
    """Put text into the sync queue for the TTS worker"""
    global recent_speech_buffer
    # Normalize and store for echo cancellation
    import re
    clean_text = re.sub(r"[^\w\s]", "", text).lower().strip()
    if clean_text:
        recent_speech_buffer.append(clean_text)
        if len(recent_speech_buffer) > 5: # Keep last 5 chunks
            recent_speech_buffer.pop(0)
    
    tts_queue.put(text)

# -----------------------------------
# TTS WORKER
# -----------------------------------

def tts_worker():
    """
    Worker that manages Deepgram TTS via REST API in a separate thread.
    """
    url = "https://api.deepgram.com/v1/speak?model=aura-2-thalia-en&encoding=linear16&sample_rate=16000"
    headers = {
        "Authorization": f"Token {DEEPGRAM_API_KEY}",
        "Content-Type": "application/json"
    }

    while True:
        try:
            # Wait for text to speak
            text = tts_queue.get()
            if text is None: 
                break

            if worker_stop_event.is_set():
                worker_stop_event.clear()
                continue
            
            payload = {"text": text}
            
            with httpx.stream("POST", url, headers=headers, json=payload, timeout=10) as response:
                if response.status_code != 200:
                    print(f"TTS API Error: {response.status_code}")
                    continue
                
                for chunk in response.iter_bytes():
                    if worker_stop_event.is_set():
                        break 
                    if chunk:
                        audio_array = np.frombuffer(chunk, dtype=np.int16)
                        audio_queue.put(audio_array)

        except Exception as e:
            print(f"TTS Worker Exception: {e}")
            time.sleep(1)

# -----------------------------------
# HELPER FUNCTIONS
# -----------------------------------

def is_speaking():
    """Checks if the agent is currently speaking or has audio queued."""
    return not tts_queue.empty() or not audio_queue.empty() or is_playing_flag

def stop_speaking():
    """
    Stops all current and queued speech.
    """
    global recent_speech_buffer
    recent_speech_buffer = [] # Clear buffer on stop to allow immediate new speech
    worker_stop_event.set()
    stop_event.set()
    
    # Clear tts queue
    while not tts_queue.empty():
        try:
            tts_queue.get_nowait()
        except queue.Empty:
            break
            
    # Clear audio queue
    while not audio_queue.empty():
        try:
            audio_queue.get_nowait()
        except queue.Empty:
            break

def get_recent_speech():
    """Returns a single string of all recently spoken text chunks."""
    return " ".join(recent_speech_buffer)

# Start the TTS worker thread
tts_thread = threading.Thread(target=tts_worker, daemon=True)
tts_thread.start()