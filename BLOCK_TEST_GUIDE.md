# テスト用：新規ブロック検証スクリプト

これはサンプルスクリプトで、Scratchプロジェクト内での新規ブロック使用例を示します。

## 期待されるブロックのopcode名

### アクション型ブロック（コマンド実行）
- `preview_setStageSize` → 入力: WIDTH, HEIGHT
- `preview_setOriginHere` → 入力: なし
- `preview_setOriginXY` → 入力: X, Y
- `preview_clearOrigin` → 入力: なし
- `preview_turnRight` → 入力: DEGREES
- `preview_turnLeft` → 入力: DEGREES
- `preview_moveBy` → 入力: DX, DY
- `preview_moveXBy` → 入力: DX
- `preview_moveYBy` → 入力: DY
- `preview_moveToLocal` → 入力: LX, LY
- `preview_changeSizeBy` → 入力: CHANGE
- `preview_setSizeTo` → 入力: SIZE

### レポーター型ブロック（値返却）
- `preview_getStageWidth` → 出力: 数値
- `preview_getStageHeight` → 出力: 数値
- `preview_getX` → 出力: 数値
- `preview_getY` → 出力: 数値
- `preview_getLocalX` → 出力: 数値
- `preview_getLocalY` → 出力: 数値

## テスト実行例

### Test 1: ステージサイズ設定
```
setStageSize width: 640 height: 480
```
期待動作: ステージサイズが 640x480 に変更される

### Test 2: 原点設定と相対移動
```
setOriginHere
moveToLocal LX: 100 LY: 50
```
期待動作: 原点が現在位置に設定され、その相対位置 (100, 50) に移動

### Test 3: 座標取得
```
[変数] x を [getX] に設定する
[変数] y を [getY] に設定する
```
期待動作: 変数に現在のスプライト座標が格納される

### Test 4: ローカル座標取得
```
setOriginXY X: 0 Y: 0
[変数] localX を [getLocalX] に設定する
[変数] localY を [getLocalY] に設定する
```
期待動作: ローカル座標が正しく取得される

## デバッグ方法

1. Scratchプロジェクトを `.sb3` ファイルで保存
2. 7-Zipなどで解凍して `project.json` を確認
3. 各ブロックのopcode が正しく `preview_*` 形式になっているか確認
4. parser.pyのログで `preview_*` opcode が検出されているか確認
5. 生成されたスケジュール（timeline）で正しくコマンドに変換されているか確認
