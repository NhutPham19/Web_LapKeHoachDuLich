import base64
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def sync_folders():
    cloudinary_url = os.environ.get("CLOUDINARY_URL")
    if not cloudinary_url:
        print("CLOUDINARY_URL is missing!")
        return

    parsed = urllib.parse.urlparse(cloudinary_url)
    key, secret, cloud = parsed.username, parsed.password, parsed.hostname
    auth_str = base64.b64encode(f"{key}:{secret}".encode()).decode()

    cache_path = Path(__file__).resolve().parent.parent / "db" / "seed" / ".cloudinary_upload_cache.json"
    if not cache_path.exists():
        print("Cache file not found!")
        return

    with open(cache_path, "r", encoding="utf-8") as f:
        cache = json.load(f)

    print(f"Bắt đầu đồng bộ asset_folder cho {len(cache)} ảnh trên Cloudinary...")

    updated = 0
    errors = 0
    for public_id in cache.keys():
        folder = "/".join(public_id.split("/")[:-1])
        if not folder:
            continue

        data = urllib.parse.urlencode({"asset_folder": folder}).encode()
        url = f"https://api.cloudinary.com/v1_1/{cloud}/resources/image/upload/{public_id}"
        req = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {auth_str}"})

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                res = json.loads(resp.read().decode())
                updated += 1
                if updated % 10 == 0 or updated == len(cache):
                    print(f"[{updated}/{len(cache)}] Đã chuyển vào thư mục: {folder} ({public_id.split('/')[-1]})")
        except Exception as e:
            errors += 1
            print(f"Lỗi {public_id}: {e}")

        time.sleep(0.05)

    print(f"\nHoàn tất! Thành công: {updated}, Lỗi: {errors}")


if __name__ == "__main__":
    sync_folders()
