import asyncio
import os
import pyaudio
import numpy as np
import time
import queue
import threading
from google import genai

                                                                             
               
                                                                             
API_KEY = "GEMINI_API_KEY"
MODEL = "gemini-3.1-flash-live-preview"                                      

                 
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 512 

                                                                             
                               
                                                                             
mic_queue = queue.Queue(maxsize=10)
speaker_queue = queue.Queue() 

class AudioEngine:
    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.mic_stream = self.p.open(
            format=FORMAT, channels=CHANNELS, rate=RATE,
            input=True, frames_per_buffer=CHUNK
        )
        self.speaker_stream = self.p.open(
            format=FORMAT, channels=CHANNELS, rate=RATE,
            output=True, frames_per_buffer=CHUNK
        )

    def speaker_worker(self):
        while True:
            data = speaker_queue.get()
            if data is None: break
            self.speaker_stream.write(data)

    def mic_worker(self):
        while True:
            try:
                data = self.mic_stream.read(CHUNK, exception_on_overflow=False)
                if mic_queue.full():
                    try: mic_queue.get_nowait()
                    except: pass
                mic_queue.put(data)
            except:
                time.sleep(0.01)

                                                                             
            
                                                                             

async def main():
    print(f"\n[CONNECTING TO {MODEL}...]")
                                                                    
    client = genai.Client(api_key=API_KEY)
    engine = AudioEngine()
    
    threading.Thread(target=engine.speaker_worker, daemon=True).start()
    threading.Thread(target=engine.mic_worker, daemon=True).start()

    config = {
        "system_instruction": "You are a fast voice assistant. Be extremely concise. 1 sentence max.",
        "response_modalities": ["AUDIO"],
    }

    while True:
        try:
                                                                     
            async with client.aio.live.connect(model=MODEL, config=config) as session:
                print("\n>>> AGENT ONLINE")
                print(">>> Speak now. Response will be sub-second.")

                last_speech_time = None
                is_receiving = False
                last_send_time = time.time()

                async def send_loop():
                    nonlocal last_speech_time, is_receiving, last_send_time
                    while True:
                        data = await asyncio.to_thread(mic_queue.get)
                        
                        audio_data = np.frombuffer(data, dtype=np.int16)
                        amplitude = np.abs(audio_data).mean()

                        if is_receiving:
                            if amplitude < 4000: continue
                            else:
                                          
                                while not speaker_queue.empty():
                                    try: speaker_queue.get_nowait()
                                    except: break
                        
                        if amplitude > 300:
                            if not is_receiving and not last_speech_time:
                                last_speech_time = asyncio.get_event_loop().time()
                            
                            await session.send_realtime_input(audio={"mime_type": "audio/pcm", "data": data})
                            last_send_time = time.time()
                            print(".", end="", flush=True) 
                        else:
                            if time.time() - last_send_time > 1.5:
                                await session.send_realtime_input(text="")
                                last_send_time = time.time()

                async def receive_loop():
                    nonlocal is_receiving, last_speech_time
                    async for response in session.receive():
                        if response.data:
                            if not is_receiving:
                                if last_speech_time:
                                    latency = asyncio.get_event_loop().time() - last_speech_time
                                    print(f"\n[LATENCY]: {latency:.3f}s")
                                is_receiving = True
                            speaker_queue.put(response.data)
                        
                        if response.server_content:
                            content = response.server_content
                            if content.turn_complete:
                                print("\n[Turn Complete]")
                                is_receiving = False
                                last_speech_time = None
                            if content.interrupted:
                                is_receiving = False
                                while not speaker_queue.empty():
                                    try: speaker_queue.get_nowait()
                                    except: break

                await asyncio.gather(send_loop(), receive_loop())

        except Exception as e:
            print(f"\n>>> Reconnecting... ({e})")
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[OFFLINE]")
