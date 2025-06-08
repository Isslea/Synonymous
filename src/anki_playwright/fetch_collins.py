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

def fetch_pron_camb(word: str):
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"https://dictionary.cambridge.org/dictionary/english/{word}")
            page.wait_for_selector(f"body .dpron-i", timeout=1000)
        except Exception:
            return None, None
        regions = page.query_selector_all(f"body .dpron-i")
        ipa = None
        sound_url = None

        if len(regions) > 0:
            for region in regions:
                lead = region.query_selector(f"span.region.dreg")
                # Find IPA
                pron = region.query_selector("span.pron.dpron")
                if pron:
                    ipa = pron.inner_text().strip().replace("/", "").strip()

                # Find sound source
                sound = region.query_selector('audio source[type="audio/mpeg"]')
                if sound:
                    sound_url = "https://dictionary.cambridge.org" + sound.get_attribute("src")

                # Find American pronunciation else leave the British one
                if lead and "US" in lead.inner_text():
                    break

        browser.close()
        return ipa, sound_url

if __name__ == "__main__":
    word = sys.argv[1]

    #Fetch from collins pronunciation tab
    ipa, sound = fetch_pron_in_pron_tab(word)

    # If not found, try fetching from collins definition tab
    if not ipa or not sound:
        temp_ipa, temp_sound = fetch_pron_in_def_tab(word)
        if temp_ipa:
            ipa = temp_ipa
        if temp_sound:
            sound = temp_sound
        # If still not found, try fetching from Cambridge
        if not temp_ipa or not temp_sound:
            temp_ipa, temp_sound = fetch_pron_camb(word)
            if temp_ipa:
                ipa = temp_ipa
            if temp_sound:
                sound = temp_sound

    print(json.dumps({
        "ipa": ipa,
        "audio_url": sound
    }))
