import base64
import csv
import hashlib
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
API_HEADERS = {"User-Agent": USER_AGENT}


def get_cloudinary_credentials():
    cloudinary_url = os.environ.get("CLOUDINARY_URL")
    if not cloudinary_url:
        raise ValueError("Chưa thiết lập biến môi trường CLOUDINARY_URL trong .env")

    parsed = urllib.parse.urlparse(cloudinary_url)
    api_key = parsed.username
    api_secret = parsed.password
    cloud_name = parsed.hostname

    if not (api_key and api_secret and cloud_name):
        raise ValueError("Chuỗi CLOUDINARY_URL không đúng định dạng: cloudinary://<key>:<secret>@<cloud_name>")

    return cloud_name, api_key, api_secret


def upload_single_image(cloud_name: str, api_key: str, api_secret: str, image_url: str, public_id: str) -> dict:
    clean_url = image_url.split("?")[0]
    # 1. Tải ảnh từ Wikimedia về bộ nhớ đệm (có retry backoff chống 403 rate-limit)
    img_bytes = None
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(clean_url, headers=API_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                img_bytes = resp.read()
                break
        except Exception as e:
            last_err = e
            time.sleep(1.0 * (attempt + 1))

    if not img_bytes:
        raise last_err or RuntimeError("Không thể tải ảnh sau 3 lần thử")

    b64_content = "data:image/jpeg;base64," + base64.b64encode(img_bytes).decode("utf-8")

    # 2. Tạo chữ ký SHA-1 cho Cloudinary
    timestamp = int(time.time())
    to_sign = f"public_id={public_id}&timestamp={timestamp}{api_secret}"
    signature = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()

    # 3. Gửi POST request lên Cloudinary API
    upload_url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
    post_data = urllib.parse.urlencode({
        "file": b64_content,
        "public_id": public_id,
        "timestamp": timestamp,
        "api_key": api_key,
        "signature": signature,
    }).encode("utf-8")

    post_req = urllib.request.Request(upload_url, data=post_data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(post_req, timeout=25) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upload_all_destinations(max_items: int = 100):
    cloud_name, api_key, api_secret = get_cloudinary_credentials()
    root_dir = Path(__file__).resolve().parent.parent
    manifest_path = root_dir / "db" / "seed" / "image_manifest.csv"
    cache_path = root_dir / "db" / "seed" / ".cloudinary_upload_cache.json"
    dest_path = root_dir / "db" / "seed" / "destinations.csv"

    cache = {}
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_rows = list(csv.DictReader(f))

    print(f"=== BẮT ĐẦU UPLOAD ẢNH LÊN CLOUDINARY (Cloud: {cloud_name}) ===")
    print(f"Tổng số điểm cần xử lý: {len(manifest_rows)}")

    success_count = 0
    skip_count = 0
    error_count = 0

    for idx, row in enumerate(manifest_rows, start=1):
        if idx > max_items:
            break

        name = row["name"]
        public_id = row["image_public_id"]
        thumb_url = row["thumbnail_url"]
        status = row["review_status"]

        if status != "APPROVED" or not thumb_url:
            continue

        if public_id in cache:
            skip_count += 1
            continue

        print(f"[{idx}/{len(manifest_rows)}] Đang tải: {name} -> {public_id} ...", end=" ", flush=True)
        try:
            res = upload_single_image(cloud_name, api_key, api_secret, thumb_url, public_id)
            cache[public_id] = {
                "secure_url": res.get("secure_url"),
                "bytes": res.get("bytes"),
                "format": res.get("format"),
                "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            success_count += 1
            print("THÀNH CÔNG!")
            time.sleep(0.2)
        except Exception as e:
            error_count += 1
            print(f"LỖI ({e})")
            time.sleep(0.5)

    # Lưu cache
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 50)
    print("HOÀN TẤT UPLOAD CLOUDINARY:")
    print(f"  - Thành công mới: {success_count}")
    print(f"  - Đã có sẵn (bỏ qua): {skip_count}")
    print(f"  - Lỗi: {error_count}")
    print(f"  - Tổng số ảnh đã có trên Cloudinary: {len(cache)}")
    print("=" * 50)


if __name__ == "__main__":
    upload_all_destinations()
