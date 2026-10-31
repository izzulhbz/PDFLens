from argon2 import PasswordHasher

from app.security.passwords import hash_password, needs_rehash, verify_password


def test_hash_is_argon2id_and_never_the_password():
    password_hash = hash_password("correct horse battery staple")

    assert password_hash.startswith("$argon2id$")
    assert "correct horse" not in password_hash


def test_same_password_hashes_differently_each_time():
    # A random salt per hash means equal passwords don't produce equal
    # hashes, so precomputed (rainbow) tables are useless.
    assert hash_password("same password!") != hash_password("same password!")


def test_verify_accepts_right_password_and_rejects_wrong_one():
    password_hash = hash_password("correct horse battery staple")

    assert verify_password(password_hash, "correct horse battery staple") is True
    assert verify_password(password_hash, "Correct horse battery staple") is False


def test_verify_returns_false_for_a_corrupt_hash():
    assert verify_password("not-a-hash", "anything") is False


def test_hash_with_weaker_parameters_needs_rehash():
    weak = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash("pw")

    assert needs_rehash(weak) is True
    assert needs_rehash(hash_password("pw")) is False
