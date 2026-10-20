import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Values that must never be used as a real secret key.
_UNSAFE_SECRET_KEYS = {"", "your-secret-key-here", "dev-secret-key-change-me"}


def resolve_secret_key(value):
    """Return (key, is_random). A missing or placeholder key becomes a random per-run key."""
    if value is None or value.strip() in _UNSAFE_SECRET_KEYS:
        return secrets.token_hex(32), True
    return value, False


SECRET_KEY, SECRET_KEY_IS_RANDOM = resolve_secret_key(os.getenv("SECRET_KEY"))
DATABASE = str(BASE_DIR / "instance" / "campusfix.db")
UPLOAD_FOLDER = str(BASE_DIR / "uploads")
# Uploaded issue images: size and dimension limits (checked again on the image content).
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
# Whole-request limit: a little above the image limit to leave room for the other form fields.
MAX_CONTENT_LENGTH = 6 * 1024 * 1024
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}

# Shared choices used by routes and templates.
ALLOWED_STATUSES = ["Pending", "In Progress", "Resolved"]
CATEGORY_CHOICES = ["Electrical", "Plumbing", "Furniture", "Civil", "Cleaning", "Other"]
AI_PRIORITY_CHOICES = ["Critical", "Important", "Normal", "Low"]
