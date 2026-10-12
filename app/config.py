import os
from dotenv import load_dotenv

load_dotenv()

FLASK_ENV = os.environ.get("FLASK_ENV", "development")
IS_PRODUCTION = os.environ.get("RENDER") == "true" or FLASK_ENV == "production"

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
if IS_PRODUCTION and (not SECRET_KEY or SECRET_KEY == "dev-secret-key-change-in-production"):
    raise RuntimeError("SECRET_KEY bắt buộc phải được thiết lập an toàn trong môi trường Production!")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dulich")
import urllib.parse

OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL", "")
CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
if not CLOUDINARY_CLOUD_NAME and CLOUDINARY_URL:
    try:
        parsed_c = urllib.parse.urlparse(CLOUDINARY_URL)
        CLOUDINARY_CLOUD_NAME = parsed_c.hostname or ""
    except Exception:
        pass

IMAGE_VERSION = os.environ.get("IMAGE_VERSION", "2")

