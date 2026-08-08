from core.local_store import LocalStore
from core.text_expansion import expand_snippets


def test_history_survives_store_reopen(tmp_path):
    db_path = tmp_path / "audioscribe.db"
    store = LocalStore(db_path)
    item = store.save_transcription("texto final", raw_text="texto bruto", model="local")
    assert item["text"] == "texto final"
    store.close()

    reopened = LocalStore(db_path)
    items = reopened.list_transcriptions()
    assert len(items) == 1
    assert items[0]["raw_text"] is None
    assert reopened.delete_transcription(item["id"]) is True
    assert reopened.list_transcriptions() == []
    assert reopened._db.execute("SELECT COUNT(*) FROM transcriptions").fetchone()[0] == 0


def test_history_is_opt_in_for_default_store(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIOSCRIBE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("AUDIOSCRIBE_HISTORY_ENABLED", raising=False)
    store = LocalStore()

    assert store.save_transcription("do not persist") == {}
    assert store.list_transcriptions() == []


def test_dictionary_is_case_insensitive_and_supports_manual_promotion(tmp_path):
    store = LocalStore(tmp_path / "dictionary.db")
    assert store.add_dictionary_words(["OpenAI"], "learned") == 1
    assert store.add_dictionary_words(["openai"], "manual") == 1
    entries = store.list_dictionary()
    assert len(entries) == 1
    assert entries[0]["source"] == "manual"


def test_snippets_are_persisted_and_expanded_only_on_word_boundaries(tmp_path):
    store = LocalStore(tmp_path / "snippets.db")
    store.upsert_snippet("minha assinatura", "Atenciosamente,\nRodolfo")
    snippets = store.list_snippets(enabled_only=True)
    assert expand_snippets("Envie minha assinatura hoje", snippets) == "Envie Atenciosamente,\nRodolfo hoje"
    assert expand_snippets("minha assinaturação", snippets) == "minha assinaturação"


def test_disabled_snippets_are_not_expanded(tmp_path):
    store = LocalStore(tmp_path / "disabled.db")
    store.upsert_snippet("abc", "expanded", enabled=False)
    assert expand_snippets("abc", store.list_snippets(enabled_only=True)) == "abc"
