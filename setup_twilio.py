import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

# Twilio Credentials
account_sid = os.getenv("TWILIO_ACCOUNT_SID")
auth_token = os.getenv("TWILIO_AUTH_TOKEN")
ngrok_url = os.getenv("NGROK_URL")

client = Client(account_sid, auth_token)

def setup_number():
    # Get all phone numbers in the account
    incoming_phone_numbers = client.incoming_phone_numbers.list(limit=5)

    if not incoming_phone_numbers:
        print("No Twilio numbers found. Please buy a number in the Twilio console first.")
        return

    # Use the first available number
    number = incoming_phone_numbers[0]
    webhook_url = f"https://{ngrok_url}/voice"

    print(f"Configuring {number.phone_number}...")
    
    number.update(
        voice_url=webhook_url,
        voice_method="POST"
    )

    print(f"\nSUCCESS! Call {number.phone_number} to talk to your agent.")
   

if __name__ == "__main__":
    setup_number()
