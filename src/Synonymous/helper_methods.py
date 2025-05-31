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