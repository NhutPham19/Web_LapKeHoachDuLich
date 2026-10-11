import csv
import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

USER_AGENT = "DuLich-App/1.0 (nhutpham@example.com; student-project)"
API_HEADERS = {"User-Agent": USER_AGENT}

WHITELIST_LICENSES = [
    "CC0",
    "PUBLIC DOMAIN",
    "PD",
    "CC-ZERO",
    "CC BY",
    "CC BY-SA",
    "CREATIVE COMMONS CC0",
]

BLACKLIST_KEYWORDS = ["NC", "ND", "NONCOMMERCIAL", "NODERIVATIVES", "FAIR USE"]


def slugify(text: str) -> str:
    """Chuyển đổi chuỗi tiếng Việt thành slug ASCII chuẩn."""
    text = unicodedata.normalize("NFD", text)
    text = re.sub(r"[\u0300-\u036f]", "", text)
    text = text.replace("đ", "d").replace("Đ", "D")
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text


def is_license_approved(license_str: str) -> bool:
    if not license_str:
        return False
    upper = license_str.upper()
    for b in BLACKLIST_KEYWORDS:
        if b in upper:
            return False
    for w in WHITELIST_LICENSES:
        if w in upper:
            return True
    return False


def query_wikimedia_for_destination(name: str, province: str, cache: dict) -> dict | None:
    cache_key = f"{province}::{name}"
    if cache_key in cache:
        return cache[cache_key]

    queries_to_try = [
        f"{name} ({province})",
        name,
        f"{name} {province}",
    ]

    result = None
    for q in queries_to_try:
        try:
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": q,
                "gsrlimit": 1,
                "prop": "pageimages",
                "pithumbsize": 1600,
                "format": "json",
            }
            url = "https://vi.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
            req = urllib.request.Request(url, headers=API_HEADERS)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                pages = data.get("query", {}).get("pages", {})
                for pid, p in pages.items():
                    if "thumbnail" in p:
                        thumb_url = p["thumbnail"]["source"]
                        page_img = p.get("pageimage", "")
                        if page_img:
                            # Lấy metadata từ Commons
                            meta = query_commons_metadata(page_img)
                            if meta and is_license_approved(meta.get("license", "")):
                                result = {
                                    "image_url": thumb_url,
                                    "pageimage": page_img,
                                    "author": meta.get("author", "Unknown"),
                                    "license": meta.get("license", "CC BY-SA"),
                                    "source_url": meta.get("source_url", ""),
                                }
                                break
            time.sleep(0.3)
            if result:
                break
        except Exception:
            time.sleep(0.3)
            continue

    cache[cache_key] = result
    return result


def query_commons_metadata(file_name: str) -> dict | None:
    try:
        file_title = file_name if file_name.startswith("File:") else f"File:{file_name}"
        params = {
            "action": "query",
            "titles": file_title,
            "prop": "imageinfo",
            "iiprop": "extmetadata|url",
            "format": "json",
        }
        url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=API_HEADERS)
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            pages = data.get("query", {}).get("pages", {})
            for pid, p in pages.items():
                imageinfo = p.get("imageinfo", [])
                if not imageinfo:
                    continue
                ii = imageinfo[0]
                meta = ii.get("extmetadata", {})
                artist_raw = meta.get("Artist", {}).get("value", "")
                artist = re.sub(r"<[^>]+>", "", artist_raw).strip() or "Wikimedia Commons Contributor"
                license_name = meta.get("LicenseShortName", {}).get("value", "") or meta.get("License", {}).get("value", "")
                source_url = ii.get("descriptionurl", f"https://commons.wikimedia.org/wiki/{urllib.parse.quote(file_title)}")
                return {
                    "author": artist,
                    "license": license_name,
                    "source_url": source_url,
                }
    except Exception:
        pass
    return None


def upload_to_cloudinary(image_url: str, public_id: str) -> dict | None:
    """Tải ảnh lên Cloudinary qua REST API chuẩn bằng urllib + SHA-1 (không cần thư viện ngoài)."""
    cloudinary_url = os.environ.get("CLOUDINARY_URL")
    if not cloudinary_url:
        return None

    try:
        parsed = urllib.parse.urlparse(cloudinary_url)
        api_key = parsed.username
        api_secret = parsed.password
        cloud_name = parsed.hostname

        if not (api_key and api_secret and cloud_name):
            return None

        timestamp = int(time.time())
        to_sign = f"public_id={public_id}&timestamp={timestamp}{api_secret}"
        signature = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()

        upload_url = f"https://api.cloudinary.com/v1_1/{cloud_name}/image/upload"
        data = urllib.parse.urlencode({
            "file": image_url,
            "public_id": public_id,
            "timestamp": timestamp,
            "api_key": api_key,
            "signature": signature,
        }).encode("utf-8")

        req = urllib.request.Request(upload_url, data=data, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            res_json = json.loads(resp.read().decode("utf-8"))
            return res_json
    except Exception as e:
        print(f"  [Cloudinary] Không thể tải {public_id}: {e}")
        return None


def run_ingest(perform_cloudinary_upload: bool = False):
    root_dir = Path(__file__).resolve().parent.parent
    dest_path = root_dir / "db" / "seed" / "destinations.csv"
    manifest_path = root_dir / "db" / "seed" / "image_manifest.csv"
    cache_path = root_dir / "db" / "seed" / ".wikimedia_cache.json"

    cache = {}
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    with open(dest_path, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    manifest_rows = []
    updated_dest_rows = []

    print(f"=== Bắt đầu Ingest Wikimedia Images cho {len(reader)} địa điểm ===")

    for idx, row in enumerate(reader, start=1):
        name = row["name"].strip()
        province = row["province"].strip()
        category = row["category_name"].strip()

        hub_slug = slugify(province)
        name_slug = slugify(name)
        public_id = f"dulich_vn/destinations/{hub_slug}/{name_slug}"

        wiki_info = query_wikimedia_for_destination(name, province, cache)

        if wiki_info and wiki_info.get("image_url"):
            img_url = wiki_info["image_url"]
            img_source = "wikimedia"
            img_author = wiki_info.get("author", "Wikimedia Commons")
            img_license = wiki_info.get("license", "CC BY-SA")
            img_source_url = wiki_info.get("source_url", "")
            review_status = "APPROVED"
        else:
            img_url = ""
            img_source = "placeholder"
            img_author = ""
            img_license = ""
            img_source_url = ""
            review_status = "PLACEHOLDER"

        if perform_cloudinary_upload and img_source == "wikimedia" and img_url:
            print(f"  [{idx}/{len(reader)}] Đang upload Cloudinary cho: {name} -> {public_id}")
            upload_to_cloudinary(img_url, public_id)

        manifest_rows.append({
            "id": idx,
            "name": name,
            "province": province,
            "category_name": category,
            "image_public_id": public_id,
            "image_source": img_source,
            "thumbnail_url": img_url,
            "image_author": img_author,
            "image_license": img_license,
            "image_source_url": img_source_url,
            "review_status": review_status,
        })

        updated_row = dict(row)
        updated_row["image_public_id"] = public_id
        updated_row["image_source"] = img_source
        updated_row["image_author"] = img_author
        updated_row["image_license"] = img_license
        updated_row["image_source_url"] = img_source_url
        if img_url:
            updated_row["image_url"] = img_url
        updated_dest_rows.append(updated_row)

    # Lưu cache
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    # Ghi manifest CSV
    manifest_fieldnames = [
        "id", "name", "province", "category_name", "image_public_id",
        "image_source", "thumbnail_url", "image_author", "image_license",
        "image_source_url", "review_status"
    ]
    with open(manifest_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=manifest_fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)
    print(f"-> Đã xuất Image Manifest: {manifest_path}")

    # Ghi đè destinations.csv có thêm 5 cột metadata
    dest_fieldnames = list(reader[0].keys())
    for col in ["image_public_id", "image_source", "image_author", "image_license", "image_source_url"]:
        if col not in dest_fieldnames:
            dest_fieldnames.append(col)

    with open(dest_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=dest_fieldnames)
        writer.writeheader()
        writer.writerows(updated_dest_rows)
    print(f"-> Đã cập nhật destinations.csv với 5 cột metadata ảnh.")

    approved_count = sum(1 for m in manifest_rows if m["review_status"] == "APPROVED")
    placeholder_count = sum(1 for m in manifest_rows if m["review_status"] == "PLACEHOLDER")
    print(f"Thống kê ảnh:")
    print(f"  - Wikimedia Commons (Approved CC license): {approved_count} / {len(reader)}")
    print(f"  - Category Fallback SVG Placeholder: {placeholder_count} / {len(reader)}")


if __name__ == "__main__":
    run_ingest()
