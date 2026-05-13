import asyncio
import os
import pyaudio
import numpy as np
import time
import queue
import threading
from google import genai

                                                                             
               
                                                                             
API_KEY = "AIzaSyCPSUOAWzEQJ_eZec5zuKq3ZDacUPZFuY4"
MODEL = "gemini-3.1-flash-live-preview"

                 
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024 

                                                                             
              
                                                                             
mic_queue = asyncio.Queue()
speaker_queue = queue.Queue() 

                                                                             
            
                                                                             

async def main():
    client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1alpha'})
    p = pyaudio.PyAudio()
    
             
    mic_stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    speaker_stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK)

    def audio_player():
        while True:
            data = speaker_queue.get()
            if data is None: break
            speaker_stream.write(data)

    threading.Thread(target=audio_player, daemon=True).start()

    async def mic_reader():
        while True:
            try:
                data = await asyncio.to_thread(mic_stream.read, CHUNK, exception_on_overflow=False)
                await mic_queue.put(data)
            except: await asyncio.sleep(0.01)

    asyncio.create_task(mic_reader())

    config = {
        "system_instruction": "Fast voice assistant. Concise responses.",
        "response_modalities": ["AUDIO"],
        "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": "Aoede"}}}
    }

    while True:
        try:
            async with client.aio.live.connect(model=MODEL, config=config) as session:
                print("\n>>> AGENT ONLINE (Speak now)")

                last_speech_time = None
                is_receiving = False
                last_send_time = time.time()
                is_speaking_now = False
                silence_counter = 0

                async def send_audio():
                    nonlocal last_speech_time, last_send_time, is_receiving, is_speaking_now, silence_counter
                    while True:
                        data = await mic_queue.get()
                        if is_receiving: continue

                        audio_data = np.frombuffer(data, dtype=np.int16)
                        amplitude = np.abs(audio_data).mean()

                        if amplitude > 300:                   
                            if not is_speaking_now:
                                print("[USER]", end=" ", flush=True)
                                is_speaking_now = True
                                silence_counter = 0
                            if not last_speech_time:
                                last_speech_time = asyncio.get_event_loop().time()
                            
                            await session.send_realtime_input(audio={"mime_type": "audio/pcm", "data": data})
                            last_send_time = time.time()
                        else:                 
                            if is_speaking_now:
                                silence_counter += 1
                                if silence_counter > 10:                   
                                    is_speaking_now = False
                                    print("[FINISH]", end=" ", flush=True)
                                                      
                                    await session.send_realtime_input(text="")
                                    last_send_time = time.time()
                            
                                                                     
                                                                                   
                            pass

                async def receive_responses():
                    nonlocal is_receiving, last_speech_time
                    async for response in session.receive():
                        if response.data:
                            if not is_receiving:
                                if last_speech_time:
                                    print(f"\n[LATENCY]: {asyncio.get_event_loop().time() - last_speech_time:.3f}s")
                                is_receiving = True
                            speaker_queue.put(response.data)
                        
                        if response.server_content:
                            content = response.server_content
                            if content.turn_complete:
                                print("\n[Turn Complete]")
                                is_receiving = False
                                last_speech_time = None
                                while not mic_queue.empty(): mic_queue.get_nowait()
                            if content.interrupted:
                                is_receiving = False
                                while not speaker_queue.empty():
                                    try: speaker_queue.get_nowait()
                                    except: break
                        
                        if response.text:
                            print(f"[Gemini]: {response.text}", end="", flush=True)

                async def heartbeat():
                    nonlocal last_send_time
                    while True:
                        await asyncio.sleep(2)
                        if time.time() - last_send_time > 3:
                            try:
                                await session.send_realtime_input(text="")
                                last_send_time = time.time()
                            except: break

                await asyncio.gather(send_audio(), receive_responses(), heartbeat())

        except Exception as e:
            print(f"\n>>> Session Refreshing: {e}")
            await asyncio.sleep(1)
            while not mic_queue.empty(): mic_queue.get_nowait()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
