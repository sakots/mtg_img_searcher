import asyncio
import html
import io
import os
import re
from urllib import parse

import bs4
import discord
import requests
from dotenv import load_dotenv
from mtg_image_similarity import (
  download_card_image,
  find_similar_card,
  is_image_attachment,
  read_image_attachment,
)


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


def _clean_image_url(value):
  if not value:
    return None

  value = html.unescape(value).replace("\\/", "/")
  value = parse.unquote(value).strip()
  if value.startswith("//"):
    value = f"https:{value}"

  if value.startswith(("http://", "https://")):
    return value

  return None


def _urls_from_srcset(srcset):
  for item in srcset.split(","):
    url = item.strip().split(" ")[0]
    image_url = _clean_image_url(url)
    if image_url:
      yield image_url


def _urls_from_link_href(href):
  link_url = _clean_image_url(href)
  if not link_url:
    return

  parsed_url = parse.urlparse(link_url)
  query = parse.parse_qs(parsed_url.query)
  for param_name in ("imgurl", "image_url", "imageUrl", "url", "u", "rurl"):
    for value in query.get(param_name, []):
      image_url = _clean_image_url(value)
      if image_url:
        yield image_url


def _urls_from_page_text(text):
  for match in re.finditer(r"https?:\\?/\\?/[^\"'<>\s]+", text):
    image_url = _clean_image_url(match.group(0))
    if image_url:
      yield image_url


def _yahoo_mtg_img_urls(command):
  query = f"+{command} (MTG or マジック or ギャザ or magic) (カード or card)"
  params = {
    "p": query,
    "ei": "UTF-8",
    "n": "60",
    "dim": "",
    "imw": "",
    "imh": "",
    "imt": "",
    "imc": "",
    "ctype": "",
  }
  url = "https://search.yahoo.co.jp/image/search?" + parse.urlencode(params)

  response = requests.get(url, headers=HEADERS, timeout=15)
  response.raise_for_status()

  soup = bs4.BeautifulSoup(response.text, "html.parser")
  seen = set()

  def unique_urls(urls):
    for image_url in urls:
      if image_url is None or image_url in seen:
        continue
      seen.add(image_url)
      yield image_url

  for img in soup.find_all("img"):
    for attr_name in ("src", "data-src", "data-original"):
      yield from unique_urls([_clean_image_url(img.get(attr_name))])
    if img.get("srcset"):
      yield from unique_urls(_urls_from_srcset(img["srcset"]))

  for link in soup.find_all("a"):
    yield from unique_urls(_urls_from_link_href(link.get("href")))

  yield from unique_urls(_urls_from_page_text(response.text))


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


def download_first_yahoo_mtg_image(command):
  try:
    image_urls = _yahoo_mtg_img_urls(command)

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

  image_attachments = [attachment for attachment in message.attachments if is_image_attachment(attachment)]
  if client.user in message.mentions and image_attachments:
    async with message.channel.typing():
      try:
        image_bytes = await read_image_attachment(image_attachments[0])
        card = await asyncio.to_thread(find_similar_card, image_bytes)
        if card is not None:
          result = await asyncio.to_thread(download_card_image, card)
        else:
          result = None
      except (ValueError, requests.RequestException, OSError) as error:
        print(f"Image similarity search failed: {error}")
        result = None

    if result is None:
      await message.channel.send("似ているカードが見つかりませんでした＞＜")
      return

    image_bytes, filename = result
    image_file = discord.File(io.BytesIO(image_bytes), filename=filename)
    await message.channel.send(f"{card.name}\n{card.scryfall_uri}", file=image_file)
    return

  if not message.content.startswith(PREFIX):
    return

  command = message.content[len(PREFIX):].strip()

  if command == "":
    await message.channel.send("??")
    return

  async with message.channel.typing():
    result = await asyncio.to_thread(download_first_yahoo_mtg_image, command)

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
