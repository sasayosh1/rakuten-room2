#!/bin/bash
# 実行スクリプト

echo "🚀 楽天ROOM自動化システム"
echo "========================="

# .envファイルの読み込み
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ .envファイルを読み込みました"
else
    echo "❌ .envファイルが見つかりません"
    echo "setup.shを実行してください"
    exit 1
fi

echo ""
echo "実行モードを選択してください:"
echo "1) 商品データ収集のみ"
echo "2) 楽天ROOM投稿のみ"
echo "3) 完全自動化（収集 + 投稿）"
echo ""

read -p "選択 (1-3): " choice

case $choice in
    1)
        echo "📊 商品データ収集を開始..."
        python3 src/main.py --mode collect --products 3
        ;;
    2)
        echo "📝 楽天ROOM投稿を開始..."
        python3 src/main.py --mode post --max-posts 2
        ;;
    3)
        echo "🚀 完全自動化を開始..."
        python3 src/main.py --mode full --products 2 --max-posts 2
        ;;
    *)
        echo "❌ 無効な選択です"
        exit 1
        ;;
esac

echo ""
echo "✅ 実行完了"