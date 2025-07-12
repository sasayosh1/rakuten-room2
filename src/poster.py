#!/usr/bin/env python3
"""楽天ROOM投稿ボット"""

import base64
import json
import os
import random
import time
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
        
        self.daily_limit = 3  # 1日最大投稿数
        self.stats_file = Path("daily_stats.json")
    
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
            
            # 「ROOMに投稿」ボタンを探してクリック
            selectors = [
                'button:has-text("ROOMに投稿")',
                'a:has-text("ROOMに投稿")',
                '[data-testid="post-to-room"]',
                '.post-to-room-btn'
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
            
            # 説明文入力
            description_selectors = ['textarea', 'input[type="text"]']
            for selector in description_selectors:
                try:
                    page.fill(selector, product['description'])
                    break
                except:
                    continue
            
            time.sleep(random.uniform(1, 2))
            
            # 投稿ボタンクリック
            submit_selectors = [
                'button:has-text("投稿")',
                'button[type="submit"]',
                'input[type="submit"]'
            ]
            
            for selector in submit_selectors:
                try:
                    page.click(selector, timeout=5000)
                    break
                except:
                    continue
            
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
        
        # 投稿実行
        posted_count = poster.post_to_room(products)
        return posted_count
        
    except Exception as e:
        print(f"エラー: {e}")
        return 0


if __name__ == "__main__":
    exit(main())