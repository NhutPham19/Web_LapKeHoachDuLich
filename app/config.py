import os
from dotenv import load_dotenv

load_dotenv()

FLASK_ENV = os.environ.get("FLASK_ENV", "development")
IS_PRODUCTION = os.environ.get("RENDER") == "true" or FLASK_ENV == "production"

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
if IS_PRODUCTION and (not SECRET_KEY or SECRET_KEY == "dev-secret-key-change-in-production"):
    raise RuntimeError("SECRET_KEY bắt buộc phải được thiết lập an toàn trong môi trường Production!")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/dulich")
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")

