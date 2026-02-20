import json
import os
import time

import requests
from aqt import mw

#Card types
DOUBLE = "1. Podwójny (wpisywanie odpowiedzi)"
TYPE_ENGLISH = "2. Pojedynczy (wpisywanie angielski)"
READ_POLISH = "3. Podstawowy (odczytywanie polski)"

#Create notes
def create_note(card_type: str):
    card_polish_read = mw.col.models.by_name(card_type)
    return mw.col.new_note(card_polish_read)

def create_note_from_existing(card_type: str, note):
    card_polish_read = mw.col.models.by_name(card_type)
    new_note = mw.col.new_note(card_polish_read)

    for field in note.keys():
        new_note[field] = note[field]

    return new_note

#Check card type
def has_card_type(note, card_type: str):
    note_type = note.model()['name']
    return note_type == card_type

#Move queue
def move_queue_to_top(note_id):
    db = mw.col.db
    top_due = db.first("SELECT MIN(due) FROM cards WHERE queue IN (0)")[0]
    card_ids = []

    note = mw.col.get_note(note_id)
    card_ids.extend(note.card_ids())

    for card_id in card_ids:
        card = mw.col.get_card(card_id)
        if card:
            top_due = top_due - 1
            card.due = top_due
            mw.col.update_card(card)

def add_note_and_move_queue_up(note, deck_id):
    mw.col.add_note(note, deck_id)
    move_queue_to_top(note.id)

#Delete notes
def delete_notes(selected_notes):
    card_ids = []

    for note_id in selected_notes:
        note = mw.col.get_note(note_id)
        card_ids.extend(note.card_ids())

    mw.col.remove_cards_and_orphaned_notes(card_ids)

#Json helpers
def read_json_file(filename: str):
    profile_folder = mw.pm.profileFolder()
    json_path = os.path.join(profile_folder, f"{filename}.json")

    # Create if does not exists
    if not os.path.exists(json_path):
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=4)

    # Read if is not empty
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            pron_dict = json.load(f)
    except json.JSONDecodeError:
        pron_dict = {}
    return json_path, pron_dict

def write_json_file(filepath: str, data: dict):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def call_gemini_api_async(text: str) -> str | None:
    api_key = "AIzaSyDpQ5fpf1S6G9hJ8wy7CPJrqPyOb8sOPfc"
    url = (
        f"https://generativelanguage.googleapis.com/"
        f"v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    )

    request_body = {
        "contents": [
            {
                "parts": [
                    {"text": text}
                ]
            }
        ]
    }

    try:
        headers = {
            "User-Agent": "PostmanRuntime/7.36.3",
            "Accept": "*/*",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
        }

        response = requests.post(url, json=request_body, headers=headers, timeout=30)
        response_text = response.text

        try:
            gemini_response = json.loads(response_text)
        except json.JSONDecodeError:
            print("Invalid JSON response")
            return None

        if response.status_code < 200 or response.status_code >= 300:
            error_msg = (
                gemini_response.get("error", {}).get("message")
            )
            print(f"{response.reason}: {error_msg}")
            return None

        text_from_gemini = (
            gemini_response.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text")
        )

        if text_from_gemini is None:
            time.sleep(5)
        else:
            time.sleep(3)

        return text_from_gemini

    except Exception as ex:
        print(f"Error calling Gemini API: {ex}")
        return None
