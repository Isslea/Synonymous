import os
import certifi
import subprocess
import json

def fetch_pronunciation(word: str, is_english: bool):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    collins_path = os.path.join(current_dir, 'anki_playwright', 'fetch_collins.py')

    script_path = os.path.expanduser(collins_path)
    result = subprocess.run([
        "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
        script_path,
        word,
        "1" if is_english else "0",
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Playwright script failed for '{word}' (exit {result.returncode})")
        if result.stderr:
            print(result.stderr.strip())
        return None, None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Error decoding JSON for word '{word}': {result.stdout}")
        if result.stderr:
            print(result.stderr.strip())
        return None, None
    return data["ipa"], data["audio_url"]
