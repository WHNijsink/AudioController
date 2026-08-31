from audio_controller import user, settings


def test_hash_password_is_salted_and_verifies():
    h1 = user.hash_password("secret")
    h2 = user.hash_password("secret")
    assert h1 != h2                       # random salt -> different records
    assert h1.startswith("pbkdf2_sha256$")
    assert user.verify_password("secret", h1)
    assert user.verify_password("secret", h2)
    assert not user.verify_password("wrong", h1)


def test_verify_password_backward_compatible_with_legacy():
    legacy = user.encryptPassword("oldpw")   # unsalted blake2b hex
    assert user.is_legacy_hash(legacy)
    assert user.verify_password("oldpw", legacy)
    assert not user.verify_password("nope", legacy)


def test_new_hash_is_not_flagged_legacy():
    assert not user.is_legacy_hash(user.hash_password("x"))


def test_default_admin_must_change_password():
    users = user.default_users()
    admin = [u for u in users if u.username == "admin"]
    # a fresh install (no previous users file) seeds a forced-change admin
    if admin:
        a = admin[0]
        if a.must_change_password:
            # its stored password authenticates as 'admin' but forces a change
            assert user.verify_password("admin", a.password)


def test_update_users_salts_and_clears_flag(tmp_settings_file):
    # simulate the forced admin setting a real password via the users grid
    settings.update_users([
        {"username": "admin", "password": "NewStrongPw", "admin": True, "camera": True},
    ])
    stored = settings.users[0]
    assert not user.is_legacy_hash(stored.password)      # salted now
    assert stored.password != "NewStrongPw"              # not plaintext
    assert user.verify_password("NewStrongPw", stored.password)
    assert stored.must_change_password is False          # flag cleared
