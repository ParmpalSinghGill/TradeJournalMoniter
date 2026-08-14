import os
import requests
import json
import time
import hmac
import hashlib

def load_env(filepath=".env"):
    config = {}
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
    return config

def main():
    config = load_env()
    api_key = config.get("COINDCX_API")
    api_secret = config.get("COINDCX_SECRATE")
    
    if not api_key or not api_secret:
        print("CoinDCX API Key or Secret missing in .env")
    url = "https://api.coindcx.com/exchange/v1/derivatives/futures/data/instrument"
    
    # Try as GET request
    query = "?pair=B-XAU_USDT&margin_currency_short_name=INR"
    full_url = url + query
    res = requests.get(full_url)
    print(f"Instrument Status Code: {res.status_code}")
    print("Instrument Response:")
    print(json.dumps(res.json(), indent=2))
    
    pass

if __name__ == "__main__":
    main()
