import argparse
import json
import os
import urllib

from urllib import request as req
from urllib import error
from urllib import parse
import bs4

from mimetypes import guess_extension
from urllib.request import urlopen, Request
from urllib.parse import quote
from bs4 import BeautifulSoup
import discord

client = discord.Client()
async def on_ready():
    print('Logged in as')
    print(client.user.name)
    print(client.user.id)
    print('------')

def _request(url):
    # requestを処理しHTMLとcontent-typeを返す
    req = Request(url)
    try:
        with urlopen(req, timeout=5) as p:
             b_content = p.read()
             mime = p.getheader('Content-Type')
    except:
        return None, None
    return b_content, mime

def _yahoo_mtgimg_search(word):
    # yahoo!画像検索の結果から画像を返す
    url = 'https://search.yahoo.co.jp/image/search?n=1&p={}+mtg&vaop=a&fmt=&dim=specific&imw=223&imh=310&imt=&imc=&ctype=&search.x=1'.format(quote(word))
    byte_content, _ = _request(url)
    structured_page = BeautifulSoup(byte_content.decode('UTF-8'), 'html.parser')
    img_link_elems = structured_page.find_all('img')
    # 順番守りつつset取る
    seen = set()
    seen_add = seen.add
    img_urls = [e.get('src') for e in img_link_elems if e.get('src') not in seen and not seen_add(e.get('src'))]
    return img_urls

@client.event
async def on_message(message):
    # 「>>」で始まるか調べる
    if message.content.startswith(">>"):
        # 送り主がBotだった場合反応したくないので
        if client.user != message.author:
            command = message.content[len(">>"):].lower().strip()

            m = _yahoo_mtgimg_search(command)

            await message.channel.send(m)

client.run("自分のBotのアクセストークンに置き換えてください")