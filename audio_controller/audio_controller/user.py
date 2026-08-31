""" """

import random
import string
import hashlib
import hmac
import os, sys
from pathlib import Path
from dataclasses import dataclass, field, asdict, is_dataclass



# file to save usernames and passwords
file_users = Path.home() / ".audio_controller_users.txt"
# file to save cookie secret
file_cookie = Path.home() / ".audio_controller_cookie.txt"

for file in [file_users, file_cookie]:
    if not file.exists():
        with open(file, 'w'):
            pass

@dataclass
class User:
    username: str
    password: str
    admin: bool = False
    camera: bool = False
    must_change_password: bool = False


def clear_users():
    with open(file_users, 'w') as f:
        f.writelines([])


def add_user(username: str, password: str):
    assert ";" not in username
    pw = encryptPassword(password)
    line = f"{username};{pw}\n"
    with open(file_users, 'a') as f:
        f.write(line)


def check_user(username: str, password: str):
    pw = encryptPassword(password)
    with open(file_users, 'r') as f:
        lines = f.readlines()
    for line in lines:
        [username_, pw_] = line.split(";")
        pw_ = pw_.strip()  # remove "\n"
        if username == username_ and pw == pw_:
            return True
    return False


def get_users():
    users: list[User] = []

    with open(file_users, "r") as f:
        for line in f:
            username, password = line.strip().split(";")
            users.append(
                User(
                    username=username,
                    password=password
                )
            )

    return users

def encryptPassword(password):
    """ Legacy unsalted hash. Kept only to verify (and migrate) old stored passwords. """
    return hashlib.blake2b(password.encode()).hexdigest()


# Salted, slow password hashing (replaces the unsalted blake2b for stored passwords).
# Format: "pbkdf2_sha256$<rounds>$<salt_hex>$<hash_hex>".
_PBKDF2_ROUNDS = 200000


def hash_password(password: str) -> str:
    """ Return a salted PBKDF2-SHA256 record for a plaintext password. """
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", str(password).encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def is_legacy_hash(stored: str) -> bool:
    """ True if the stored password is an old unsalted blake2b hex hash. """
    return not str(stored).startswith("pbkdf2_sha256$")


def verify_password(password: str, stored: str) -> bool:
    """ Verify a plaintext password against a stored hash. Accepts both the new
    salted format and legacy unsalted blake2b hashes (backward compatible). """
    stored = str(stored)
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, rounds, salt_hex, hash_hex = stored.split("$")
            dk = hashlib.pbkdf2_hmac("sha256", str(password).encode(),
                                     bytes.fromhex(salt_hex), int(rounds))
            return hmac.compare_digest(dk.hex(), hash_hex)
        except (ValueError, TypeError):
            return False
    # legacy unsalted blake2b
    return hmac.compare_digest(encryptPassword(password), stored)

def get_cookie_secret():
    with open(file_cookie, 'r') as f:
        lines = f.readlines()
    if lines:
        return lines[0].strip()  # remove "\n"
    else:
        random_string = ''.join(random.choice(string.ascii_letters) for i in range(30))
        secret = hashlib.sha256(random_string.encode()).hexdigest()
        with open(file_cookie, 'a') as f:
            line = f"{secret}\n"
            f.write(line)
            return secret


def default_users():
    """ Default users, used as initial and factory defaults """
    result = []

    # first: import previous users file
    previous_registered = get_users()
    for usr in previous_registered:
        usr.admin = True
        result.append( usr )

    # else: import default user. The default admin authenticates with 'admin',
    # but must_change_password forces setting a real password before anything
    # else can be done (see the login gate in handlers).
    if len(result) == 0:
        result.append(User('admin', hash_password("admin"), True, True,
                           must_change_password=True))

    return result


def test():
    return
    sys.exit(0)
