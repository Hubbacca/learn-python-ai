from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.environ.get('API_KEY')
debug = os.environ.get('DEBUG')

print(f"API Key: {api_key}")
print(f"Debug mode: {debug}")