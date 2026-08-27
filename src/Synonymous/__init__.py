from aqt import gui_hooks, mw
from aqt.qt import QAction, QMenu
from aqt.utils import showInfo, getText
from aqt.browser import Browser
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QProgressBar, QPushButton, QComboBox, QLabel, QLineEdit, QPlainTextEdit
from PyQt6.QtCore import Qt
from aqt.qt import QApplication
import re
import os
import requests

from .collins_dict import fetch_pronunciation
from .helper_methods import READ_POLISH, TYPE_ENGLISH, DOUBLE, create_note, create_note_from_existing, \
    delete_notes, has_card_type, add_note_and_move_queue_up, read_json_file, write_json_file, \
    call_gemini_api_async, SETTINGS_FILE, GEMINI_KEY_KEY

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
        self.setWindowTitle("Adding...")
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

LANGUAGES_KEY = "languages"

DEFAULT_ENGLISH = {"name": "angielski", "level": "B2-C1", "deck": None}

#The only user-editable part of the sentences prompt
DEFAULT_STYLE_PROMPT = (
    "- Używaj naturalnego, współczesnego języka (np. praca, życie codzienne).\n"
    "- Zdania mają jasno ilustrować dane znaczenie."
)

SENTENCES_PROMPT_TEMPLATE = (
    "Działaj jako precyzyjny generator danych CSV dla osób uczących się języka.\n\n"
    "ZADANIE:\n"
    "- Na podstawie podanego słowa i jego znaczeń utwórz po jednym naturalnym zdaniu w języku: {language} "
    "(poziom {level}) dla każdego znaczenia i przetłumacz je na polski.\n"
    "{style}\n\n"
    "PRZYKŁAD POPRAWNEGO FORMATU:\n"
    "I finally figured out how this device works.|W końcu zrozumiałem, jak działa to urządzenie.\n\n"
    "PRZYKŁAD NIEPOPRAWNY (NIE RÓB TAK):\n"
    "I finally figured out how this device works.\n"
    "W końcu zrozumiałem, jak działa to urządzenie.\n\n"
    "ZASADY FORMATOWANIA (BEZWZGLĘDNE):\n"
    "- Zwróć WYŁĄCZNIE wynik w formacie CSV: Zdanie w języku {language}|Polskie zdanie\n"
    "- NIE dodawaj słowa kluczowego ani definicji na początku.\n"
    "- NIE dodawaj żadnych wstępów, komentarzy, numeracji ani pustych linii.\n"
    "- Używaj wyłącznie separatora | i nie używaj cudzysłowów, chyba że są częścią zdania.\n"
    "- Każde znaczenie to dokładnie jedna linia w formacie CSV.\n\n"
    "Oto słówko:\n"
    "Słówko ({language}): {foreign}\n"
    "Polski: {polish}"
)

def get_languages(settings):
    languages = settings.get(LANGUAGES_KEY) or [dict(DEFAULT_ENGLISH)]
    for lang in languages:
        if not lang.get("style"):
            lang["style"] = DEFAULT_STYLE_PROMPT
    return languages

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Synonymous settings")
        self.filepath, self.settings = read_json_file(SETTINGS_FILE)
        self.decks = sorted(mw.col.decks.all_names_and_ids(), key=lambda deck: deck.name)
        self.lang_rows = []

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Gemini API key:", self))
        key_row = QHBoxLayout()
        self.key_input = QLineEdit(self)
        self.key_input.setText(self.settings.get(GEMINI_KEY_KEY, ""))
        self.key_input.setPlaceholderText("Paste your Gemini API key")
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setEnabled(False)
        key_row.addWidget(self.key_input)
        self.key_edit_btn = QPushButton("Edit", self)
        self.key_edit_btn.setFixedWidth(50)
        self.key_edit_btn.clicked.connect(self.toggle_key_edit)
        key_row.addWidget(self.key_edit_btn)
        layout.addLayout(key_row)

        layout.addWidget(QLabel("Languages (generate sentences):", self))
        self.langs_layout = QVBoxLayout()
        layout.addLayout(self.langs_layout)
        for i, lang in enumerate(get_languages(self.settings)):
            self.add_language_row(lang, removable=(i > 0))

        add_btn = QPushButton("+", self)
        add_btn.clicked.connect(lambda: self.add_language_row({"name": "", "level": "", "deck": None}, removable=True))
        layout.addWidget(add_btn)

        save_btn = QPushButton("Save", self)
        save_btn.clicked.connect(self.save)
        layout.addWidget(save_btn)

    def toggle_key_edit(self):
        editing = not self.key_input.isEnabled()
        self.key_input.setEnabled(editing)
        self.key_input.setEchoMode(QLineEdit.EchoMode.Normal if editing else QLineEdit.EchoMode.Password)
        self.key_edit_btn.setText("Hide" if editing else "Edit")
        if editing:
            self.key_input.setFocus()

    def add_language_row(self, lang, removable):
        row = QHBoxLayout()
        name_input = QLineEdit(self)
        name_input.setText(lang.get("name", ""))
        name_input.setPlaceholderText("angielski")
        level_input = QLineEdit(self)
        level_input.setText(lang.get("level", ""))
        level_input.setPlaceholderText("A2")

        deck_combo = QComboBox(self)
        for deck in self.decks:
            deck_combo.addItem(deck.name, deck.id)
        if lang.get("deck") is not None:
            index = deck_combo.findData(lang["deck"])
            if index >= 0:
                deck_combo.setCurrentIndex(index)

        row.addWidget(QLabel("language:", self))
        row.addWidget(name_input)
        row.addWidget(QLabel("level:", self))
        row.addWidget(level_input)
        row.addWidget(QLabel("deck:", self))
        row.addWidget(deck_combo)

        style_input = QPlainTextEdit(self)
        style_input.setPlainText(lang.get("style") or DEFAULT_STYLE_PROMPT)
        style_input.setFixedHeight(60)

        entry = {"name": name_input, "level": level_input, "deck": deck_combo, "style": style_input, "row": row}
        if removable:
            remove_btn = QPushButton("x", self)
            remove_btn.setFixedWidth(30)
            remove_btn.clicked.connect(lambda _, e=entry: self.remove_language_row(e))
            row.addWidget(remove_btn)
        else:
            #Default english cannot be renamed or removed
            name_input.setEnabled(False)

        self.lang_rows.append(entry)
        self.langs_layout.addLayout(row)
        self.langs_layout.addWidget(style_input)

    def remove_language_row(self, entry):
        self.lang_rows.remove(entry)
        while entry["row"].count():
            item = entry["row"].takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.langs_layout.removeItem(entry["row"])
        entry["style"].deleteLater()

    def save(self):
        languages = []
        for entry in self.lang_rows:
            name = entry["name"].text().strip()
            if not name:
                continue
            languages.append({
                "name": name,
                "level": entry["level"].text().strip(),
                "deck": entry["deck"].currentData(),
                "style": entry["style"].toPlainText().strip() or DEFAULT_STYLE_PROMPT,
            })
        self.settings[GEMINI_KEY_KEY] = self.key_input.text().strip()
        self.settings[LANGUAGES_KEY] = languages
        write_json_file(self.filepath, self.settings)
        self.accept()

def open_settings(browser: Browser):
    if SettingsDialog(browser).exec():
        build_mine_menu(browser)

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

def add_pronunciation(browser: Browser, is_english = True):
    selected = browser.selectedNotes()
    if not selected:
        showInfo("Please select at least one note.")
        return

    json = "pron_and_ipa_list" if is_english else "pron_and_ipa_list_it"
    filepath, pron_dict = read_json_file(json)

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
            ipa, audio_url = fetch_pronunciation(word, is_english)

            if (not ipa or not audio_url) and "-" in word:
               words.extend(word.split("-"))
               continue

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
                pron_dict[word]['sound'] = ""
                audio_list.append("")

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

def generate_sentences(browser: Browser, lang: dict):
    selected = browser.selectedNotes()
    if not selected:
        showInfo("Please select at least one note.")
        return
    _, settings = read_json_file(SETTINGS_FILE)
    if not settings.get(GEMINI_KEY_KEY):
        showInfo("No Gemini API key set in settings")
        return

    error = ""
    style = lang.get("style") or DEFAULT_STYLE_PROMPT
    saved_deck = lang.get("deck")

    # Open progress and cancel window
    progress_dialog = ProgressDialog(len(selected), mw)
    progress_dialog.show()
    QApplication.processEvents()

    for idx, note_id in enumerate(selected):
        # Cancel
        if progress_dialog.canceled:
            break

        note = mw.col.get_note(note_id)
        deck_id = saved_deck if saved_deck else note.cards()[0].did

        note_field = note[FOREIGN_FIELD]
        note_field = re.sub(r'^to\s', '', note_field)
        note_field = re.sub(r'\[\d+\]', '', note_field)
        note_field = re.sub(r'\'s\b', '', note_field)
        note_field = note_field.replace("&nbsp;", " ")
        words = re.split(r'\s*,\s*', note_field.strip()) or note_field.split(",")
        for word in words:
            if not word.strip():
                continue

            #Call Gemini
            prompt_values = {
                "language": lang.get("name", ""),
                "level": lang.get("level", ""),
                "style": style,
                "foreign": word,
                "polish": note[POLISH_FIELD],
            }
            ask_gemini = SENTENCES_PROMPT_TEMPLATE
            for key, value in prompt_values.items():
                ask_gemini = ask_gemini.replace("{" + key + "}", str(value))
            gemini_response = call_gemini_api_async(ask_gemini)
            if gemini_response is None:
                error += f"{note_field}: gemini returned none;"
                continue
            splitted_sentences = [line for line in gemini_response.split("\n") if line.strip()]
            if len(splitted_sentences) == 0:
                error +=  f"{note_field}: gemini returned wrong format (\\n) "
                continue
            for sentence_line in splitted_sentences:
                parts = sentence_line.split("|")
                if len(parts) != 2:
                    error +=  f"{note_field}: gemini returned wrong format (|) "
                    continue
                # Create note
                new_polish_note = create_note(TYPE_ENGLISH)
                new_polish_note[FOREIGN_FIELD] = parts[0]
                new_polish_note[POLISH_FIELD] = parts[1]
                add_note_and_move_queue_up(new_polish_note, deck_id)


        note.flush()
        # Go to next word in queue
        progress_dialog.progress.setValue(idx + 1)
        QApplication.processEvents()

    progress_dialog.close()
    browser.model.reset()
    if error:
        showInfo(f"Could not generate sentences: {error}")
    else:
        showInfo("Sentences generated")

def build_mine_menu(browser: Browser):
    custom_menu = getattr(browser, "_synonymous_menu", None)
    if custom_menu is None:
        custom_menu = QMenu("MINE", browser)
        browser._synonymous_menu = custom_menu
        browser.form.menubar.addMenu(custom_menu)
    custom_menu.clear()

    action_add = QAction("Add synonymous", browser)
    action_add.triggered.connect(lambda: add_english_synonym(browser))
    custom_menu.addAction(action_add)

    action_split = QAction("Split polish synonymous", browser)
    action_split.triggered.connect(lambda: split_polish_synonymous(browser))
    custom_menu.addAction(action_split)

    _, settings = read_json_file(SETTINGS_FILE)
    for lang in get_languages(settings):
        action_gen = QAction(f"Generate sentences {lang['name']}", browser)
        action_gen.triggered.connect(lambda _=False, l=lang: generate_sentences(browser, l))
        custom_menu.addAction(action_gen)

    action_settings = QAction("Settings", browser)
    # Prevent macOS from moving "Settings" into the app menu as Preferences
    action_settings.setMenuRole(QAction.MenuRole.NoRole)
    action_settings.triggered.connect(lambda: open_settings(browser))
    custom_menu.addAction(action_settings)

# Hook the function to the browser when it's initialized
gui_hooks.browser_menus_did_init.append(build_mine_menu)
