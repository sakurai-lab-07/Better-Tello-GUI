# Tello プレビュー拡張機能 - ブロック実装ガイド

## 実装完了したブロック一覧

### ✅ ステージ関連
- **setStageSize** (`preview_setStageSize`)
  - ステージの横幅と高さを指定した値に変更し、そのサイズを保存
  - 入力: WIDTH (横幅), HEIGHT (高さ)
  - 実装位置: scratch_parser.py `_traverse_blocks()`内

- **getStageWidth** - 別途実装が必要（レポーター型ブロック）
  - 現在のステージの横幅を返す

- **getStageHeight** - 別途実装が必要（レポーター型ブロック）
  - 現在のステージの高さを返す

---

### ✅ 座標取得
- **getX** - 別途実装が必要（レポーター型ブロック）
  - アクティブなスプライトの現在の X 座標を返す
  - show_runner.py の `sprite_positions` 辞書から取得

- **getY** - 別途実装が必要（レポーター型ブロック）
  - アクティブなスプライトの現在の Y 座標を返す
  - show_runner.py の `sprite_positions` 辞書から取得

---

### ✅ 原点（オフセット）関連
- **setOriginHere** (`preview_setOriginHere`)
  - 原点（基準位置）をスプライトの現在位置に設定
  - 実装位置: scratch_parser.py `_traverse_blocks()`内
  - 状態管理: `self.origin_offset[sprite_name] = (px, py)`

- **setOriginXY** (`preview_setOriginXY`)
  - 原点（基準位置）を指定した X と Y に設定
  - 入力: X, Y
  - 実装位置: scratch_parser.py `_traverse_blocks()`内

- **clearOrigin** (`preview_clearOrigin`)
  - 設定されている原点（オフセット）を削除
  - 実装位置: scratch_parser.py `_traverse_blocks()`内
  - 状態管理: `self.origin_offset[sprite_name] = None`

- **getLocalX** - 別途実装が必要（レポーター型ブロック）
  - スプライトの現在位置が原点からどれだけ X 方向に離れているかを返す
  - 計算: `現在位置X - 原点X`

- **getLocalY** - 別途実装が必要（レポーター型ブロック）
  - スプライトの現在位置が原点からどれだけ Y 方向に離れているかを返す
  - 計算: `現在位置Y - 原点Y`

- **moveToLocal** (`preview_moveToLocal`)
  - 原点を基準として指定されたローカル座標（LX, LY）にスプライトを移動
  - 入力: LX, LY
  - 実装位置: scratch_parser.py `_traverse_blocks()`内
  - 処理: 原点 + ローカル座標 = 絶対座標に変換して移動

---

### ✅ 移動・回転・サイズ操作

- **turnRight** (`preview_turnRight`)
  - スプライトを指定した角度だけ右回転させる
  - 入力: DEGREES
  - 実装位置: scratch_parser.py `_traverse_blocks()`内
  - コマンド: `cw {角度}`

- **turnLeft** (`preview_turnLeft`)
  - スプライトを指定した角度だけ左回転させる
  - 入力: DEGREES
  - 実装位置: scratch_parser.py `_traverse_blocks()`内
  - コマンド: `ccw {角度}`

- **moveBy** (`preview_moveBy`)
  - スプライトを現在位置から X と Y の指定量だけ移動させる
  - 入力: DX, DY
  - 実装位置: scratch_parser.py `_traverse_blocks()`内
  - 処理: 水平移動（DX）と垂直移動（DY）を別々に処理

- **moveXBy** (`preview_moveXBy`)
  - スプライトを X 方向に指定量だけ移動させる
  - 入力: DX
  - 実装位置: scratch_parser.py `_traverse_blocks()`内
  - コマンド: `left/right {距離}`

- **moveYBy** (`preview_moveYBy`)
  - スプライトを Y 方向に指定量だけ移動させる
  - 入力: DY
  - 実装位置: scratch_parser.py `_traverse_blocks()`内
  - コマンド: `forward/back {距離}`

- **changeSizeBy** (`preview_changeSizeBy`)
  - スプライトの大きさを指定量だけ相対的に変化させる
  - 入力: CHANGE
  - 実装位置: scratch_parser.py `_traverse_blocks()`内
  - コマンド: `up/down {距離}`（高度変更）

- **setSizeTo** (`preview_setSizeTo`)
  - スプライトの大きさを指定サイズに設定する
  - 入力: SIZE
  - 実装位置: scratch_parser.py `_traverse_blocks()`内
  - コマンド: `up/down {距離}`（高度変更）

---

## 状態管理の詳細

### scratch_parser.py (パース時)
```python
self.stage_width = 480           # ステージ幅
self.stage_height = 360          # ステージ高さ
self.origin_offset = {}          # {sprite_name: (x, y) or None}
```

### show_runner.py (実行時)
```python
self.sprite_positions = {}       # {sprite_name: (x, y, z)}
self.stage_size = {              # ステージサイズ
    "width": 480,
    "height": 360
}
self.origin_offsets = {}         # {sprite_name: (ox, oy) or None}
```

---

## レポーター型ブロック（getX, getY等）の実装方法

これらのブロックは値を返す型なので、以下の修正が必要です：

1. **scratch_parser.py** の `_get_input_value()` メソッドに処理を追加
2. ブロックのopcode（例：`preview_getX`）を認識して、該当する値を返す
3. 座標情報に基づいて計算結果を返す

### 実装例（疑似コード）
```python
elif input_type == 3 and isinstance(input_value, list):
    if input_value[0] == 12:  # レポーター型
        opcode = input_value[1]
        if opcode == "preview_getX":
            # スプライトの現在のX座標を返す
            return sprite_positions.get(current_sprite, (0, 0, 80))[0]
        elif opcode == "preview_getY":
            # スプライトの現在のY座標を返す
            return sprite_positions.get(current_sprite, (0, 0, 80))[1]
        # ... 他のレポーター処理
```

---

## テスト方法

1. Scratch で新規拡張ブロックを使用したプロジェクトを作成
2. 各ブロックのopcode（`preview_*`）がScratchプロジェクトJSONに正しく記録されていることを確認
3. `scratch_parser.py` で正しく解析されているかログで確認
4. タイムラインが正しく生成されているか確認
5. 実際のドローン実行で位置が正しく更新されているか確認

---

## 既知の制限事項

- **Z軸（高度）** の初期値は `INITIAL_HOVER_HEIGHT_CM` (80cm) で固定
- **座標系** は Scratch 座標系 (中心が原点) ではなく、相対座標で管理
- レポーター型ブロック（getX, getY等）はまだ値を返すロジックが未実装

---

## 実装の進捗状況

| ブロック | パース | 実行 | レポート | 状態 |
|---------|-------|------|---------|------|
| setStageSize | ✅ | ❌ | N/A | パース完了 |
| getStageWidth | ❌ | ❌ | ❌ | 未実装 |
| getStageHeight | ❌ | ❌ | ❌ | 未実装 |
| getX | ❌ | ✅ | ❌ | 部分実装 |
| getY | ❌ | ✅ | ❌ | 部分実装 |
| setOriginHere | ✅ | N/A | N/A | 完了 |
| setOriginXY | ✅ | N/A | N/A | 完了 |
| clearOrigin | ✅ | N/A | N/A | 完了 |
| getLocalX | ❌ | ✅ | ❌ | 部分実装 |
| getLocalY | ❌ | ✅ | ❌ | 部分実装 |
| moveToLocal | ✅ | ✅ | N/A | 完了 |
| turnRight | ✅ | ✅ | N/A | 完了 |
| turnLeft | ✅ | ✅ | N/A | 完了 |
| moveBy | ✅ | ✅ | N/A | 完了 |
| moveXBy | ✅ | ✅ | N/A | 完了 |
| moveYBy | ✅ | ✅ | N/A | 完了 |
| changeSizeBy | ✅ | ✅ | N/A | 完了 |
| setSizeTo | ✅ | ✅ | N/A | 完了 |
