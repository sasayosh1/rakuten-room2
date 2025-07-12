# 楽天ROOM自動化システム（クリーン版）

シンプルで効率的な楽天ROOM自動化システムです。

## 🌟 特徴

- **シンプル構成**: 必要最小限の3ファイル
- **API最小化**: 楽天API呼び出しを従来の半分に削減（16→8キーワード）
- **フォールバック機能**: API→スクレイピング→ダミーデータの3段階対応
- **安全設計**: 投稿数制限と適切な間隔
- **自動重複除去**: 既存データとの重複チェック
- **GitHub Actions対応**: クラウド自動実行

## 📁 プロジェクト構造

```
rakuten-room2/
├── src/
│   ├── collector_optimized.py  # 商品データ収集（API最小化版）
│   ├── poster.py              # 楽天ROOM投稿
│   └── main.py               # メインスクリプト
├── scripts/
│   ├── setup.sh         # セットアップ
│   └── run.sh           # ローカル実行
├── .github/workflows/
│   └── automation.yml   # GitHub Actions
├── requirements.txt     # 依存関係
└── README.md           # このファイル
```

## 🚀 クイックスタート

### ローカル環境

```bash
# セットアップ
./scripts/setup.sh

# .envファイルに認証情報を入力
# 実行
./scripts/run.sh
```

### GitHub Actions

1. **リポジトリSecretsに以下を設定**:
   - `RAKUTEN_APP_ID`: 楽天APIキー（省略可能 - スクレイピングモードで動作）
   - `ROOM_EMAIL`: 楽天ROOMメール
   - `ROOM_PASSWORD`: 楽天ROOMパスワード
   - `GSPREAD_KEY`: Google SheetsのスプレッドシートID
   - `GSA_JSON_B64`: Service AccountのJSONキー（Base64エンコード）

2. **手動実行**:
   - Actions → "楽天ROOM自動化" → "Run workflow"
   - モード選択: `collect`（収集のみ）/ `post`（投稿のみ）/ `full`（完全）

3. **自動実行**:
   - 毎日午前10時（JST）に商品収集モードで自動実行

## ⚙️ 実行モード

### 商品データ収集のみ
```bash
python3 src/main.py --mode collect --products 3
```

### 楽天ROOM投稿のみ
```bash
python3 src/main.py --mode post --max-posts 2
```

### 完全自動化
```bash
python3 src/main.py --mode full --products 2 --max-posts 2
```

## 📊 収集対象

年代別の美容商品キーワード（API最小化版）:

- **20代**: ニキビケア、保湿クリーム（2キーワード）
- **30代**: 大人ニキビ、エイジングケア（2キーワード）
- **40代**: 毛穴ケア、美白ケア（2キーワード）
- **50代**: 保湿ケア、たるみケア（2キーワード）

**合計8キーワード** （従来の16から半減してAPI使用量を最小化）

## 🛡️ 安全機能

- **投稿制限**: 1日最大3件
- **投稿間隔**: 5-10分の自動調整
- **重複除去**: URL重複の自動チェック
- **エラーハンドリング**: 堅牢なエラー処理

## 📋 Google Sheetsフォーマット

各年代ごとにシートが作成され、以下の列を含みます:

| 列名 | 内容 |
|------|------|
| 商品名 | 商品タイトル |
| 商品URL | 楽天市場の商品ページURL |
| 価格 | 商品価格 |
| ショップ名 | 販売店名 |
| 評価 | 商品評価 |
| レビュー数 | レビュー件数 |
| 紹介文 | 自動生成された投稿用テキスト |
| 画像URL | 商品画像URL |
| 更新日時 | データ収集日時 |

## 🔧 設定

### 投稿数制限の変更
`src/poster.py`の`daily_limit`を変更:
```python
self.daily_limit = 3  # 1日最大投稿数
```

### 検索キーワードの追加
`src/collector_optimized.py`の`KEYWORDS`辞書を編集:
```python
KEYWORDS = {
    "20代": ["ニキビケア", "保湿クリーム"],
    "30代": ["大人ニキビ", "エイジングケア"],
    ...
}
```

### API使用の有効/無効
楽天APIキー（`RAKUTEN_APP_ID`）が設定されていない場合、自動的にスクレイピングモードに切り替わります。

## 🔒 セキュリティ

- `.env`ファイルは`.gitignore`に含まれます
- GitHub SecretsでCredentialを安全に管理
- 最小権限でのAPI利用

## 📈 推奨使用方法

1. **初回**: `collect`モードで商品データ収集
2. **確認**: Google Sheetsでデータ確認
3. **投稿**: `post`モードで少数投稿テスト
4. **運用**: `full`モードで定期実行

## 🐛 トラブルシューティング

### 環境変数エラー
```bash
# 環境変数の確認
source .env && env | grep -E "(ROOM_|GSPREAD_|RAKUTEN_)"
```

### Google Sheets接続エラー
- Service Accountでスプレッドシートが共有されているか確認
- Base64エンコードが正しいか確認

### 楽天ROOMログインエラー
- 2要素認証が無効になっているか確認
- メール・パスワードが正しいか確認

## ⚠️ 注意事項

- 楽天ROOMの利用規約を遵守してください
- 1日の投稿数は3件以下に制限してください
- 認証情報を公開しないでください

---

**このツールは教育・研究目的で作成されています。楽天の利用規約を遵守して使用してください。**