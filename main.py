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

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user} ({client.user.id})")


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
