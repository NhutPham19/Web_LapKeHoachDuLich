import base64
import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from typing import Optional


def slugify(text: str) -> str:
    """Chuyển đổi chuỗi tiếng Việt thành slug an toàn cho Cloudinary public_id."""
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("utf-8")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "_", text)


def upload_image_file(file_storage, province: str, dest_name: str) -> Optional[dict]:
    """
    Tải file ảnh từ máy tính (Flask FileStorage) lên Cloudinary:
    - Lưu vào đúng thư mục: dulich_vn/destinations/<hub>/<slug>
    - Đặt public_id chuẩn hóa
    - Trả về dict: {"public_id": str, "secure_url": str, "format": str}
    """
    cloudinary_url = os.environ.get("CLOUDINARY_URL")
    if not cloudinary_url:
        return None

    parsed = urllib.parse.urlparse(cloudinary_url)
    api_key = parsed.username
    api_secret = parsed.password
    cloud_name = parsed.hostname
    if not (api_key and api_secret and cloud_name):
        return None

    file_bytes = file_storage.read()
    if not file_bytes:
        return None

    hub_slug = slugify(province or "viet_nam")
    dest_slug = slugify(dest_name or f"dest_{int(time.time())}")
    folder = f"dulich_vn/destinations/{hub_slug}"
    public_id = f"{folder}/{dest_slug}"

    content_type = getattr(file_storage, "content_type", "") or "image/jpeg"
    b64_content = f"data:{content_type};base64," + base64.b64encode(file_bytes).decode("utf-8")

    timestamp = int(time.time())
    to_sign = f"asset_folder={folder}&public_id={public_id}&timestamp={timestamp}{api_secret}"
    signature = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()

    payload = {
        "file": b64_content,
        "public_id": public_id,
        "asset_folder": folder,
        "timestamp": timestamp,
        "api_key": api_key,
        "signature": signature,
    }

    upload_url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
    post_data = urllib.parse.urlencode(payload).encode("utf-8")

    req = urllib.request.Request(
        upload_url,
        data=post_data,
        headers={"User-Agent": "Mozilla/5.0 DuLichAdminUploader/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return {
            "public_id": res.get("public_id", public_id),
            "secure_url": res.get("secure_url", ""),
            "format": res.get("format", "jpg"),
        }
