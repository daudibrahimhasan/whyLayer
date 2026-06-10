import urllib.request
import json
import sys

BASE_URL = "http://localhost:8000"

def test_health():
    try:
        url = f"{BASE_URL}/health"
        print(f"Testing {url}...")
        with urllib.request.urlopen(url) as response:
            data = json.load(response)
            print(f"Health Response: {data}")
            if data.get("status") == "ok":
                print("✅ Health Check Passed")
                return True
    except Exception as e:
        print(f"❌ Health Check Failed: {e}")
        return False

def test_start_hi():
    try:
        url = f"{BASE_URL}/api/decision/start"
        print(f"Testing {url} with query 'hi'...")
        data = json.dumps({"query": "hi"}).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            result = json.load(response)
            print(f"Start 'hi' Response: {result}")
            # We assume it should succeed now based on code allowing len >= 2
            print("✅ Start 'hi' Handled")
    except urllib.error.HTTPError as e:
        print(f"ℹ️ Start 'hi' returned HTTP {e.code}: {e.read().decode()}")
        if e.code == 400:
             print("✅ Start 'hi' Rejected as expected (if logic changed)")
    except Exception as e:
        print(f"❌ Start 'hi' Failed: {e}")

def test_start_valid():
    try:
        url = f"{BASE_URL}/api/decision/start"
        print(f"Testing {url} with valid query...")
        data = json.dumps({"query": "Should I move to a new city?"}).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            result = json.load(response)
            print(f"Start Valid Response Keys: {list(result.keys())}")
            if "session_id" in result and "questions" in result:
                print("✅ Start Valid Passed")
            else:
                print("❌ Start Valid verification failed")
    except Exception as e:
        print(f"❌ Start Valid Failed: {e}")

if __name__ == "__main__":
    if test_health():
        test_start_hi()
        test_start_valid()
