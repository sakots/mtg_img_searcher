# mtg_img_searcher

MTG Image searcher

## 何？

入力された文字列にmtgを加えてyahooで画像検索してmtg-jp.comのギャラリーから1件返すだけのDiscordBot。
![マツコ](https://github.com/sakots/mtg_img_searcher/blob/master/image.png "サンプル")

google検索バージョンも用意しました。こっちはちょっと重い。
![ジェラード](https://github.com/sakots/mtg_img_searcher/blob/master/image2.png "サンプル")

## 使い方

`pip3 install discord.py bs4 urllib3`

client.run( )の中身を自分のBotのアクセストークンに置き換えてください。

Bot管理画面のPRESENCE INTENTをONにしてください。

## こうしんりれき

### 22/12/23

エラーを出なくした。画像はダウンロードできない。検索の仕様変わった？

### 22/12/22

ver2 ~~画像検索サイトをgatherer.wizards.comとmtg-jp.comにした。~~ 画像サイズ最適化によりおっぱい最適化復活。

### 19/09/22

ver2 画像を1件だけダウンロードするように無理やりした。

### 19/09/11

google検索を使ったver2公開。こちらは一度画像をダウンロードします。

### 19/09/10 2度め

画像ファイルをpng限定にすることによりカード以外が出る可能性をさらに下げた。

### 19/09/10

mtgカードギャラリーの画像サイズが1パターンではないことが判明したため修正。おっぱい最適化を断念。

### 19/09/06

とりあえず公開
