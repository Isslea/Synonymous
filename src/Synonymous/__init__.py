from aqt import gui_hooks
from aqt.qt import QAction, QMenu
from aqt.utils import showInfo
from aqt.browser import Browser
import logging
logging.basicConfig(level=logging.DEBUG, filename='anki_debug.log', filemode='w')


DOUBLE = "1. Podwójny (wpisywanie odpowiedzi)"
TYPE_ENGLISH = "2. Pojedynczy (wpisywanie angielski)"
READ_POLISH = "3. Podstawowy (odczytywanie polski)"


def move_queue_to_top(note_id, browser: Browser):
    db = browser.mw.col.db
    top_due = db.first("SELECT MIN(due) FROM cards WHERE queue IN (0)")[0]
    card_ids = []

    note = browser.mw.col.get_note(note_id)
    card_ids.extend(note.card_ids())

    for card_id in card_ids:
        card = browser.mw.col.get_card(card_id)
        if card:
            top_due = top_due - 1
            card.due = top_due
            browser.mw.col.update_card(card)

def delete_notes(selected_notes, browser: Browser):
    card_ids = []
    for note_id in selected_notes:
        note = browser.mw.col.get_note(note_id)
        card_ids.extend(note.card_ids())

    browser.mw.col.remove_cards_and_orphaned_notes(card_ids)
def add_polish_notes(selected_notes, deck_id, browser: Browser):
    polish_model = browser.mw.col.models.by_name(READ_POLISH)

    for note in selected_notes:

        original_note = browser.mw.col.get_note(note)
        note_type = original_note.model()['name']
        if note_type == TYPE_ENGLISH:
            continue

        new_polish_note = browser.mw.col.new_note(polish_model)
        for field_name in original_note.keys():
            new_polish_note[field_name] = original_note[field_name]

        cards = original_note.cards()
        if cards:
            deck_id = cards[0].did
            browser.mw.col.add_note(new_polish_note, deck_id)
            move_queue_to_top(new_polish_note.id, browser)
        else:
            showInfo("Couldn't find deck ID")

    return deck_id

def add_english_note(selected_notes, deck_id, browser: Browser):
    english_model = browser.mw.col.models.by_name(TYPE_ENGLISH)
    new_note = browser.mw.col.new_note(english_model)
    combined_fields = {}

    for note_id in selected_notes:
        note = browser.mw.col.get_note(note_id)
        note_type = note.model()['name']
        if note_type == TYPE_ENGLISH:
            continue

        for field_name in note.keys():
            field_value = note[field_name]
            if field_name not in combined_fields:
                combined_fields[field_name] = set()
            combined_fields[field_name].add(field_value)
    count_words = 0;
    for field_name, values in combined_fields.items():

        if len(values) > 1:
            values = {val for val in values if val.strip()}
            if "Image" in field_name:
                values = {next(iter(values))}
        new_note[field_name] = ', '.join(sorted(values))

        if "Foreign" in field_name:
            count_words = len(values);

    if count_words > 1:
        new_note["Polish/MultiLuka"] += f' [{count_words}]'

    browser.mw.col.add_note(new_note, deck_id)
    move_queue_to_top(new_note.id, browser)

def my_custom_function(browser: Browser):
    deck_id = ""
    selected_notes = browser.selected_notes()
    if len(selected_notes) < 2:
        showInfo("Please select at least two notes.")
        return

    deck_id = add_polish_notes(selected_notes, deck_id, browser)
    add_english_note(selected_notes, deck_id, browser)
    delete_notes(selected_notes, browser)
    browser.model.reset()

    showInfo(f"Done")

def add_custom_menu(browser: Browser):
    # Create a new action
    action = QAction("Combine synonymous", browser)
    # Pass the browser to my_custom_function using a lambda
    action.triggered.connect(lambda: my_custom_function(browser))

    # Create a new menu
    custom_menu = QMenu("MINE", browser)
    custom_menu.addAction(action)

    # Add the new custom menu to the browser's menu bar
    browser.form.menubar.addMenu(custom_menu)

# Hook the function to the browser when it's initialized
gui_hooks.browser_menus_did_init.append(add_custom_menu)
