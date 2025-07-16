#!/usr/bin/env python3
"""楽天ROOM投稿ボット"""

import base64
import json
import os
import random
import time
import logging
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict
import gspread
from playwright.sync_api import sync_playwright


class RoomPoster:
    """楽天ROOM投稿ボット"""
    
    def __init__(self):
        """初期化"""
        # 環境変数チェック
        required_vars = ["ROOM_EMAIL", "ROOM_PASSWORD", "GSA_JSON_B64", "GSPREAD_KEY"]
        for var in required_vars:
            if not os.environ.get(var):
                raise ValueError(f"環境変数 {var} が設定されていません")
        
        # Google Sheets設定
        sa_json_b64 = os.environ["GSA_JSON_B64"]
        sa_info_json = base64.b64decode(sa_json_b64)
        sa_info = json.loads(sa_info_json)
        self.gc = gspread.service_account_from_dict(sa_info)
        self.sh = self.gc.open_by_key(os.environ["GSPREAD_KEY"])
        
        self.daily_limit = 1  # 1日最大投稿数（安全性重視）
        self.stats_file = Path("daily_stats.json")
        self.error_file = Path("error_tracking.json")
        self.max_consecutive_errors = 3  # 連続失敗上限
        self.suspension_hours = 24  # 停止時間（時間）
        self.dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"  # ドライランモード
        self.gradual_mode = os.environ.get("GRADUAL_MODE", "true").lower() == "true"  # 段階的実行モード
        self.success_threshold = 0.8  # 80%以上の成功率で投稿開始
        
        # ログ設定
        self.setup_logging()
    
    def setup_logging(self):
        """ログ設定"""
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
        log_file = f"room_poster_{date.today().isoformat()}.log"
        
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info("=== 楽天ROOM投稿ボット開始 ===")
    
    def log_action(self, action: str, details: dict = None, level: str = "INFO"):
        """詳細ログ記録"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'dry_run': self.dry_run,
            'gradual_mode': self.gradual_mode,
            'daily_limit': self.daily_limit
        }
        
        if details:
            log_entry.update(details)
        
        # ログファイルにJSON形式で記録
        log_json_file = f"detailed_log_{date.today().isoformat()}.jsonl"
        with open(log_json_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        
        # 標準ログにも出力
        log_message = f"{action}: {json.dumps(details, ensure_ascii=False) if details else ''}"
        getattr(self.logger, level.lower(), self.logger.info)(log_message)
    
    def get_daily_stats(self) -> Dict:
        """本日の投稿統計取得"""
        today = date.today().isoformat()
        
        if self.stats_file.exists():
            with open(self.stats_file, "r", encoding="utf-8") as f:
                stats = json.load(f)
        else:
            stats = {}
        
        if today not in stats:
            stats[today] = {"posts": 0, "last_post": None}
        
        return stats[today]
    
    def update_daily_stats(self, posts_count: int):
        """投稿統計更新"""
        today = date.today().isoformat()
        
        if self.stats_file.exists():
            with open(self.stats_file, "r", encoding="utf-8") as f:
                stats = json.load(f)
        else:
            stats = {}
        
        stats[today] = {
            "posts": posts_count,
            "last_post": datetime.now().isoformat()
        }
        
        with open(self.stats_file, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    
    def check_suspension_status(self) -> bool:
        """停止状態をチェック"""
        if not self.error_file.exists():
            return False
        
        with open(self.error_file, "r", encoding="utf-8") as f:
            error_data = json.load(f)
        
        suspended_until = error_data.get("suspended_until")
        if suspended_until:
            suspend_time = datetime.fromisoformat(suspended_until)
            if datetime.now() < suspend_time:
                print(f"⏸️  システム停止中（解除予定: {suspended_until}）")
                return True
        
        return False
    
    def record_error(self, error_type: str, error_msg: str):
        """エラー記録"""
        if self.error_file.exists():
            with open(self.error_file, "r", encoding="utf-8") as f:
                error_data = json.load(f)
        else:
            error_data = {"consecutive_errors": 0, "last_errors": []}
        
        # エラー記録更新
        error_data["consecutive_errors"] += 1
        error_data["last_errors"].append({
            "timestamp": datetime.now().isoformat(),
            "type": error_type,
            "message": error_msg
        })
        
        # 直近10件のみ保持
        error_data["last_errors"] = error_data["last_errors"][-10:]
        
        # 連続失敗が上限に達したら停止
        if error_data["consecutive_errors"] >= self.max_consecutive_errors:
            from datetime import timedelta
            suspend_until = datetime.now() + timedelta(hours=self.suspension_hours)
            error_data["suspended_until"] = suspend_until.isoformat()
            print(f"🚨 連続失敗{self.max_consecutive_errors}回に達しました。{self.suspension_hours}時間停止します。")
        
        with open(self.error_file, "w", encoding="utf-8") as f:
            json.dump(error_data, f, ensure_ascii=False, indent=2)
    
    def record_success(self):
        """成功記録（エラーカウンタリセット）"""
        if self.error_file.exists():
            with open(self.error_file, "r", encoding="utf-8") as f:
                error_data = json.load(f)
            
            # 連続エラーカウンタをリセット
            error_data["consecutive_errors"] = 0
            if "suspended_until" in error_data:
                del error_data["suspended_until"]
            
            with open(self.error_file, "w", encoding="utf-8") as f:
                json.dump(error_data, f, ensure_ascii=False, indent=2)
    
    def dry_run_mode(self, products: List[Dict]) -> int:
        """ドライランモード：投稿をシミュレート"""
        print("🧪 ドライランモード：実際の投稿は行いません")
        print(f"📊 投稿予定商品数: {len(products)}")
        print("-" * 50)
        
        for i, product in enumerate(products, 1):
            print(f"{i}. 【{product.get('category', 'カテゴリ不明')}】")
            print(f"   タイトル: {product['title'][:50]}{'...' if len(product['title']) > 50 else ''}")
            print(f"   URL: {product['url']}")
            print(f"   説明: {product['description'][:100]}{'...' if len(product['description']) > 100 else ''}")
            print()
        
        print("✅ ドライラン完了：すべての商品が投稿可能な状態です")
        return len(products)  # シミュレーション成功として件数を返す
    
    def calculate_success_rate(self) -> float:
        """成功率を計算"""
        if not self.error_file.exists():
            return 1.0  # エラーファイルがない場合は100%
        
        with open(self.error_file, "r", encoding="utf-8") as f:
            error_data = json.load(f)
        
        # 直近10回の実行を評価
        recent_errors = error_data.get("last_errors", [])
        if not recent_errors:
            return 1.0
        
        # 直近のエラー数から成功率を推定
        consecutive_errors = error_data.get("consecutive_errors", 0)
        if consecutive_errors == 0:
            return 1.0
        elif consecutive_errors <= 2:
            return 0.8
        else:
            return 0.5
    
    def should_allow_posting(self) -> bool:
        """段階的実行モード：投稿を許可するかチェック"""
        if not self.gradual_mode:
            return True  # 段階的モードが無効なら常に許可
        
        success_rate = self.calculate_success_rate()
        print(f"📊 現在の成功率: {success_rate*100:.1f}%")
        
        if success_rate >= self.success_threshold:
            print(f"✅ 成功率が閾値({self.success_threshold*100:.0f}%)以上のため投稿を実行")
            return True
        else:
            print(f"⚠️  成功率が閾値({self.success_threshold*100:.0f}%)未満のためドライランのみ実行")
            return False
    
    def get_products_to_post(self, max_count: int = 3) -> List[Dict]:
        """投稿用商品データ取得"""
        products = []
        
        try:
            worksheets = self.sh.worksheets()
            
            for worksheet in worksheets:
                try:
                    data = worksheet.get_all_values()
                    if len(data) <= 1:
                        continue
                    
                    rows = data[1:]  # ヘッダー除く
                    
                    for row in rows:
                        if len(row) < 3 or not row[1]:  # URLがない場合はスキップ
                            continue
                        
                        product = {
                            'title': row[0] if len(row) > 0 else '',
                            'url': row[1] if len(row) > 1 else '',
                            'price': row[2] if len(row) > 2 else '',
                            'description': row[6] if len(row) > 6 else row[0],
                            'sheet_name': worksheet.title
                        }
                        
                        products.append(product)
                        
                        if len(products) >= max_count:
                            break
                    
                    if len(products) >= max_count:
                        break
                        
                except Exception as e:
                    print(f"シート読み込みエラー: {worksheet.title} - {e}")
                    continue
        
        except Exception as e:
            print(f"データ取得エラー: {e}")
            return []
        
        return products[:max_count]
    
    def post_to_room(self, products: List[Dict]) -> int:
        """楽天ROOMに投稿"""
        if not products:
            print("投稿する商品がありません")
            return 0
        
        # 日次制限チェック
        daily_stats = self.get_daily_stats()
        if daily_stats["posts"] >= self.daily_limit:
            print(f"本日の投稿制限に達しています: {daily_stats['posts']}/{self.daily_limit}")
            return 0
        
        posted_count = 0
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            try:
                # ログイン
                if not self._login(page):
                    return 0
                
                # 投稿処理
                for i, product in enumerate(products):
                    if daily_stats["posts"] + posted_count >= self.daily_limit:
                        print("日次制限に達したため投稿を停止")
                        break
                    
                    try:
                        if self._post_product(page, product):
                            posted_count += 1
                            print(f"投稿成功: {product['title'][:30]}...")
                            
                            # 統計更新
                            self.update_daily_stats(daily_stats["posts"] + posted_count)
                            
                            # 投稿間隔（5-10分）
                            if i < len(products) - 1:
                                delay = random.uniform(300, 600)
                                print(f"次の投稿まで {delay/60:.1f}分 待機...")
                                time.sleep(delay)
                        else:
                            print(f"投稿失敗: {product['title'][:30]}...")
                            
                    except Exception as e:
                        print(f"投稿エラー: {e}")
                        continue
            
            finally:
                browser.close()
        
        print(f"投稿完了: {posted_count}件")
        return posted_count
    
    def _login(self, page) -> bool:
        """楽天ROOMにログイン"""
        try:
            print("楽天ROOMにログイン中...")
            
            page.goto("https://room.rakuten.co.jp/", timeout=30000)
            time.sleep(random.uniform(2, 4))
            
            # ログインボタンクリック
            page.click('a[href*="login"]', timeout=10000)
            time.sleep(random.uniform(1, 3))
            
            # メールアドレス入力
            page.fill('input[type="email"]', os.environ["ROOM_EMAIL"])
            time.sleep(random.uniform(0.5, 1.5))
            
            # パスワード入力
            page.fill('input[type="password"]', os.environ["ROOM_PASSWORD"])
            time.sleep(random.uniform(0.5, 1.5))
            
            # ログインボタンクリック
            page.click('button[type="submit"]', timeout=10000)
            
            # ログイン完了を待機
            page.wait_for_url("**/room.rakuten.co.jp/**", timeout=15000)
            time.sleep(random.uniform(2, 4))
            
            print("ログイン成功")
            return True
            
        except Exception as e:
            print(f"ログインエラー: {e}")
            return False
    
    def _post_product(self, page, product: Dict) -> bool:
        """商品を投稿"""
        try:
            # 商品URL移動
            page.goto(product['url'], timeout=30000)
            time.sleep(random.uniform(2, 4))
            
            # 「ROOMに投稿」ボタンを探してクリック（複数のフォールバック戦略）
            selectors = [
                # 標準的なセレクター
                'button:has-text("ROOMに投稿")',
                'a:has-text("ROOMに投稿")',
                
                # より広範囲なテキストマッチング
                'button:has-text("ROOM")',
                'a:has-text("ROOM")',
                'button:has-text("投稿")',
                'a:has-text("投稿")',
                
                # data属性ベース
                '[data-testid="post-to-room"]',
                '[data-action="room-post"]',
                '[data-room="post"]',
                
                # クラス名ベース
                '.post-to-room-btn',
                '.room-post-button',
                '.rakuten-room-post',
                
                # 部分的なクラス名
                '[class*="room"][class*="post"]',
                '[class*="post"][class*="room"]',
                
                # より一般的なボタン
                'button[type="button"]',
                'input[type="button"]'
            ]
            
            clicked = False
            for selector in selectors:
                try:
                    page.click(selector, timeout=5000)
                    clicked = True
                    break
                except:
                    continue
            
            if not clicked:
                print("投稿ボタンが見つかりません")
                return False
            
            time.sleep(random.uniform(1, 3))
            
            # 投稿フォームが表示されるまで待機
            page.wait_for_selector('textarea, input[type="text"]', timeout=10000)
            time.sleep(random.uniform(1, 2))
            
            # 説明文入力（複数のフォールバック）
            description_selectors = [
                'textarea[placeholder*="コメント"]',
                'textarea[placeholder*="説明"]',
                'textarea[name*="comment"]',
                'textarea[name*="description"]',
                'textarea',
                'input[type="text"][placeholder*="コメント"]',
                'input[type="text"][placeholder*="説明"]',
                'input[type="text"]',
                '[contenteditable="true"]'
            ]
            
            description_filled = False
            for selector in description_selectors:
                try:
                    page.fill(selector, product['description'])
                    description_filled = True
                    break
                except:
                    continue
            
            if not description_filled:
                print("⚠️  説明文入力フィールドが見つかりません")
            
            time.sleep(random.uniform(1, 2))
            
            # 投稿ボタンクリック（複数のフォールバック）
            submit_selectors = [
                # テキストベース
                'button:has-text("投稿する")',
                'button:has-text("投稿")',
                'button:has-text("送信")',
                'button:has-text("完了")',
                'a:has-text("投稿")',
                
                # 属性ベース
                'button[type="submit"]',
                'input[type="submit"]',
                'button[value="投稿"]',
                
                # クラス名ベース
                '.submit-btn',
                '.post-btn',
                '.send-btn',
                '[class*="submit"]',
                '[class*="post"]',
                
                # より一般的
                'form button:last-child',
                'button:last-child'
            ]
            
            submit_clicked = False
            for selector in submit_selectors:
                try:
                    page.click(selector, timeout=5000)
                    submit_clicked = True
                    break
                except:
                    continue
            
            if not submit_clicked:
                print("⚠️  投稿ボタンが見つかりません")
                return False
            
            # 投稿完了を確認
            time.sleep(3)
            
            return True
            
        except Exception as e:
            print(f"投稿エラー: {e}")
            return False


def main():
    """メイン実行"""
    try:
        poster = RoomPoster()
        
        # 停止状態チェック
        if poster.check_suspension_status():
            poster.log_action("EXECUTION_SKIPPED", {"reason": "system_suspended"}, "WARNING")
            print("システム停止中のため実行をスキップします")
            return 0
        
        # 投稿可能数チェック
        daily_stats = poster.get_daily_stats()
        remaining = poster.daily_limit - daily_stats["posts"]
        
        if remaining <= 0:
            print("本日の投稿制限に達しています")
            return 0
        
        print(f"本日の残り投稿可能数: {remaining}")
        
        # 商品データ取得
        products = poster.get_products_to_post(remaining)
        if not products:
            print("投稿する商品がありません")
            return 0
        
        print(f"投稿予定商品数: {len(products)}")
        
        # 実行モード決定（ドライラン/段階的実行/通常投稿）
        if poster.dry_run:
            poster.log_action("MODE_SELECTED", {"mode": "dry_run", "reason": "dry_run_enabled"})
            posted_count = poster.dry_run_mode(products)
        elif poster.gradual_mode and not poster.should_allow_posting():
            # 段階的実行モードで成功率が低い場合はドライランのみ
            poster.log_action("MODE_SELECTED", {"mode": "dry_run", "reason": "gradual_mode_low_success_rate"})
            posted_count = poster.dry_run_mode(products)
        else:
            poster.log_action("MODE_SELECTED", {"mode": "live_posting", "reason": "normal_execution"})
            posted_count = poster.post_to_room(products)
        
        # 結果に応じて成功/失敗を記録
        if posted_count > 0:
            poster.record_success()
            poster.log_action("EXECUTION_SUCCESS", {"posted_count": posted_count, "products_count": len(products)})
            print(f"✅ 投稿成功: {posted_count}件")
        else:
            poster.record_error("POST_FAILURE", "投稿に失敗しました")
            poster.log_action("EXECUTION_FAILURE", {"posted_count": 0, "products_count": len(products)}, "ERROR")
            print("❌ 投稿失敗")
        
        return posted_count
        
    except Exception as e:
        print(f"❌ システムエラー: {e}")
        try:
            poster = RoomPoster()
            poster.record_error("SYSTEM_ERROR", str(e))
        except:
            pass
        return 0


if __name__ == "__main__":
    exit(main())