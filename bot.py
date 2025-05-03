import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import tempfile
import shutil
from pathlib import Path
import sys
import re
import time
import subprocess


# 環境変数の読み込み
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# spotdlのパス設定 (環境変数から取得するか、デフォルト値を使用)
SPOTDL_PATH = os.getenv("SPOTDL_PATH", "spotdl")

# システムのPythonを使用するための設定
PYTHON_PATH = sys.executable  # 現在実行中のPythonインタープリタのパス

# ダウンロードされたファイルを保存するディレクトリ
DOWNLOAD_DIR = os.getenv(
    "DOWNLOAD_DIR", r"C:\Users\sakip\Music\Spotify_DL"
)  # 環境変数から読み込むよう変更
# ダウンロードディレクトリが存在しない場合は作成
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 最大ファイルサイズ設定（Discord添付ファイルの制限：8MB）
MAX_FILE_SIZE = 20 * 1024 * 1024  # 8MB

# Botの設定
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# spotdlの状態を診断する関数
async def diagnose_spotdl():
    """spotdlのインストール状態を詳細に診断する"""
    results = {
        "installed": False,
        "version": None,
        "path": None,
        "python_path": sys.executable,
        "methods": [],
    }

    # 診断方法1: where/whichコマンドでパスを確認
    try:
        cmd = "where" if sys.platform == "win32" else "which"
        process = await asyncio.create_subprocess_exec(
            cmd,
            "spotdl",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        if process.returncode == 0:
            path = stdout.decode().strip().split("\n")[0]
            results["path"] = path
            results["installed"] = True
            results["methods"].append(f"{cmd}コマンドで検出: {path}")
    except Exception as e:
        results["methods"].append(f"{cmd}コマンドでエラー: {e}")

    # 診断方法2: バージョン確認
    for cmd in [["spotdl", "--version"], [PYTHON_PATH, "-m", "spotdl", "--version"]]:
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            output = stdout.decode() + stderr.decode()

            # バージョン情報を抽出
            version_match = re.search(r"version (\d+\.\d+\.\d+)", output, re.IGNORECASE)
            if version_match:
                results["version"] = version_match.group(1)
                results["installed"] = True
                results["methods"].append(
                    f"{' '.join(cmd)}で検出: v{version_match.group(1)}"
                )
        except Exception as e:
            results["methods"].append(f"{' '.join(cmd)}でエラー: {e}")

    # 診断方法3: pipでインストール済みパッケージを確認
    try:
        process = await asyncio.create_subprocess_exec(
            PYTHON_PATH,
            "-m",
            "pip",
            "list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await process.communicate()
        output = stdout.decode()

        if "spotdl" in output:
            results["methods"].append("pipのインストール済みパッケージとして検出")
            if not results["installed"]:
                results["installed"] = True

            # バージョン情報を抽出
            pip_version_match = re.search(r"spotdl\s+(\d+\.\d+\.\d+)", output)
            if pip_version_match and not results["version"]:
                results["version"] = pip_version_match.group(1)
    except Exception as e:
        results["methods"].append(f"pipでのパッケージ確認中にエラー: {e}")

    return results


# spotdlを直接実行する関数（バッチファイルなし、非同期処理）
async def run_spotdl(args, temp_dir=None):
    """
    spotdlを実行する関数 - 非同期実行で直接実行

    戻り値: (成功したか, 出力, エラー, ファイルリスト)
    """
    # 追加のオプションを設定（出力形式の明示的指定）
    full_args = args.copy()

    # フォーマット指定が含まれていなければ追加
    if "--format" not in " ".join(args):
        full_args.extend(["--format", "mp3"])

    # 出力形式のデバッグ
    print(f"使用する引数: {full_args}")

    # 完全なPythonモジュールパスで実行（最も確実な方法）
    cmd = [PYTHON_PATH, "-m", "spotdl"] + full_args
    print(f"実行コマンド: {' '.join(cmd)}")

    try:
        # 非同期でサブプロセスを実行
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=temp_dir,
        )

        # 標準出力と標準エラーを取得
        stdout, stderr = await process.communicate()
        stdout_text = stdout.decode()
        stderr_text = stderr.decode()

        # 結果の表示
        print(f"終了コード: {process.returncode}")
        if stdout_text:
            print(f"標準出力 (一部): {stdout_text[:200]}...")
        if stderr_text:
            print(f"標準エラー (一部): {stderr_text[:200]}...")

        # 戻り値の確認
        if process.returncode == 0:
            # ダウンロードされたファイルをチェック
            files = []
            if temp_dir:
                # 複数の拡張子をチェック
                for ext in ["mp3", "m4a", "flac", "opus", "ogg", "wav"]:
                    files.extend(list(Path(temp_dir).glob(f"*.{ext}")))

                print(f"ダウンロードされたファイル: {len(files)}個")
                if files:
                    print(f"最初のファイル: {files[0]}")
                else:
                    print(f"ディレクトリ内容: {os.listdir(temp_dir)}")

                    # ファイルがなくてもコマンドが成功した場合は、少し待ってから再確認
                    if "Downloaded" in stdout_text or "Success" in stdout_text:
                        print(
                            "ダウンロード成功のメッセージを検出しましたが、ファイルが見つかりません。待機中..."
                        )
                        # 非同期で待機
                        await asyncio.sleep(2)  # 2秒待機

                        # 再度ファイルをチェック
                        for ext in ["mp3", "m4a", "flac", "opus", "ogg", "wav"]:
                            files.extend(list(Path(temp_dir).glob(f"*.{ext}")))

                        print(f"再チェック後のファイル数: {len(files)}個")

            if files or "Downloaded" in stdout_text or "Success" in stdout_text:
                return True, stdout_text, stderr_text, files
            else:
                return (
                    False,
                    stdout_text,
                    "コマンドは成功しましたが、ファイルが見つかりませんでした",
                    [],
                )
        else:
            return (
                False,
                stdout_text,
                f"コマンド実行エラー (コード {process.returncode}): {stderr_text}",
                [],
            )

    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        print(f"実行例外: {error_details}")
        return False, "", f"コマンド実行例外: {str(e)}", []


# プレイリスト情報を取得する関数（非同期版）
async def get_playlist_info(url):
    """プレイリスト情報を非同期に取得する"""
    if not is_valid_spotify_url(url) or get_spotify_url_type(url) != "playlist":
        return None

    # プレイリストIDを抽出
    match = re.search(r"playlist/([a-zA-Z0-9]+)", url)
    playlist_id = match.group(1) if match else "unknown"

    # 結果を格納する辞書
    result = {
        "url": url,
        "id": playlist_id,
        "title": f"Spotify プレイリスト ({playlist_id})",  # デフォルト値
        "track_count": 20,  # デフォルト値
    }

    try:
        # saveコマンドを非同期で実行
        cmd = [
            PYTHON_PATH,
            "-m",
            "spotdl",
            "save",
            url,
            "--client-id",
            SPOTIFY_CLIENT_ID,
            "--client-secret",
            SPOTIFY_CLIENT_SECRET,
        ]

        # 非同期プロセス実行
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        # 標準出力と標準エラーを取得
        stdout, stderr = await process.communicate()
        output = stdout.decode()

        if process.returncode == 0:
            # saveコマンドの結果から生成されたファイルを取得
            save_file_match = re.search(r"Saved to (.*?\.spotdl)", output)
            if save_file_match:
                saved_file = save_file_match.group(1)
                try:
                    with open(saved_file, "r", encoding="utf-8") as f:
                        tracks = f.readlines()
                        result["track_count"] = len(tracks)
                        print(f"プレイリスト内の曲数: {len(tracks)}")
                except Exception:
                    pass

                # プレイリスト名の抽出
                title_match = re.search(r"Saved songs from (.*?) to", output)
                if title_match:
                    result["title"] = title_match.group(1).strip()
                    print(f"プレイリスト名: {result['title']}")
    except Exception as e:
        print(f"プレイリスト情報取得中にエラー: {e}")

    return result


# Spotify URLの検証関数
def is_valid_spotify_url(url):
    """URLがSpotifyのURLかどうかを確認"""
    # より柔軟な正規表現パターンを使用し、クエリパラメータなどを考慮
    spotify_pattern = re.compile(
        r"https?://(?:open\.)?spotify\.com/(?:track|album|playlist|artist)/[a-zA-Z0-9]+"
    )
    matched = bool(spotify_pattern.match(url))
    print(f"Spotify URL検証: {url} -> {matched}")
    return matched


# Spotify URLのタイプを取得
def get_spotify_url_type(url):
    """SpotifyのURLがどのタイプかを返す (track, album, playlist, artist)"""
    match = re.search(r"spotify\.com/(\w+)/", url)
    return match.group(1) if match else None


# YouTube URLの検証関数
def is_youtube_url(url):
    """URLがYouTubeのURLかどうかを確認（YouTube MusicのURLも含む）"""
    # 正規表現をより寛容にし、ほとんどのYouTube関連URLにマッチするように
    youtube_pattern = re.compile(
        r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com|youtu\.be)(?:/.*)?"
    )
    matched = bool(youtube_pattern.match(url))
    print(f"YouTube URL検証: {url} -> {matched}")
    return matched


# YouTube Musicで曲を検索する関数
async def search_youtube_music(query):
    """
    YouTube Musicで曲を検索し、最初の結果のURLを返す
    """
    print(f"YouTube Musicで検索: {query}")

    search_cmd = ["yt-dlp", f"ytsearch1:{query}", "--get-id", "--no-playlist"]

    try:
        process = await asyncio.create_subprocess_exec(
            *search_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()
        video_id = stdout.decode().strip()

        if video_id:
            url = f"https://music.youtube.com/watch?v={video_id}"
            print(f"検索結果: {url}")
            return url
        else:
            print(f"検索失敗 - エラー: {stderr.decode()}")
            return None
    except Exception as e:
        print(f"YouTube Music検索中にエラー: {str(e)}")
        return None


# yt-dlpを使って動画をダウンロードする関数（MP3形式）
async def run_ytdlp(url, temp_dir=None):
    """
    yt-dlpを使って動画または音楽をMP3形式でダウンロードする関数
    YouTube MusicのURLにも対応

    戻り値: (成功したか, 出力, エラー, ファイルリスト)
    """
    print(f"yt-dlpを使用して音楽/動画をダウンロード: {url}")

    # yt-dlpコマンドを構築
    cmd = [
        "yt-dlp",
        url,
        "-x",  # 音声を抽出
        "--audio-format",
        "mp3",  # MP3形式に変換
        "--audio-quality",
        "0",  # 最高音質
        "-o",
        f"{temp_dir}/%(title)s.%(ext)s",  # 出力パスとファイル名形式
        "--no-playlist",  # プレイリスト全体ではなく単一の曲のみダウンロード（単曲URLの場合）
        "--force-overwrites",  # 既存のファイルを上書き
    ]

    print(f"実行コマンド: {' '.join(cmd)}")

    try:
        # 非同期でサブプロセスを実行
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )

        # 標準出力と標準エラーを取得
        stdout, stderr = await process.communicate()
        stdout_text = stdout.decode()
        stderr_text = stderr.decode()

        # 結果の表示
        print(f"終了コード: {process.returncode}")
        if stdout_text:
            print(f"標準出力 (一部): {stdout_text[:200]}...")
        if stderr_text:
            print(f"標準エラー (一部): {stderr_text[:200]}...")

        # 戻り値の確認
        if process.returncode == 0:
            # ダウンロードされたファイルをチェック
            files = []
            if temp_dir:
                # MP3ファイルを検索
                files = list(Path(temp_dir).glob("*.mp3"))

                print(f"ダウンロードされたファイル: {len(files)}個")
                if files:
                    print(f"最初のファイル: {files[0]}")
                else:
                    print(f"ディレクトリ内容: {os.listdir(temp_dir)}")

                    # 少し待ってから再確認（変換に時間がかかる場合）
                    await asyncio.sleep(2)
                    files = list(Path(temp_dir).glob("*.mp3"))
                    print(f"再チェック後のファイル数: {len(files)}個")

            if files:
                return True, stdout_text, stderr_text, files
            else:
                return (
                    False,
                    stdout_text,
                    "コマンドは成功しましたが、ファイルが見つかりませんでした",
                    [],
                )
        else:
            return (
                False,
                stdout_text,
                f"コマンド実行エラー (コード {process.returncode}): {stderr_text}",
                [],
            )

    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        print(f"実行例外: {error_details}")
        return False, "", f"yt-dlp実行例外: {str(e)}", []


# ファイルをDiscordに送信する関数
async def send_file_to_discord(interaction, file_path):
    """
    ファイルをDiscordに添付ファイルとして送信する関数
    大きすぎる場合は通知のみ送信
    """
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)

    if file_size <= MAX_FILE_SIZE:
        # ファイルサイズが制限内なら添付ファイルとして送信
        file = discord.File(file_path, filename=file_name)
        try:
            await interaction.followup.send(
                f"ダウンロードした曲をファイルとして送信します:", file=file
            )
            return True
        except Exception as e:
            print(f"ファイル送信エラー: {str(e)}")
            return False
    else:
        # ファイルサイズが大きすぎる場合は通知のみ
        size_mb = file_size / (1024 * 1024)
        await interaction.followup.send(
            f"`{file_name}` のサイズが大きすぎます({size_mb:.1f}MB)。\n"
            f"Discordの添付ファイル制限は8MBです。\n"
            f"ファイルはサーバー上の `{DOWNLOAD_DIR}` に保存されています。"
        )
        return False


@bot.event
async def on_ready():
    print(f"{bot.user} としてログインしました")
    # スラッシュコマンドを同期
    try:
        print("スラッシュコマンドを同期しています...")
        synced = await bot.tree.sync()
        print(f"{len(synced)}個のコマンドを同期しました")
    except Exception as e:
        print(f"コマンドの同期中にエラーが発生しました: {str(e)}")

    # システム情報を表示
    print(f"使用中のPython: {sys.executable} (バージョン {sys.version})")

    # spotdlの診断を実行
    print("spotdlを診断しています...")
    spotdl_diagnostics = await diagnose_spotdl()

    if spotdl_diagnostics["installed"]:
        print(f"spotdl が見つかりました: バージョン {spotdl_diagnostics['version']}")
        print(f"パス: {spotdl_diagnostics['path']}")

        # 診断情報を表示
        for method in spotdl_diagnostics["methods"]:
            print(f"- {method}")
    else:
        print(
            "警告: spotdlが見つかりませんでした。以下のコマンドでインストールしてください:"
        )
        print(f'"{PYTHON_PATH}" -m pip install spotdl')
        print("\n診断結果:")
        for method_result in spotdl_diagnostics["methods"]:
            print(f"- {method_result}")


# スラッシュコマンドの実装
@bot.tree.command(
    name="download", description="SpotifyまたはYouTubeの曲をダウンロードします"
)
@app_commands.describe(
    url="SpotifyまたはYouTubeのURL",
    send_file="ダウンロード後にファイルを送信する（大きなファイルは送信できません）",
)
async def download_slash(
    interaction: discord.Interaction, url: str, send_file: bool = True
):
    """SpotifyまたはYouTubeの曲をダウンロードするコマンド"""
    await interaction.response.defer(thinking=True)

    # 入力されたURLをデバッグ表示
    print(f"受信したURL: {url}")

    # URLの最適化（トリム、余分なクエリパラメータの削除など）
    url = url.strip()

    # URLの検証
    is_spotify = is_valid_spotify_url(url)
    is_youtube = is_youtube_url(url)

    print(f"URLの検証結果: Spotify={is_spotify}, YouTube={is_youtube}")

    if not (is_spotify or is_youtube):
        # 検証失敗時、より柔軟な判定を試みる
        if "spotify" in url.lower():
            is_spotify = True
            print("柔軟な判定でSpotify URLと判断しました")
        elif "youtube" in url.lower() or "youtu.be" in url.lower():
            is_youtube = True
            print("柔軟な判定でYouTube URLと判断しました")
        else:
            await interaction.followup.send(
                f"エラー: URLはSpotifyまたはYouTubeの形式である必要があります。\n"
                f"入力されたURL: `{url}`"
            )
            return

    # YouTubeの場合
    if is_youtube:
        await interaction.followup.send(f"YouTube動画のダウンロードを開始します...")

        # 一時ディレクトリにダウンロード
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # yt-dlpを実行
                success, stdout, stderr, downloaded_files = await run_ytdlp(
                    url, temp_dir
                )

                if not success or not downloaded_files:
                    detailed_error = f"""
エラー: yt-dlpコマンドの実行に失敗しました。

以下の対処法を試してください:
1. コマンドラインで `pip install -U yt-dlp` を実行し、最新版をインストール
2. FFmpegがインストールされていることを確認

エラー詳細:
```
{stderr[:500]}...
```
"""
                    await interaction.followup.send(detailed_error)
                    return

                # ダウンロードされたファイルのリスト
                if not downloaded_files:
                    await interaction.followup.send(
                        "ダウンロードされたファイルが見つかりませんでした。URL形式を確認してください。"
                    )
                    return

                # ダウンロードされたファイルをDOWNLOAD_DIRに移動
                for file_path in downloaded_files:
                    destination = os.path.join(DOWNLOAD_DIR, file_path.name)
                    shutil.copy2(file_path, destination)

                files_count = len(downloaded_files)
                first_file = downloaded_files[0].name

                # ファイルのダウンロード完了を通知
                await interaction.followup.send(
                    f"`{first_file}` のダウンロードが完了しました！\n"
                    f"保存先: `{DOWNLOAD_DIR}`"
                )

                # 要求があればファイルを送信
                if send_file and files_count == 1:
                    file_path = os.path.join(DOWNLOAD_DIR, first_file)
                    await send_file_to_discord(interaction, file_path)
                elif send_file and files_count > 1:
                    await interaction.followup.send(
                        f"複数のファイルがダウンロードされました。個別にダウンロードするには `/list` コマンドでファイル一覧を確認してください。"
                    )

            except Exception as e:
                import traceback

                error_details = traceback.format_exc()
                print(f"詳細なエラー情報:\n{error_details}")

                await interaction.followup.send(
                    f"エラー: ダウンロード処理中に問題が発生しました。\n```\n{str(e)}\n```"
                )
        return

    # Spotifyの場合
    spotdl_diagnostics = await diagnose_spotdl()

    if not spotdl_diagnostics["installed"]:
        error_message = "エラー: spotdlが見つかりません。\n"
        error_message += (
            "サーバー管理者に連絡し、以下のコマンドでインストールしてください:\n"
        )
        error_message += "```\npip install spotdl\n```"
        error_message += "\n診断結果:\n"
        for method_result in spotdl_diagnostics["methods"]:
            error_message += f"- {method_result}\n"
        await interaction.followup.send(error_message)
        return

    await interaction.followup.send(
        f"ダウンロードを開始します...\nspotdl v{spotdl_diagnostics['version'] or '不明'}"
    )

    # 一時ディレクトリにダウンロード - 非同期処理で実行
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            print(f"一時ディレクトリ: {temp_dir}")

            # spotdlを実行 - 引数に音楽質と出力ディレクトリと形式を明示的に指定
            args = [
                url,
                "--client-id",
                SPOTIFY_CLIENT_ID,
                "--client-secret",
                SPOTIFY_CLIENT_SECRET,
                "--output",
                temp_dir,
                "--format",
                "mp3",
                "--bitrate",
                "320k",  # ビットレートを明示的に指定
                "--print-errors",  # エラーを詳細表示
            ]

            # URLのタイプを判定して適切なオプションを追加
            url_type = get_spotify_url_type(url) if is_spotify else None
            print(f"URLのタイプ: {url_type}")

            success, stdout, stderr, downloaded_files = await run_spotdl(args, temp_dir)

            # ダウンロードに失敗した場合、より詳細な診断とリトライ
            if not success or not downloaded_files:
                # ログを詳細に出力
                print(f"ダウンロード失敗 - コマンドの出力:")
                print(f"STDOUT: {stdout}")
                print(f"STDERR: {stderr}")
                print(f"ディレクトリ内容: {os.listdir(temp_dir)}")

                # ユーザーに通知
                await interaction.followup.send(
                    "標準的なダウンロード方法に失敗しました。別の方法を試しています..."
                )

                # バックアップ方法でリトライ - 直接URLだけを渡して最小限のパラメータで実行
                backup_args = [
                    url,
                    "--output",
                    temp_dir,
                ]

                print(
                    f"バックアップ方法でリトライ: {' '.join([PYTHON_PATH, '-m', 'spotdl'] + backup_args)}"
                )
                success, stdout, stderr, downloaded_files = await run_spotdl(
                    backup_args, temp_dir
                )

                # それでも失敗した場合は、YouTube Musicで曲名を検索してダウンロードを試みる
                if not success or not downloaded_files:
                    # Spotify URLからのトラック情報を取得
                    url_type = get_spotify_url_type(url) if is_spotify else None

                    if url_type == "track" or url_type == "album":
                        await interaction.followup.send(
                            "Spotifyからのダウンロードに失敗しました。YouTube Musicで検索を試みています..."
                        )

                        # トラック名を抽出（URLの最後の部分から推測）
                        track_parts = url.split("/")[-1].split("?")[0].replace("-", " ")
                        search_query = track_parts

                        # YouTube Musicで検索
                        yt_music_url = await search_youtube_music(search_query)

                        if yt_music_url:
                            await interaction.followup.send(
                                f"YouTube Musicで類似の曲が見つかりました。ダウンロードを試みています..."
                            )

                            # yt-dlpで直接ダウンロード
                            success, stdout, stderr, downloaded_files = await run_ytdlp(
                                yt_music_url, temp_dir
                            )

                            if not success or not downloaded_files:
                                await interaction.followup.send(
                                    "バックアップ方法でのダウンロードにも失敗しました。"
                                )
                                return
                        else:
                            await interaction.followup.send(
                                "YouTube Musicでの検索に失敗しました。手動で曲名を確認して再試行してください。"
                            )
                            return
                    else:
                        detailed_error = f"""
エラー: spotdlコマンドの実行に失敗しました。

以下の対処法を試してください:
1. コマンドライン/ターミナルで `pip install spotdl --upgrade` を実行し、最新版をインストール
2. コマンドライン/ターミナルで `python -m spotdl --version` で動作確認
3. FFmpegがインストールされていることを確認
4. URL形式が正しいか確認してください

詳細情報:
URL: {url}
URLタイプ: {url_type}

エラー詳細:
```
{stderr[:500]}...
```
"""
                        await interaction.followup.send(detailed_error)
                        return

            # ダウンロードされたファイルのリスト
            if not downloaded_files:
                await interaction.followup.send(
                    "ダウンロードされたファイルが見つかりませんでした。URL形式を確認してください。"
                )
                return

            # ダウンロードされたファイルをDOWNLOAD_DIRに移動
            for file_path in downloaded_files:
                destination = os.path.join(DOWNLOAD_DIR, file_path.name)
                shutil.copy2(file_path, destination)

            files_count = len(downloaded_files)
            first_file = downloaded_files[0].name

            # ファイルのダウンロード完了を通知
            await interaction.followup.send(
                f"`{first_file}` のダウンロードが完了しました！\n"
                f"保存先: `{DOWNLOAD_DIR}`"
            )

            # 要求があればファイルを送信
            if send_file and files_count == 1:
                file_path = os.path.join(DOWNLOAD_DIR, first_file)
                await send_file_to_discord(interaction, file_path)
            elif send_file and files_count > 1:
                await interaction.followup.send(
                    f"複数のファイルがダウンロードされました。個別にダウンロードするには `/list` コマンドでファイル一覧を確認してください。"
                )

        except Exception as e:
            import traceback

            error_details = traceback.format_exc()
            print(f"詳細なエラー情報:\n{error_details}")

            await interaction.followup.send(
                f"エラー: ダウンロード処理中に問題が発生しました。\n```\n{str(e)}\n```"
            )


@bot.tree.command(
    name="playlist", description="Spotifyのプレイリスト全体をダウンロードします"
)
@app_commands.describe(url="SpotifyプレイリストのURL")
async def playlist_slash(interaction: discord.Interaction, url: str):
    """Spotifyのプレイリスト全体をダウンロードするコマンド"""
    await interaction.response.defer(thinking=True)

    # URLの検証
    if not is_valid_spotify_url(url):
        await interaction.followup.send("エラー: 有効なSpotify URLを入力してください。")
        return

    # プレイリスト以外のURLの場合は通常のダウンロードコマンドを使用するよう促す
    url_type = get_spotify_url_type(url)
    if url_type != "playlist":
        await interaction.followup.send(
            f"これは{url_type}のURLです。プレイリストではありません。\n`/download`コマンドを使用してください。"
        )
        return

    # spotdlを診断
    spotdl_diagnostics = await diagnose_spotdl()

    if not spotdl_diagnostics["installed"]:
        error_message = "エラー: spotdlが見つかりません。\n"
        error_message += (
            "サーバー管理者に連絡し、以下のコマンドでインストールしてください:\n"
        )
        error_message += "```\npip install spotdl\n```"
        await interaction.followup.send(error_message)
        return

    # プレイリスト情報を取得
    playlist_info = await get_playlist_info(url)
    if not playlist_info:
        await interaction.followup.send("プレイリスト情報を取得できませんでした。")
        return

    track_count = playlist_info["track_count"]
    title = playlist_info["title"]

    # プレイリスト情報を表示
    await interaction.followup.send(
        f"**「{title}」** をダウンロードします。\n"
        f"プレイリスト内の曲数: {track_count}曲\n"
        f"ダウンロードを開始しています..."
    )

    start_time = time.time()
    progress_message = await interaction.channel.send("プレイリストの処理中...")

    try:
        # 一時ディレクトリにダウンロード
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # spotdlを実行 (最もシンプルな方法)
                success, stdout, stderr, downloaded_files = await run_spotdl(
                    [
                        url,
                        "--client-id",
                        SPOTIFY_CLIENT_ID,
                        "--client-secret",
                        SPOTIFY_CLIENT_SECRET,
                        "--output",
                        temp_dir,
                    ],
                    temp_dir,
                )

                if not success:
                    await progress_message.edit(
                        content=(
                            "プレイリストのダウンロード中にエラーが発生しました。\n"
                            f"エラー: ```\n{stderr[:500]}...\n```"
                        )
                    )
                    return

                # ダウンロードされたファイルのリスト
                if not downloaded_files:
                    await progress_message.edit(
                        content="ダウンロードされたファイルが見つかりませんでした。"
                    )
                    return

                # ダウンロードされたファイルをDOWNLOAD_DIRに移動
                for file_path in downloaded_files:
                    destination = os.path.join(DOWNLOAD_DIR, file_path.name)
                    shutil.copy2(file_path, destination)

                # 完了メッセージ
                files_count = len(downloaded_files)
                elapsed_time = time.time() - start_time
                minutes, seconds = divmod(int(elapsed_time), 60)

                await progress_message.edit(
                    content=(
                        f"✅ **「{title}」** のダウンロードが完了しました！\n"
                        f"ダウンロードした曲数: {files_count}/{track_count} 曲\n"
                        f"所要時間: {minutes}分{seconds}秒\n"
                        f"保存先: `{DOWNLOAD_DIR}`"
                    )
                )

            except Exception as e:
                await progress_message.edit(
                    content=f"エラーが発生しました: {str(e)[:1500]}"
                )
                import traceback

                traceback.print_exc()

    except Exception as e:
        await interaction.followup.send(
            f"予期しないエラーが発生しました: {str(e)[:1500]}"
        )
        import traceback

        traceback.print_exc()


@bot.tree.command(name="list", description="ダウンロード済みの曲のリストを表示します")
@app_commands.describe(download="選択したファイルをダウンロードする")
async def list_slash(interaction: discord.Interaction, download: int = 0):
    """ダウンロード済みの曲のリストを表示、または特定のファイルをダウンロード"""
    try:
        files = list(Path(DOWNLOAD_DIR).glob("*.mp3"))

        if not files:
            await interaction.response.send_message(
                "ダウンロードされた曲はありません。"
            )
            return

        # ダウンロード引数が指定されている場合は特定のファイルを送信
        if download > 0 and download <= len(files):
            await interaction.response.defer(thinking=True)
            selected_file = files[download - 1]
            await send_file_to_discord(interaction, selected_file)
            return

        # ファイルリストの生成（最大25件まで）
        file_list = "\n".join(
            [f"{idx + 1}. {file.name}" for idx, file in enumerate(files[:25])]
        )

        if len(files) > 25:
            file_list += f"\n\n...他 {len(files) - 25} 件"

        await interaction.response.send_message(
            f"**ダウンロード済みの曲リスト**\n"
            f"特定のファイルをダウンロードするには `/list download:番号` を使用してください。\n"
            f"```\n{file_list}\n```"
        )

    except Exception as e:
        await interaction.response.send_message(f"エラーが発生しました: {str(e)}")


@bot.tree.command(name="settings", description="ダウンロード設定を表示・変更します")
async def settings_slash(interaction: discord.Interaction):
    """ダウンロード設定を表示する"""
    settings_text = f"""
**現在の設定:**
ダウンロードディレクトリ: `{DOWNLOAD_DIR}`
ダウンロードしたファイルはボットが動作しているサーバーに保存されます。

**ファイルの取得方法:**
1. 8MB以下のファイルは自動的にDiscordに添付ファイルとして送信されます
2. より大きなファイルはサーバー上に保存され、`/list`コマンドで確認できます
"""
    await interaction.response.send_message(settings_text)


@bot.tree.command(
    name="help_music", description="音楽ダウンロードコマンドのヘルプを表示します"
)
async def help_music_slash(interaction: discord.Interaction):
    """コマンドの使い方を表示"""
    help_text = """
**使用可能なコマンド:**
`/download [URL] (send_file:True/False)` - Spotify/YouTube URLからダウンロード。send_fileをTrueにするとファイルも送信
`/playlist [Spotify URL]` - プレイリスト全体をダウンロードします
`/list (download:番号)` - ダウンロード済みの曲リストを表示。番号を指定するとそのファイルをダウンロードできます
`/settings` - 現在の設定とファイル取得方法を表示します
`/help_music` - このヘルプメッセージを表示します

**注意点:**
- ダウンロードファイルはボットが動作しているサーバーに保存されます
- 8MB以下のファイルはDiscordに直接送信できます
- それ以上のサイズはDiscordの制限により送信できません
    """
    await interaction.response.send_message(help_text)


# Botの実行
bot.run(TOKEN)
