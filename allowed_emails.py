"""
Allowed Users Configuration

This module contains the list of allowed user emails/IDs that can access the API.
Only users in this list will be granted access to the API endpoints.
"""

# Email allow list - only users with these emails can access the API
ALLOWED_EMAILS = [
    'hanlin.li@oligolink.com',
        # Tom
    'minxz162@gmail.com',
    'z08040992048@gmail.com',

    # Chen
    'qwchen.phd@gmail.com',

    # Yuan
    'yweilin753@gmail.com',

    # Ann
    'ganartal@gmail.com',

    # Stev
    'metalstiv93@gmail.com',

    # Oleg
    'Licht9estalt@proton.me',
    'oleg.lichtgestalt@gmail.com',

    # Takeshi Yamada
    'yamada.takeshi@tmd.ac.jp',
    'yamada61801',

    # Xicheng Sun
    'xichengs@yahoo.com',
    'sun469775',

    # Jef
    'jafar.199685@gmail.com',

    # Nakatani
    'nakatani@sanken.osaka-u.ac.jp',

    # Eitaro Murakami
    'murakami41234',

    # Lttbio
    'lttbio653024',

    # Yamamoto
    'yamamoto14234',

    # Crestone
    'crestone52345',

    # Existing users from MongoDB (non-test users)
    'Chen',
    'DLeader',
    'Tom',
    'Tom1',
    'Tom2',
    'Test user',
]


def is_user_allowed(user_id: str) -> bool:
    """Check if the given user_id/email is in the allowed list.

    Args:
        user_id: The user identifier (email or username) to check

    Returns:
        True if the user is allowed, False otherwise
    """
    if not user_id:
        return False
    # Case-insensitive comparison
    user_id_lower = user_id.lower().strip()
    return user_id_lower in [e.lower() for e in ALLOWED_EMAILS]


def add_user(user_id: str) -> None:
    """Add a user to the allowed list (runtime only, not persisted).

    Args:
        user_id: The user identifier to add
    """
    if user_id and user_id not in ALLOWED_EMAILS:
        ALLOWED_EMAILS.append(user_id)


def remove_user(user_id: str) -> bool:
    """Remove a user from the allowed list (runtime only, not persisted).

    Args:
        user_id: The user identifier to remove

    Returns:
        True if user was removed, False if not found
    """
    user_id_lower = user_id.lower().strip()
    for email in ALLOWED_EMAILS:
        if email.lower() == user_id_lower:
            ALLOWED_EMAILS.remove(email)
            return True
    return False


def get_allowed_users() -> list:
    """Get the list of all allowed users.

    Returns:
        List of allowed user identifiers
    """
    return ALLOWED_EMAILS.copy()
