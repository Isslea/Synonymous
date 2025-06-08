from aqt import gui_hooks, mw
from aqt.qt import QAction, QMenu
from aqt.utils import showInfo, getText
from aqt.browser import Browser
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QProgressBar, QPushButton
from PyQt6.QtCore import Qt
from aqt.qt import QApplication
import re
import os
import requests

from .collins_dict import fetch_pronunciation
from .helper_methods import READ_POLISH, TYPE_ENGLISH, DOUBLE, create_note, create_note_from_existing, \
    move_queue_to_top, delete_notes, has_card_type, add_note_and_move_queue_up, read_json_file, write_json_file

#Fields
FOREIGN_FIELD = "Foreign/Content"
POLISH_FIELD = "Polish/MultiLuka"
AUDIO_FIELD = "Audio"
IMAGE_FIELD = "Image"
PART_OF_SPEECH_FIELD = "PartOfSpeech"
EXTRA_FIELD = "Extra"
DIALECT_FIELD = "Dialect"
IPA_FIELD = "IPA"

class ProgressDialog(QDialog):
    def __init__(self, maximum, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Adding pronunciation...")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.canceled = False
        layout = QVBoxLayout(self)
        self.progress = QProgressBar(self)
        self.progress.setMaximum(maximum)
        layout.addWidget(self.progress)
        self.cancel_btn = QPushButton("Anuluj", self)
        self.cancel_btn.clicked.connect(self.cancel)
        layout.addWidget(self.cancel_btn)

    def cancel(self):
        self.canceled = True

def add_english_synonym(browser: Browser):
    selected = browser.selectedNotes()
    if not selected:
        showInfo("Please select one (manual mode) or more (combine mode) notes")
        return

    note_list = []
    note = mw.col.get_note(selected[0])
    deck_id = note.cards()[0].did

    if len(selected) == 1:
        word, ok = getText("Enter an English synonym:")
        if not ok or not word.strip():
            return
        #Fake notes when manual mode
        note[POLISH_FIELD] = re.sub(r'\s*\[\d+\]', '', note[POLISH_FIELD])
        if not has_card_type(note, TYPE_ENGLISH):
            note_list.append(note)
        new_note = create_note_from_existing(DOUBLE, note)
        new_note[AUDIO_FIELD] = ""
        new_note[DIALECT_FIELD] = ""
        new_note[FOREIGN_FIELD] = word
        note_list.append(new_note)
    else:
        for i, value in enumerate(selected):
            curr_note = mw.col.get_note(selected[i])
            if not has_card_type(curr_note, TYPE_ENGLISH):
                note_list.append(curr_note)
            else:
                note = curr_note

    if has_card_type(note, TYPE_ENGLISH):
        new_english_note = create_note_from_existing(TYPE_ENGLISH, note)
        new_english_note[POLISH_FIELD] = re.sub(r'\s*\[\d+\]', '', new_english_note[POLISH_FIELD])
    else:
        new_english_note = create_note(TYPE_ENGLISH)

    for note in note_list:
        # Add new polish note
        new_polish_note = create_note_from_existing(READ_POLISH, note)
        add_note_and_move_queue_up(new_polish_note, deck_id)

    #Fill english note
        for field_name in note.keys():
            if not note[field_name].strip():
                continue

            delimiter = ""
            if new_english_note[field_name].strip():
                delimiter = ', '
                if field_name in [EXTRA_FIELD, IMAGE_FIELD, AUDIO_FIELD]:
                    delimiter = "<br>"

            #Avoid duplicates
            if delimiter:
                if note[field_name] in new_english_note[field_name] or note[field_name] in new_english_note[field_name].split(delimiter):
                    continue

            new_english_note[field_name] += delimiter + note[field_name]

            #Connect dialects with meanings
            if DIALECT_FIELD in field_name:
                dialect_info = ""
                if new_english_note[EXTRA_FIELD]:
                    dialect_info = "<br>"
                dialect_info += f"{note[DIALECT_FIELD]} - {note[POLISH_FIELD]}"
                new_english_note[EXTRA_FIELD] += dialect_info

    #Add polish count
    new_english_note[POLISH_FIELD] += f" [{len(new_english_note[FOREIGN_FIELD].split(','))}]"

    #Add completed english note
    add_note_and_move_queue_up(new_english_note, deck_id)

    #Delete selected note
    delete_notes(selected)
    browser.model.reset()
    showInfo(f"Added synonym")

def split_polish_synonymous(browser: Browser):
    selected = browser.selectedNotes()
    if not selected:
        showInfo("Please select one note.")
        return
    if len(selected) > 1:
        showInfo("Please select only one note.")
        return

    selected_note = mw.col.get_note(selected[0])
    deck_id = selected_note.cards()[0].did

    polish_words = re.sub(r"&nbsp;", " ",selected_note[POLISH_FIELD]).split(';')
    if len(polish_words) <= 1:
        showInfo("Nothing to split.")
        return

    #Create polish combined note
    new_polish_note = create_note_from_existing(READ_POLISH, selected_note)
    new_polish_note[FOREIGN_FIELD] += f' [{len(polish_words)}]'
    add_note_and_move_queue_up(new_polish_note, deck_id)

    #Create english notes
    for polish_word in polish_words:
        new_english_note = create_note_from_existing(TYPE_ENGLISH, selected_note)
        new_english_note[POLISH_FIELD] = polish_word
        add_note_and_move_queue_up(new_english_note, deck_id)

    #Delete selected notes
    delete_notes(selected)
    browser.model.reset()
    showInfo(f"Splitted {', '.join(polish_words)}")

def add_pronunciation(browser: Browser):
    selected = browser.selectedNotes()
    if not selected:
        showInfo("Please select at least one note.")
        return

    filepath, pron_dict = read_json_file("pron_and_ipa_list")

    #Open progress and cancel window
    progress_dialog = ProgressDialog(len(selected), mw)
    progress_dialog.show()
    QApplication.processEvents()
    for idx, note_id in enumerate(selected):
        #Cancel
        if progress_dialog.canceled:
            break

        note = mw.col.get_note(note_id)
        ipa_list = []
        audio_list = []

        note_field = note[FOREIGN_FIELD]
        note_field = re.sub(r'^to\s', '', note_field)
        note_field = re.sub(r'\[\d+\]', '', note_field)
        note_field = re.sub(r'\'s\b', '', note_field)
        note_field = note_field.replace("&nbsp;", " ")
        words = re.split(r'[, ]+', note_field.strip())
        for word in words:
            if not word.strip():
                continue

            #Check if word is already in the dictionary
            if word in pron_dict:
                temp_ipa = pron_dict[word].get('ipa', None)
                temp_sound = pron_dict[word].get('sound', None)
                if temp_ipa and temp_sound:
                    ipa_list.append(temp_ipa)
                    audio_list.append(temp_sound)
                    continue
            else:
                pron_dict[word] = {}

            #Fetch pronunciation and IPA
            ipa, audio_url = fetch_pronunciation(word)

            if ipa:
                ipa_list.append(f"/{ipa}/")
                pron_dict[word]['ipa'] = f"/{ipa}/"
            else:
                ipa_list.append("/-/")
                pron_dict[word]['ipa'] = "/-/"

            if audio_url:
                # Download the audio file
                filename = f"{word}.mp3"
                filetag = f"[sound:{filename}]"
                downloads_dir = os.path.join(os.path.expanduser("~"), "Library/Application Support/Anki2/temp/collection.media")
                file_path = os.path.join(downloads_dir, filename)

                headers = {
                    "User-Agent": "Mozilla/5.0"
                }
                response = requests.get(audio_url, headers=headers)

                if response.status_code == 200:
                    audio_list.append(filetag)
                    pron_dict[word]['sound'] = filetag
                    with open(file_path, "wb") as f:
                        f.write(response.content)
            else:
                audio_list.append("[sound:error.mp3]")
                pron_dict[word]['sound'] = "[sound:error.mp3]"

        # Add IPA and audio to the note
        if len(ipa_list) > 0:
            note[IPA_FIELD] = " ".join(ipa_list) if ipa_list else ""
        if len(audio_list) > 0:
            note[AUDIO_FIELD] = "<br>".join(audio_list) if audio_list else ""
        note.flush()
        # Go to next word in queue
        progress_dialog.progress.setValue(idx + 1)
        QApplication.processEvents()

    progress_dialog.close()
    write_json_file(filepath, pron_dict)
    browser.model.reset()
    showInfo(f"Added pronunciation")

def add_custom_menu(browser: Browser):
    # Action 1
    action_add = QAction("Add synonymous", browser)
    action_add.triggered.connect(lambda: add_english_synonym(browser))

    # Action 2
    action_split = QAction("Split polish synonymous", browser)
    action_split.triggered.connect(lambda: split_polish_synonymous(browser))

    action_pron = QAction("Add pronunciation", browser)
    action_pron.triggered.connect(lambda: add_pronunciation(browser))

    # Create menu and add both actions
    custom_menu = QMenu("MINE", browser)
    custom_menu.addAction(action_add)
    custom_menu.addAction(action_split)
    custom_menu.addAction(action_pron)

    # Add the new custom menu to the browser's menu bar
    browser.form.menubar.addMenu(custom_menu)

# Hook the function to the browser when it's initialized
gui_hooks.browser_menus_did_init.append(add_custom_menu)
