import os
import certifi
import subprocess
import json

def fetch_pronunciation(word: str):
    script_path = os.path.expanduser("/Users/klaudiarapacz/Documents/Python/Synonymous/src/anki_playwright/fetch_collins.py")
    result = subprocess.run([
        "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
        script_path,
        word
    ], capture_output=True, text=True)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Error decoding JSON for word '{word}': {result.stdout}")
        return None, None
    return data["ipa"], data["audio_url"]