# Ultra-Flux Telephony Voice Agent

A production-ready, ultra-low latency conversational AI voice agent built for telephony. This project bridges a Twilio phone number to a real-time AI pipeline featuring Google Gemini 2.5 Flash-Lite and Deepgram Nova-2/Aura.

By utilizing sentence-based streaming, persistent HTTP connections, and on-the-fly signal resampling, this agent achieves **sub-1.5 second round-trip latency** over a standard phone call.

## Features
*   **Twilio Media Streams Integration**: Native WebSocket bridging for 8kHz µ-law audio.
*   **Sub-Second Latency**: Optimized TTFT (Time-To-First-Token) using Gemini Flash-Lite and Deepgram Aura.
*   **Smart Barge-In**: Users can interrupt the agent naturally while it's speaking.
*   **Conversation Memory**: Session-based history (last 10 turns) allows the agent to maintain context over the phone.
*   **Deep Speech Cleaning**: Automatically removes markdown, code blocks, and lists to ensure the TTS sounds natural and human-like.
*   **Asynchronous Concurrency**: Built on FastAPI and `asyncio` for non-blocking stream processing.

## Prerequisites
*   Python 3.11+
*   A Twilio Account with an active Phone Number
*   [Ngrok](https://ngrok.com/) (or another tunneling service)
*   [Deepgram API Key](https://deepgram.com/)
*   [Google Gemini API Key](https://aistudio.google.com/app/apikey)

## Setup Instructions

1.  **Clone the repository**
2.  **Create and activate a virtual environment**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
3.  **Install dependencies**:
    ```bash
    pip install fastapi uvicorn twilio python-dotenv deepgram-sdk google-generativeai httpx audioop-lts
    ```
    *(Note: `audioop-lts` is recommended if you are running Python 3.13+ where native `audioop` is deprecated)*
4.  **Configure Environment Variables**:
    Create a `.env` file in the root directory:
    ```env
    TWILIO_ACCOUNT_SID=your_twilio_sid
    TWILIO_AUTH_TOKEN=your_twilio_token
    DEEPGRAM_API_KEY=your_deepgram_key
    GEMINI_API_KEY=your_gemini_key
    NGROK_URL=your_ngrok_url.ngrok-free.dev
    ```

## Running the Application

1.  **Start your Ngrok tunnel**:
    ```bash
    ngrok http 8000
    ```
    *(Update your `.env` file with the new URL if it changes)*

2.  **Start the Telephony Agent Server**:
    ```bash
    ./venv/bin/python3 phone_agent.py
    ```

3.  **Configure your Twilio Webhook**:
    Run the provided setup script to automatically link your Twilio number to your running server:
    ```bash
    ./venv/bin/python3 setup_twilio.py
    ```

4.  **Make a Call!**
    Dial your Twilio phone number to interact with the agent. Alternatively, you can trigger an outbound call to your personal phone using:
    ```bash
    ./venv/bin/python3 make_call.py
    ```

## Local Testing Without a Phone Call

If you want to test the LLM logic, sentence splitting, and speech cleaning *without* using Twilio credits, you can use the local logic test script:

```bash
./venv/bin/python3 test_agent_logic.py
```

## Architecture

For a deep dive into the system design, signal processing, and a full latency breakdown, please see the [architecture.md](architecture.md) file.
