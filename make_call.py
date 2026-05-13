import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

# Credentials
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
ngrok_url = os.getenv("NGROK_URL")

# Target
MY_PHONE_NUMBER = "+917984608871"

client = Client(account_sid, auth_token)

def make_outbound_call():
    # 1. Get your Twilio number automatically
    incoming_phone_numbers = client.incoming_phone_numbers.list(limit=1)
    if not incoming_phone_numbers:
        print("No Twilio numbers found.")
        return
    
    twilio_number = incoming_phone_numbers[0].phone_number
    webhook_url = f"https://{ngrok_url}/voice"

    print(f"Initiating call from {twilio_number} to {MY_PHONE_NUMBER}...")

    # 2. Trigger the call
    call = client.calls.create(
        to=MY_PHONE_NUMBER,
        from_=twilio_number,
        url=webhook_url
    )

    print(f"Call Sid: {call.sid}")
    print("Your phone should be ringing now!")

if __name__ == "__main__":
    make_outbound_call()
