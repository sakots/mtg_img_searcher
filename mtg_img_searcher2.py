import discord
import bs4
import requests
import os
import shutil
import argparse
import sys
import json
import urllib.request, urllib.error
from urllib import request as req
from urllib import error
from urllib import parse


# 自分のBotのアクセストークンに置き換えてください
TOKEN = '自分のBotのアクセストークンに置き換えてください'

def _google_mtgimg_search(word):

    if os.path.exists('img'):
        shutil.rmtree('./img')
    if not os.path.exists('img'):
        os.mkdir('img')

    urlKeyword = parse.quote(word)
    url = 'https://www.google.com/search?as_st=y&tbm=isch&hl=ja&as_q=' + urlKeyword + '+img_sys&as_epq=&as_oq=&as_eq=&cr=&as_sitesearch=mtg-jp.com&safe=images&tbs=iar:t,ift:png'

    headers = {"User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:47.0) Gecko/20100101 Firefox/47.0",}
    request = req.Request(url=url, headers=headers)
    page = req.urlopen(request)

    html = page.read().decode('utf-8')
    html = bs4.BeautifulSoup(html, "html.parser")
    elems = html.select('.rg_meta.notranslate')

    counter = 0
    for ele in elems:
        ele = ele.contents[0].replace('"','').split(',')
        eledict = dict()
        for e in ele:
            num = e.find(':')
            eledict[e[0:num]] = e[num+1:]
        imageURL = eledict['ou']

        pal = '.jpg'
        if '.jpg' in imageURL:
            pal = '.jpg'
        elif '.JPG' in imageURL:
            pal = '.jpg'
        elif '.png' in imageURL:
            pal = '.png'
        elif '.gif' in imageURL:
            pal = '.gif'
        elif '.jpeg' in imageURL:
            pal = '.jpeg'
        else:
            pal = '.png'

        try:
            img = req.urlopen(imageURL)
            localfile = open('./img/'+str(counter)+pal, 'wb')
            localfile.write(img.read())
            img.close()
            localfile.close()
            counter += 1
        except UnicodeEncodeError:
            continue
        except error.HTTPError:
            continue
        except error.URLError:
            continue

# 接続に必要なオブジェクトを生成
client = discord.Client()

# 起動時に動作する処理
@client.event
async def on_ready():
    # 起動したらターミナルにログイン通知が表示される
    print('ログインしました')

# メッセージ受信時に動作する処理
@client.event
async def on_message(message):
    # 「>>」で始まるか調べる
    if message.content.startswith(">>"):
        # 送り主がBotだった場合反応したくないので
        if client.user != message.author:
            command = message.content[len(">>"):].lower().strip()

            filepath = 'img/0.png'

            _google_mtgimg_search(command)
            await message.channel.send(command)
            if os.path.isfile('img/0.png') == False:
                await message.channel.send('＞＜')
            await message.channel.send(file=discord.File(filepath))

# Botの起動とDiscordサーバーへの接続
client.run(TOKEN)