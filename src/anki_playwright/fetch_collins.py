import sys
import json
from playwright.sync_api import sync_playwright

def fetch_pron(word: str, url:str, container:str, title:str):
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"https://www.collinsdictionary.com/dictionary/{url}/{word}")
            page.wait_for_selector(f"body {container}", timeout=1000)
        except Exception:
            return None, None
        regions = page.query_selector_all(f"body {container}")
        ipa = None
        sound_url = None

        if len(regions) > 0:
            for region in regions:
                lead = region.query_selector(f"span{title}")

                # Find IPA
                pron = region.query_selector("span.pron")
                if pron:
                    ipa = pron.inner_text().strip()

                # Find sound source
                sound = region.query_selector('a[class*="sound"]')
                if sound:
                    sound_url = sound.get_attribute("data-src-mp3")

                # Find American pronunciation else leave the British one
                if lead and "American" in lead.inner_text():
                    break

        browser.close()
        return ipa, sound_url

def fetch_pron_in_pron_tab(word: str):
    return fetch_pron(word, "english-pronunciations", "span.region", ".lead")

def fetch_pron_in_def_tab(word: str):
    return fetch_pron(word, "english", ".dictlink", ".dictname")

if __name__ == "__main__":
    word = sys.argv[1]

    ipa, sound = fetch_pron_in_pron_tab(word)
    if not ipa and not sound:
        ipa, sound = fetch_pron_in_def_tab(word)

    print(json.dumps({
        "ipa": ipa,
        "audio_url": sound
    }))
