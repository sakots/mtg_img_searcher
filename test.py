import json
import os
from pathlib import Path
from urllib import parse

import bs4
import requests


HEADERS = {
  "User-Agent": (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
  ),
  "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def _bing_mtg_img_urls(command):
  query = f"{command} (MTG OR マジック OR ギャザ OR magic) カード"
  params = {
    "q": query,
    "qft": "+filterui:aspect-tall",
    "form": "HDRSC2",
    "first": "1",
  }
  url = "https://www.bing.com/images/search?" + parse.urlencode(params)

  response = requests.get(url, headers=HEADERS, timeout=15)
  response.raise_for_status()

  soup = bs4.BeautifulSoup(response.text, "html.parser")

  for elem in soup.select("a.iusc"):
    metadata = elem.get("m")
    if not metadata:
      continue

    try:
      image_url = json.loads(metadata).get("murl")
    except json.JSONDecodeError:
      continue

    if image_url and image_url.startswith(("http://", "https://")):
      yield image_url

  for img in soup.find_all("img"):
    image_url = img.get("src") or img.get("data-src")
    if image_url and image_url.startswith(("http://", "https://")):
      yield image_url


def _extension_from_response(response):
  content_type = response.headers.get("content-type", "").split(";")[0]
  return {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
  }.get(content_type, ".jpg")


def download_first_bing_mtg_image(command, output_dir="img"):
  Path(output_dir).mkdir(exist_ok=True)

  for image_url in _bing_mtg_img_urls(command):
    try:
      response = requests.get(image_url, headers=HEADERS, timeout=20)
      response.raise_for_status()
    except requests.RequestException:
      continue

    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/"):
      continue

    filepath = Path(output_dir) / f"0{_extension_from_response(response)}"
    filepath.write_bytes(response.content)
    return filepath

  return None


if __name__ == "__main__":
  command = "デブ霊夢"
  filepath = download_first_bing_mtg_image(command)

  if filepath is None:
    print("画像をダウンロードできませんでした")
  else:
    print(f"ダウンロードしました: {os.fspath(filepath)}")
