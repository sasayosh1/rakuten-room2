#!/bin/bash
# セットアップスクリプト

echo "🚀 楽天ROOM自動化システム セットアップ"
echo "======================================="

# Python依存関係のインストール
echo "📦 依存パッケージをインストール中..."
pip install -r requirements.txt

# Playwrightブラウザのインストール
echo "🌐 Playwrightブラウザをインストール中..."
playwright install chromium --with-deps

# 環境変数ファイルのサンプル作成
if [ ! -f .env ]; then
    echo "📄 .envファイルのサンプルを作成中..."
    cat > .env << 'EOF'
# 楽天API設定
RAKUTEN_APP_ID=your_rakuten_app_id

# 楽天ROOM認証情報
ROOM_EMAIL=your_email@example.com
ROOM_PASSWORD=your_password

# Google Sheets設定
GSPREAD_KEY=your_google_sheets_key
GSA_JSON_B64=your_base64_encoded_service_account_json
EOF
    echo "✅ .envファイルを作成しました"
    echo "⚠️  .envファイルに必要な情報を入力してください"
else
    echo "✅ .envファイルが既に存在します"
fi

# 実行権限付与
chmod +x scripts/*.sh
chmod +x src/*.py

echo ""
echo "🎉 セットアップ完了！"
echo ""
echo "次のステップ:"
echo "1. .envファイルに認証情報を入力"
echo "2. ./scripts/run.sh でシステムを実行"