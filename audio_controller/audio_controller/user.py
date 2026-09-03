""" """

import secrets
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
    # These hold the cookie-signing secret and the user records: owner-only, so a
    # local user cannot read the secret (and forge admin sessions) or the users.
    try:
        os.chmod(file, 0o600)
    except OSError:
        pass

@dataclass
class User:
    username: str
    password: str
    admin: bool = False
    camera: bool = False
    must_change_password: bool = False


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
    if lines and lines[0].strip():
        return lines[0].strip()  # remove "\n"
    # Generate with a CSPRNG (was random.choice on the Mersenne-Twister PRNG,
    # which is not cryptographically secure). This secret signs all auth cookies.
    secret = secrets.token_hex(32)
    with open(file_cookie, 'w') as f:
        f.write(f"{secret}\n")
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
