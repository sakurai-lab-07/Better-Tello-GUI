# Better Tello GUI 🚁

Scratchプロジェクトから生成されたタイムラインに基づいてTelloドローンのショーを制御するGUIアプリケーションです。

![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)
![License](https://img.shields.io/badge/License-Educational-green.svg)

## ✨ 主な機能

### 🎮 ドローン制御
- 複数のTelloドローンを同時制御
- Scratchプロジェクト（.sb3）からタイムラインを自動生成
- 緊急停止機能

### 🎵 音楽機能
- **メドレー再生**: 複数の音楽ファイルを連続再生
- **YouTube対応**: YouTube URLから直接音源を取得・再生
- **曲間インターバル**: 曲と曲の間の待機時間を設定可能
- 対応形式: MP3, WAV, OGG, FLAC

### 📊 タイムラインビューアー
- 動画編集ソフトのようなタイムライン表示
- **波形表示**: 音楽ファイルの波形をリアルタイム表示
- **コマンド色分け**:
  - 🔵 青: 左右移動 (left/right)
  - 🟣 紫: 上下移動 (up/down)
  - 🟠 オレンジ: 前後移動 (forward/back)
  - 🩷 ピンク: 回転 (cw/ccw)
  - 🩵 シアン: フリップ (flip)
- ズーム機能、スクロール対応

### 💾 プロジェクト管理
- プロジェクトの保存・読み込み（.telloproject形式）
- ドローン設定、音楽リスト、YouTube情報を一括保存

## 📁 プロジェクト構造

```
src/
├── main.py                    # アプリケーションエントリーポイント
├── config.py                  # 設定管理（定数、色、フォント等）
├── tello_controller.py        # Telloドローン制御クラス
├── scratch_parser.py          # Scratchプロジェクト解析クラス
├── show_runner.py             # ドローンショー実行ロジック
├── music_player.py            # 音楽プレイヤーモジュール
├── project_manager.py         # プロジェクト保存・読み込み
├── youtube_downloader.py      # YouTube音源ダウンロード
├── debug_parser.py            # デバッグ用パーサー
└── gui/
    ├── __init__.py
    ├── main_window.py         # メインウィンドウ
    ├── music_manager_window.py # 音楽管理ウィンドウ
    └── timeline_viewer_window.py # タイムラインビューアー
```

## 🚀 インストール・実行方法

### 必要環境
- Python 3.7以上
- Windows / macOS / Linux

### インストール

```bash
# リポジトリをクローン
git clone https://github.com/sakurai-lab-07/Better-Tello-GUI.git
cd Better-Tello-GUI

# 依存関係をインストール
pip install pygame yt-dlp pydub numpy
```

### 実行

```bash
cd src
python main.py
```

## 📦 依存関係

| パッケージ | 用途 | 必須 |
|-----------|------|------|
| pygame | 音楽再生 | ✅ |
| yt-dlp | YouTube音源取得 | ⭕ オプション |
| pydub | 波形データ抽出 | ⭕ オプション |
| numpy | 波形データ処理 | ⭕ オプション |

```bash
# 最小インストール（音楽再生のみ）
pip install pygame

# フルインストール（YouTube対応・波形表示）
pip install pygame yt-dlp pydub numpy
```

## 🎯 使い方

### 1. ドローン設定
1. メインウィンドウでドローンを追加
2. 各ドローンのIPアドレスを設定
3. 設定を保存

### 2. プロジェクト読み込み
1. 「プロジェクト選択」からScratchファイル（.sb3）を選択
2. 「解析」ボタンでタイムラインを生成
3. タイムラインビューアーで確認

### 3. 音楽設定
1. 「🎵 音楽管理」ボタンをクリック
2. 音楽ファイルを追加（ローカルファイルまたはYouTube URL）
3. 再生順序を調整
4. インターバル時間を設定

### 4. ショー実行
1. 「接続」ボタンでドローンに接続
2. 「開始」ボタンでショーを開始
3. 必要に応じて「緊急停止」ボタンで停止

## 🎨 スクリーンショット

### メインウィンドウ
- ドローン設定パネル
- プロジェクト選択・解析パネル
- ショー制御パネル
- リアルタイムログ表示

### タイムラインビューアー
- 音楽トラック（波形表示付き）
- ドローントラック（コマンド色分け）
- 離陸トラック（最下部）
- ズーム・スクロール機能

## 🛠️ トラブルシューティング

### ドローンに接続できない
- ドローンのWi-Fiに接続しているか確認
- IPアドレスが正しいか確認
- ファイアウォールの設定を確認

### 音楽が再生されない
- pygameがインストールされているか確認
- 音楽ファイルの形式を確認（MP3, WAV, OGG, FLAC）

### YouTube音源が取得できない
- yt-dlpがインストールされているか確認
- インターネット接続を確認
- URLが正しいYouTube URLか確認

### 波形が表示されない
- pydubとnumpyがインストールされているか確認
- 音楽ファイルが正しく読み込まれているか確認

## 📝 開発

### 新機能の追加
1. 該当するモジュールを特定
2. 必要に応じて新しいモジュールを作成
3. `config.py`に設定を追加
4. GUIモジュールにUI要素を追加

### コード規約
- PEP 8準拠
- docstringによるドキュメント
- 型ヒントの使用推奨

## 📄 ライセンス

このプロジェクトは教育目的で作成されています。

## 🤝 貢献

改善提案やバグレポートは歓迎します。Issue や Pull Request をお気軽にどうぞ。

## 📞 サポート

問題が発生した場合は、以下を確認してください：
1. Python バージョン（3.7+）
2. 必要なライブラリのインストール
3. ドローンのIPアドレス設定
4. Scratchプロジェクトの形式
