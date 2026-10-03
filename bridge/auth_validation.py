"""Shared bounds for opaque Supabase session tokens, not WQRS secrets."""

MAX_TOKEN_LENGTH = 4096


def valid_session_token(value: object, *, refresh: bool = False) -> bool:
    # Supabase supports legacy 12-character refresh tokens and longer tokens.
    # Access tokens retain their separate lower bound.
    minimum = 12 if refresh else 20
    return (
        isinstance(value, str)
        and minimum <= len(value) <= MAX_TOKEN_LENGTH
        and all(33 <= ord(character) <= 126 for character in value)
    )
