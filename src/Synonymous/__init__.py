from aqt import gui_hooks, mw
from aqt.qt import QAction, QMenu
from aqt.utils import showInfo, getText
from aqt.browser import Browser
import logging
import re
logging.basicConfig(level=logging.DEBUG, filename='anki_debug.log', filemode='w')

#Card type
DOUBLE = "1. Podwójny (wpisywanie odpowiedzi)"
TYPE_ENGLISH = "2. Pojedynczy (wpisywanie angielski)"
READ_POLISH = "3. Podstawowy (odczytywanie polski)"

#Fields
FOREIGN_FIELD = "Foreign/Content"
POLISH_FIELD = "Polish/MultiLuka"
AUDIO_FIELD = "Audio"
IMAGE_FIELD = "Image"
PART_OF_SPEECH_FIELD = "PartOfSpeech"
EXTRA_FIELD = "Extra"
DIALECT_FIELD = "Dialect"

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
    count_words = 0
    for field_name, values in combined_fields.items():

        if len(values) > 1:
            values = {val for val in values if val.strip()}

        delimiter = ', '
        if field_name in [EXTRA_FIELD, IMAGE_FIELD, AUDIO_FIELD]:
            delimiter = "<br>"
        new_note[field_name] = delimiter.join(sorted(values))

        if "Foreign" in field_name:
            count_words = len(values)

    if count_words > 1:
        new_note[POLISH_FIELD] += f' [{count_words}]'
    if len(combined_fields[DIALECT_FIELD]) > 0:
        for dial in combined_fields[DIALECT_FIELD]:
            for note_id in selected_notes:
                note = browser.mw.col.get_note(note_id)
                if dial in note[DIALECT_FIELD]:
                    new_note[EXTRA_FIELD] += f'<br>{dial} - {note[POLISH_FIELD]}'

    browser.mw.col.add_note(new_note, deck_id)
    move_queue_to_top(new_note.id, browser)

def combine_english_synonymous(browser: Browser):
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

def add_word_to_existing_note(browser, note, word):
    note[FOREIGN_FIELD] += f", {word}"

    old_polish_text = note[POLISH_FIELD]
    match = re.search(r'\[(\d+)\]', old_polish_text)
    if match:
        number = int(match.group(1))
        new_number = number + 1
        old = match.group(0)
        new = f'[{new_number}]'
        note[POLISH_FIELD] = old_polish_text.replace(old, new, 1)
    else:
        note[POLISH_FIELD] += " [2]"

    note.flush()
    mw.col.reset()
    browser.model.reset()

def add_new_polish_note_for_synomymous(browser, note, word):
    polish_model = browser.mw.col.models.by_name(READ_POLISH)
    new_polish_note = browser.mw.col.new_note(polish_model)

    new_polish_note[FOREIGN_FIELD] = word
    new_polish_note[POLISH_FIELD] = re.sub(r'\[\d+\]', '', note[POLISH_FIELD])
    new_polish_note[IMAGE_FIELD] = note[IMAGE_FIELD]
    new_polish_note[PART_OF_SPEECH_FIELD] = note[PART_OF_SPEECH_FIELD]
    new_polish_note[EXTRA_FIELD] = note[EXTRA_FIELD]

    deck_id = note.cards()[0].did
    browser.mw.col.add_note(new_polish_note, deck_id)
    move_queue_to_top(new_polish_note.id, browser)

def add_english_synonym(browser: Browser):
    selected = browser.selectedNotes()
    if not selected:
        showInfo("Please select one note.")
        return
    if len(selected) > 1:
        showInfo("Please select only one note.")
        return

    nid = selected[0]
    note = mw.col.get_note(nid)

    word, ok = getText("Enter an English synonym:")
    if not ok or not word.strip():
        return

    note_type = note.model()['name']
    if note_type == DOUBLE:
        deck_id = add_polish_notes(selected, "", browser)
        add_new_polish_note_for_synomymous(browser, note, word)

        add_word_to_existing_note(browser, note, word)
        add_english_note(selected, deck_id, browser)

        delete_notes(selected, browser)
    else:
        add_word_to_existing_note(browser, note, word)
        add_new_polish_note_for_synomymous(browser, note, word)

    showInfo(f"Added synonym {word}")

def split_polish_synonymous(browser: Browser):
    selected = browser.selectedNotes()
    if not selected:
        showInfo("Please select one note.")
        return
    if len(selected) > 1:
        showInfo("Please select only one note.")
        return

    nid = selected[0]
    note = mw.col.get_note(nid)

    splitted_note = note[POLISH_FIELD].split(';')
    if len(splitted_note) <= 1:
        showInfo("Nothing to split.")
        return

    card_english_type = browser.mw.col.models.by_name(TYPE_ENGLISH)
    card_polish_read = browser.mw.col.models.by_name(READ_POLISH)

    new_polish_note = browser.mw.col.new_note(card_polish_read)
    for field in note.keys():
        new_polish_note[field] = note[field]
    new_polish_note[FOREIGN_FIELD] += f'[{len(splitted_note)}]'

    deck_id = note.cards()[0].did
    browser.mw.col.add_note(new_polish_note, deck_id)
    move_queue_to_top(new_polish_note.id, browser)

    for polish_word in splitted_note:
        new_english_note = browser.mw.col.new_note(card_english_type)

        for field in note.keys():
            new_english_note[field] = note[field]
        new_english_note[POLISH_FIELD] = polish_word

        browser.mw.col.add_note(new_english_note, deck_id)
        move_queue_to_top(new_english_note.id, browser)

    delete_notes(selected, browser)
    browser.model.reset()
    showInfo(f"Splitted {', '.join(splitted_note)}")

def add_custom_menu(browser: Browser):
    # Action 1
    action_combine = QAction("Combine english synonymous", browser)
    action_combine.triggered.connect(lambda: combine_english_synonymous(browser))

    # Action 2
    action_add = QAction("Add english synonymous", browser)
    action_add.triggered.connect(lambda: add_english_synonym(browser))

    # Action 3
    action_split = QAction("Split polish synonymous", browser)
    action_split.triggered.connect(lambda: split_polish_synonymous(browser))

    # Create menu and add both actions
    custom_menu = QMenu("MINE", browser)
    custom_menu.addAction(action_combine)
    custom_menu.addAction(action_add)
    custom_menu.addAction(action_split)

    # Add the new custom menu to the browser's menu bar
    browser.form.menubar.addMenu(custom_menu)

# Hook the function to the browser when it's initialized
gui_hooks.browser_menus_did_init.append(add_custom_menu)
