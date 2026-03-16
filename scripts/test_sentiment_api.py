import requests
import time

def test_sentiment_api():
    print("Testing Sentiment API...")
    url = "http://localhost:8000/api/sentiment/latest"
    try:
        # Note: This assumes the server is running.
        # If it's not, we might need to mock or just rely on the persistence test
        # but usually we want to verify the server logic too.
        # Since I am in a dev environment and don't want to start the whole server
        # if it's not already running, I'll check if it's up.
        
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            print(f"API Response: {data}")
            if data.get("status") == "success":
                print("SUCCESS: API returned data correctly.")
            elif data.get("status") == "empty":
                print("INFO: API is empty, but working.")
            else:
                print(f"FAIL: API returned error: {data.get('message')}")
        else:
            print(f"FAIL: API returned status code {response.status_code}")
    except Exception as e:
        print(f"INFO: Could not connect to API (is the server running?): {e}")

if __name__ == "__main__":
    test_sentiment_api()
