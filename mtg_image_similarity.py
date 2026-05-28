import io
import json
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import Image, ImageOps


HEADERS = {
  "User-Agent": "mtg-img-searcher/0.1 (Discord bot; Scryfall image similarity cache)",
  "Accept": "application/json,image/*;q=0.9,*/*;q=0.8",
}

SCRYFALL_BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
CACHE_DIR = Path(".cache")
CACHE_PATH = CACHE_DIR / "scryfall_image_hashes.json"

HASH_SIZE = 8
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024
SCRYFALL_BULK_TYPE = "unique_artwork"


@dataclass
class SimilarCard:
  name: str
  image_url: str
  scryfall_uri: str
  distance: int


def is_image_attachment(attachment):
  content_type = attachment.content_type or ""
  if content_type.startswith("image/"):
    return True

  return Path(attachment.filename).suffix.lower() in IMAGE_EXTENSIONS


async def read_image_attachment(attachment):
  if attachment.size > MAX_ATTACHMENT_BYTES:
    raise ValueError("画像が大きすぎます")

  return await attachment.read()


def find_similar_card(image_bytes):
  target_hashes = _image_hashes(image_bytes)
  entries = _load_or_build_cache()

  best_entry = None
  best_distance = None
  for entry in entries:
    distance = min(
      _hamming_distance(target_hashes["ahash"], entry["ahash"]) + _hamming_distance(target_hashes["dhash"], entry["dhash"]),
      _hamming_distance(target_hashes["crop_ahash"], entry["ahash"]) + _hamming_distance(target_hashes["crop_dhash"], entry["dhash"]),
    )
    if best_distance is None or distance < best_distance:
      best_distance = distance
      best_entry = entry

  if best_entry is None:
    return None

  return SimilarCard(
    name=best_entry["name"],
    image_url=best_entry["image_url"],
    scryfall_uri=best_entry["scryfall_uri"],
    distance=best_distance,
  )


def download_card_image(card):
  response = requests.get(card.image_url, headers=HEADERS, timeout=20)
  response.raise_for_status()
  return response.content, "mtg_similar_card.jpg"


def _load_or_build_cache():
  if _cache_is_fresh():
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))["cards"]

  CACHE_DIR.mkdir(exist_ok=True)
  _write_cache([], complete=False)

  cards = _download_scryfall_cards()
  entries = []
  seen = set()
  for card in cards:
    for card_image in _card_images(card):
      cache_key = (card_image["name"], card_image["image_url"])
      if cache_key in seen:
        continue
      seen.add(cache_key)

      try:
        image_bytes = _download_image(card_image["image_url"])
        hashes = _image_hashes(image_bytes)
      except (OSError, requests.RequestException, ValueError):
        continue

      entries.append({
        "name": card_image["name"],
        "scryfall_uri": card_image["scryfall_uri"],
        "image_url": card_image["image_url"],
        "ahash": hashes["ahash"],
        "dhash": hashes["dhash"],
      })

      if len(entries) % 250 == 0:
        _write_cache(entries, complete=False)

      time.sleep(0.05)

  if not entries and CACHE_PATH.exists():
    return json.loads(CACHE_PATH.read_text(encoding="utf-8"))["cards"]

  _write_cache(entries, complete=True)
  return entries


def _write_cache(entries, complete):
  CACHE_DIR.mkdir(exist_ok=True)
  CACHE_PATH.write_text(json.dumps({
    "created_at": int(time.time()),
    "complete": complete,
    "cards": entries,
  }, ensure_ascii=False), encoding="utf-8")


def _cache_is_fresh():
  if not CACHE_PATH.exists():
    return False

  try:
    payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
  except json.JSONDecodeError:
    return False

  cards = payload.get("cards")
  return isinstance(cards, list) and len(cards) > 0


def _download_scryfall_cards():
  response = requests.get(SCRYFALL_BULK_DATA_URL, headers=HEADERS, timeout=20)
  response.raise_for_status()
  bulk_items = response.json()["data"]
  bulk_data = next(
    (item for item in bulk_items if item["type"] == SCRYFALL_BULK_TYPE),
    next(item for item in bulk_items if item["type"] == "default_cards"),
  )

  response = requests.get(bulk_data["download_uri"], headers=HEADERS, timeout=120)
  response.raise_for_status()
  return response.json()


def _card_images(card):
  scryfall_uri = card.get("scryfall_uri", "")
  if "image_uris" in card:
    image_url = card["image_uris"].get("small") or card["image_uris"].get("normal")
    if image_url:
      yield {
        "name": card.get("name", "Unknown"),
        "scryfall_uri": scryfall_uri,
        "image_url": image_url,
      }
    return

  for face in card.get("card_faces", []):
    image_uris = face.get("image_uris")
    if not image_uris:
      continue

    image_url = image_uris.get("small") or image_uris.get("normal")
    if image_url:
      yield {
        "name": face.get("name") or card.get("name", "Unknown"),
        "scryfall_uri": scryfall_uri,
        "image_url": image_url,
      }


def _download_image(url):
  response = requests.get(url, headers=HEADERS, timeout=20)
  response.raise_for_status()
  content_type = response.headers.get("content-type", "")
  if not content_type.startswith("image/"):
    raise ValueError("画像ではありません")
  return response.content


def _image_hashes(image_bytes):
  image = Image.open(io.BytesIO(image_bytes))
  image = ImageOps.exif_transpose(image).convert("L")
  return {
    "ahash": _average_hash(image),
    "dhash": _difference_hash(image),
    "crop_ahash": _average_hash(_center_crop_card_art(image)),
    "crop_dhash": _difference_hash(_center_crop_card_art(image)),
  }


def _average_hash(image):
  small = ImageOps.fit(image, (HASH_SIZE, HASH_SIZE), method=Image.Resampling.LANCZOS)
  pixels = list(small.getdata())
  average = sum(pixels) / len(pixels)
  bits = "".join("1" if pixel >= average else "0" for pixel in pixels)
  return f"{int(bits, 2):016x}"


def _difference_hash(image):
  small = ImageOps.fit(image, (HASH_SIZE + 1, HASH_SIZE), method=Image.Resampling.LANCZOS)
  pixels = list(small.getdata())
  bits = []
  for y in range(HASH_SIZE):
    row = y * (HASH_SIZE + 1)
    for x in range(HASH_SIZE):
      bits.append("1" if pixels[row + x] > pixels[row + x + 1] else "0")
  return f"{int(''.join(bits), 2):016x}"


def _center_crop_card_art(image):
  width, height = image.size
  if width <= 0 or height <= 0:
    return image

  left = int(width * 0.08)
  right = int(width * 0.92)
  top = int(height * 0.14)
  bottom = int(height * 0.55)
  if right <= left or bottom <= top:
    return image

  return image.crop((left, top, right, bottom))


def _hamming_distance(left_hash, right_hash):
  return (int(left_hash, 16) ^ int(right_hash, 16)).bit_count()
