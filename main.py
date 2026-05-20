import asyncio
import io
import json
import os
from urllib import parse

import bs4
import discord
import requests
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("TOKEN")
PREFIX = ">>"

HEADERS = {
  "User-Agent": (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
  ),
  "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

CARD_ASPECT_RATIO = 63 / 88
CARD_ASPECT_TOLERANCE = 0.08

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
  print(f"Logged in as {client.user} ({client.user.id})")


def _bing_mtg_img_urls(command):
  query = f"+{command} (MTG OR マジック OR ギャザ OR magic) (カード OR card)"
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


def _read_image_size(image_bytes):
  if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") and len(image_bytes) >= 24:
    return int.from_bytes(image_bytes[16:20], "big"), int.from_bytes(image_bytes[20:24], "big")

  if image_bytes.startswith((b"GIF87a", b"GIF89a")) and len(image_bytes) >= 10:
    return int.from_bytes(image_bytes[6:8], "little"), int.from_bytes(image_bytes[8:10], "little")

  if image_bytes.startswith(b"\xff\xd8"):
    index = 2
    while index + 9 < len(image_bytes):
      if image_bytes[index] != 0xff:
        index += 1
        continue

      marker = image_bytes[index + 1]
      index += 2
      if marker in (0xd8, 0xd9):
        continue
      if index + 2 > len(image_bytes):
        return None

      segment_length = int.from_bytes(image_bytes[index:index + 2], "big")
      if segment_length < 2 or index + segment_length > len(image_bytes):
        return None

      if marker in (0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf):
        return (
          int.from_bytes(image_bytes[index + 5:index + 7], "big"),
          int.from_bytes(image_bytes[index + 3:index + 5], "big"),
        )

      index += segment_length

  if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
    chunk_type = image_bytes[12:16]
    if chunk_type == b"VP8 " and len(image_bytes) >= 30:
      return (
        int.from_bytes(image_bytes[26:28], "little") & 0x3fff,
        int.from_bytes(image_bytes[28:30], "little") & 0x3fff,
      )
    if chunk_type == b"VP8L" and len(image_bytes) >= 25:
      bits = int.from_bytes(image_bytes[21:25], "little")
      return (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
    if chunk_type == b"VP8X" and len(image_bytes) >= 30:
      return (
        int.from_bytes(image_bytes[24:27], "little") + 1,
        int.from_bytes(image_bytes[27:30], "little") + 1,
      )

  return None


def _is_card_aspect_ratio(image_bytes):
  size = _read_image_size(image_bytes)
  if size is None:
    return False

  width, height = size
  if width <= 0 or height <= 0:
    return False

  return abs((width / height) - CARD_ASPECT_RATIO) <= CARD_ASPECT_TOLERANCE


def download_first_bing_mtg_image(command):
  try:
    image_urls = _bing_mtg_img_urls(command)

    for image_url in image_urls:
      try:
        response = requests.get(image_url, headers=HEADERS, timeout=20)
        response.raise_for_status()
      except requests.RequestException:
        continue

      content_type = response.headers.get("content-type", "")
      if not content_type.startswith("image/"):
        continue

      if not _is_card_aspect_ratio(response.content):
        continue

      extension = _extension_from_response(response)
      return response.content, f"mtg_image{extension}"
  except requests.RequestException:
    return None

  return None


@client.event
async def on_message(message):
  if message.author.bot:
    return

  if not message.content.startswith(PREFIX):
    return

  command = message.content[len(PREFIX):].strip()

  if command == "":
    await message.channel.send("??")
    return

  async with message.channel.typing():
    result = await asyncio.to_thread(download_first_bing_mtg_image, command)

  if result is None:
    await message.channel.send("＞＜")
    return

  image_bytes, filename = result
  image_file = discord.File(io.BytesIO(image_bytes), filename=filename)
  await message.channel.send(file=image_file)


if __name__ == "__main__":
  if TOKEN is None:
    raise RuntimeError(".env に TOKEN=DiscordのBotトークン を設定してください")

  client.run(TOKEN)
