import os
import sys

from tp_mcp.auth import clear_credential, get_credential, store_credential, validate_auth_sync


def set_cookie():
    """Reads Production_tpAuth cookie from stdin or env and stores it."""
    cookie = os.environ.get("TP_AUTH_COOKIE")
    if not cookie:
        print("Pasting Production_tpAuth cookie from stdin. Press Enter and Ctrl+D to submit:")
        cookie = sys.stdin.read().strip()

    if not cookie:
        print("Error: No cookie provided.", file=sys.stderr)
        sys.exit(1)

    res = store_credential(cookie)
    if res.success:
        print(f"Success: {res.message}")
    else:
        print(f"Error: {res.message}", file=sys.stderr)
        sys.exit(1)


def print_status():
    """Validates the stored credentials and prints the auth status."""
    res = get_credential()
    if not res.success or not res.cookie:
        print("Status: No credentials found.")
        sys.exit(0)

    # Validate cookie
    cookie = res.cookie
    print("Validating credentials with TrainingPeaks API...")
    val_res = validate_auth_sync(cookie)

    print(f"Validation Status: {val_res.status.value}")
    if val_res.is_valid:
        print(f"  Athlete ID: {val_res.athlete_id}")
        print(f"  User ID: {val_res.user_id}")
        print(f"  Email: {val_res.email}")
    else:
        print(f"  Message: {val_res.message}")
        sys.exit(1)


def clear_credentials():
    """Clears stored credentials from all backends."""
    res = clear_credential()
    print(f"Cleared credentials: {res.message}")
