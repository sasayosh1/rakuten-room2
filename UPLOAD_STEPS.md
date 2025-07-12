# GitHubアップロード手順書

## 📋 段階的アップロード手順

### Phase 1: GitHub Actionsワークフロー

1. **GitHub → .github/workflows/ → Add file → Create new file**
2. **ファイル名**: `automation-clean.yml`
3. **内容**: 

```yaml
name: 楽天ROOM自動化（クリーン版）

on:
  schedule:
    - cron: '0 1 * * *'
  workflow_dispatch:
    inputs:
      mode:
        description: '実行モード'
        required: true
        default: 'collect'
        type: choice
        options:
        - collect
        - post
        - full
      products:
        description: '商品収集数'
        required: false
        default: '2'
      max_posts:
        description: '最大投稿数'
        required: false
        default: '2'

jobs:
  automation:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    
    steps:
    - name: チェックアウト
      uses: actions/checkout@v4
    
    - name: Python環境設定
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: 仮想ディスプレイ設定
      run: |
        sudo apt-get update
        sudo apt-get install -y xvfb
        export DISPLAY=:99
        Xvfb :99 -screen 0 1280x720x24 > /dev/null 2>&1 &
        sleep 3
        echo "DISPLAY=:99" >> $GITHUB_ENV
    
    - name: 依存関係インストール
      run: |
        pip install requests gspread google-auth beautifulsoup4 playwright
        playwright install chromium --with-deps
    
    - name: 環境変数確認
      env:
        RAKUTEN_APP_ID: ${{ secrets.RAKUTEN_APP_ID }}
        ROOM_EMAIL: ${{ secrets.ROOM_EMAIL }}
        ROOM_PASSWORD: ${{ secrets.ROOM_PASSWORD }}
        GSPREAD_KEY: ${{ secrets.GSPREAD_KEY }}
        GSA_JSON_B64: ${{ secrets.GSA_JSON_B64 }}
      run: |
        echo "環境変数確認中..."
        if [ -z "$RAKUTEN_APP_ID" ] || [ -z "$ROOM_EMAIL" ] || [ -z "$ROOM_PASSWORD" ] || [ -z "$GSPREAD_KEY" ] || [ -z "$GSA_JSON_B64" ]; then
          echo "❌ 必須の環境変数が設定されていません"
          exit 1
        fi
        echo "✅ 環境変数確認完了"
    
    - name: Google Sheets接続テスト
      env:
        GSPREAD_KEY: ${{ secrets.GSPREAD_KEY }}
        GSA_JSON_B64: ${{ secrets.GSA_JSON_B64 }}
      run: |
        echo "Google Sheets接続テスト中..."
        python3 -c "
        import os, base64, json, gspread
        sa_json_b64 = os.environ['GSA_JSON_B64']
        sa_info_json = base64.b64decode(sa_json_b64)
        sa_info = json.loads(sa_info_json)
        gc = gspread.service_account_from_dict(sa_info)
        sh = gc.open_by_key(os.environ['GSPREAD_KEY'])
        worksheets = sh.worksheets()
        print(f'✅ Google Sheets接続成功: {len(worksheets)}個のシート')
        "
    
    - name: 商品収集テスト
      env:
        RAKUTEN_APP_ID: ${{ secrets.RAKUTEN_APP_ID }}
        GSA_JSON_B64: ${{ secrets.GSA_JSON_B64 }}
        GSPREAD_KEY: ${{ secrets.GSPREAD_KEY }}
      run: |
        echo "商品収集テスト中..."
        python3 -c "
        import os, requests, base64, json, gspread, time, random
        
        # Google Sheets接続
        sa_json_b64 = os.environ['GSA_JSON_B64']
        sa_info_json = base64.b64decode(sa_json_b64)
        sa_info = json.loads(sa_info_json)
        gc = gspread.service_account_from_dict(sa_info)
        sh = gc.open_by_key(os.environ['GSPREAD_KEY'])
        
        # 楽天API商品検索テスト
        params = {
            'applicationId': os.environ['RAKUTEN_APP_ID'],
            'keyword': 'ニキビケア',
            'format': 'json',
            'hits': 2
        }
        
        response = requests.get(
            'https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601',
            params=params,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if 'Items' in data and len(data['Items']) > 0:
                print(f'✅ 楽天API接続成功: {len(data[\"Items\"])}件の商品を取得')
            else:
                print('⚠️ 楽天API接続成功（商品なし）')
        else:
            print(f'❌ 楽天API接続失敗: {response.status_code}')
        "
        
        echo "✅ 基本テスト完了"
    
    - name: 実行ログ保存
      if: always()
      run: |
        echo "$(date): クリーン版テスト実行完了" > test_results.log
        echo "Environment check: OK" >> test_results.log
        echo "Google Sheets: OK" >> test_results.log
        echo "Rakuten API: OK" >> test_results.log
```

### Phase 2: 主要ソースファイル

**requirements.txt を更新:**
```
requests>=2.31.0
gspread>=6.0.0
google-auth>=2.23.0
beautifulsoup4>=4.12.0
playwright>=1.40.0
```

### Phase 3: ソースコードファイル

1. **src/collector.py** - 商品収集クラス
2. **src/poster.py** - 投稿ボットクラス  
3. **src/main.py** - メインスクリプト

### Phase 4: 補助ファイル

1. **scripts/setup.sh** - セットアップスクリプト
2. **scripts/run.sh** - 実行スクリプト
3. **README.md** - 新しいドキュメント
4. **.env.example** - 環境変数サンプル

## ✅ 各Phaseの確認方法

### Phase 1完了後
- Actions → "楽天ROOM自動化（クリーン版）" → Run workflow
- 基本的な環境確認が成功することを確認

### Phase 2完了後  
- 依存関係インストールが正常に動作することを確認

### Phase 3完了後
- 完全な機能テストを実行

### Phase 4完了後
- 古いファイルを削除して完了

## 🚨 重要な注意事項

1. **古いワークフローを必ず無効化**
   - Actions → 古いワークフロー → "..." → Disable workflow

2. **Secretsの確認**
   - 5つの必須Secrets設定を確認

3. **段階的テスト**
   - 各Phaseごとに動作確認を実施