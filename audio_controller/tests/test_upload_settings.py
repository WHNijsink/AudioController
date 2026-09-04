import json
import os
import pickle
from audio_controller import settings, user


def _store_with_user(password):
    return {
        "settings": {"version": 11, "title": "X"},
        "sources": [],
        "destinations": [],
        "psalmbord": {"fontfamily": "Samsung", "fontsize": 8, "fontweight": 400,
                      "active": 1, "screens": [], "refreshrate": 10},
        "cameras": [],
        "users": [{"username": "imported", "password": password, "admin": True}],
    }


def test_set_binary_hashes_plaintext_password_at_rest(tmp_settings_file):
    # S-H1: an uploaded settings file must never persist a cleartext password.
    # A hand-crafted upload with a plaintext password is hashed on the way in.
    settings.set_binary(json.dumps(_store_with_user("letmein")).encode("utf-8"))
    stored = next(u.password for u in settings.users if u.username == "imported")
    assert stored != "letmein"
    assert not user.is_legacy_hash(stored)  # stored as salted pbkdf2, not plaintext/blake2b


def test_set_binary_neutralises_injected_legacy_hash(tmp_settings_file):
    # S-H1: uploading a bare blake2b hash (the legacy format verify_password still
    # accepts) must not yield a working "known-password" account: it is re-hashed,
    # so the attacker's chosen password no longer authenticates.
    attacker_pw = "pwned"
    legacy = user.encryptPassword(attacker_pw)  # unsalted blake2b hex
    settings.set_binary(json.dumps(_store_with_user(legacy)).encode("utf-8"))
    stored = next(u.password for u in settings.users if u.username == "imported")
    assert user.verify_password(attacker_pw, stored) is False


def test_set_binary_keeps_valid_pbkdf2_hash(tmp_settings_file):
    # A genuine backup (from downloadSettings) stores salted pbkdf2 hashes; those
    # must round-trip unchanged so a restore keeps the real password working.
    real_pw = "Str0ngPass!42"
    hashed = user.hash_password(real_pw)
    settings.set_binary(json.dumps(_store_with_user(hashed)).encode("utf-8"))
    stored = next(u.password for u in settings.users if u.username == "imported")
    assert stored == hashed
    assert user.verify_password(real_pw, stored) is True


def _evil_function():
    """This function would be called if the pickle were unpickled."""
    os.environ["PWNED"] = "yes"


class _Evil:
    def __reduce__(self):
        return (_evil_function, ())


def test_set_binary_rejects_malicious_pickle(tmp_settings_file):
    # S2: uploaded settings must be parsed as json, never unpickled.
    os.environ.pop("PWNED", None)
    settings.settings.title = "Before"
    payload = pickle.dumps(_Evil())
    settings.set_binary(payload)  # must NOT execute the pickle
    assert "PWNED" not in os.environ
    assert settings.settings.title == "Before"  # unchanged


def test_set_binary_accepts_valid_json(tmp_settings_file):
    store = {
        "settings": {"version": 11, "title": "Uploaded"},
        "sources": [],
        "destinations": [],
        "psalmbord": {"fontfamily": "Samsung", "fontsize": 8, "fontweight": 400,
                      "active": 1, "screens": [], "refreshrate": 10},
        "cameras": [],
        "users": [],
    }
    settings.set_binary(json.dumps(store).encode("utf-8"))
    assert settings.settings.title == "Uploaded"
    assert tmp_settings_file.exists()


def test_set_binary_rejects_non_settings_json(tmp_settings_file):
    settings.settings.title = "Keep"
    settings.set_binary(json.dumps({"foo": "bar"}).encode("utf-8"))
    assert settings.settings.title == "Keep"  # missing required keys -> ignored


def test_get_binary_returns_json_bytes(tmp_settings_file):
    settings.settings.title = "Bin"
    settings.save()
    raw = settings.get_binary()
    parsed = json.loads(raw)
    assert parsed["settings"]["title"] == "Bin"
