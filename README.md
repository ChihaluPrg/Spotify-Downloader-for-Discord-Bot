# Spotify-Downloader-for-Discord-Bot

SpotifyのURLから音楽をダウンロードできるDiscord Botです。

## セットアップ

1. 必要なパッケージをインストール:
```bash
pip install -r requirements.txt
```

2. FFmpegのインストール:
   - Windows: [FFmpegの公式サイト](https://ffmpeg.org/download.html)からダウンロード、またはChocolateyで `choco install ffmpeg`
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg` (Ubuntu/Debian) or `sudo yum install ffmpeg` (CentOS/RHEL)

3. `.env`ファイルを作成:
   - `DISCORD_TOKEN=○○○○○○○○`Discord Botのトークンを設定
   - `SPOTIFY_CLIENT_ID=○○○○○○○○`Spotify開発者アカウントのClient IDを設定
   - `SPOTIFY_CLIENT_SECRET=○○○○○○○○`Spotify開発者アカウントのClient Secretを

## 使い方

Botは以下のコマンドに対応しています：

- `/download [Spotify URL]` - 指定されたSpotifyの曲をダウンロード
- `/list` - ダウンロード済みの曲リストを表示 
- `/help_music` - コマンドの使い方を表示
## 注意事項

- このBotは個人使用を目的としています