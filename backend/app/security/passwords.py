"""Password hashing with Argon2id.

Argon2id won the Password Hashing Competition and is OWASP's first choice.
It is deliberately slow and memory-hungry: if the users table ever leaked,
each password guess would cost an attacker real time and 64 MiB of memory,
which also takes away most of the advantage of cracking on GPUs.

argon2-cffi's defaults follow the RFC 9106 recommended profile
(time_cost=3, memory_cost=64 MiB, parallelism=4) and generate a random salt
for every hash. The stored string records its own parameters and salt, for
example $argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>, so the cost can be
raised later and old hashes upgraded as users log in (see needs_rehash).
"""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

# When someone logs in with an email that has no account, we still verify
# their password against this throwaway hash. Otherwise "no such user"
# would answer much faster than "wrong password", and the response time
# alone would tell an attacker which emails are registered.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True if the hash was made with weaker parameters than the current ones."""
    return _hasher.check_needs_rehash(password_hash)


def spend_equal_time(password: str) -> None:
    """Take as long as a real password check, for the unknown-email case."""
    verify_password(_DUMMY_HASH, password)
