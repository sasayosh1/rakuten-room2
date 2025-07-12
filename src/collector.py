#!/usr/bin/env python3
"""楽天市場商品データ収集"""

import base64
import json
import os
import random
import time
from dataclasses import dataclass
from typing import List, Dict
import requests
import gspread
from bs4 import BeautifulSoup


@dataclass
class Product:
    """商品データクラス"""
    title: str
    url: str
    price: str
    image_url: str
    shop_name: str
    rating: str
    review_count: str
    description: str = ""


# 検索キーワード（簡略化）
KEYWORDS = {
    "20代": ["ニキビケア", "保湿クリーム", "美白美容液", "アイクリーム"],
    "30代": ["大人ニキビ", "高保湿", "シミ消し", "エイジングケア"],
    "40代": ["毛穴たるみ", "乾燥小じわ", "シミ集中ケア", "たるみ改善"],
    "50代": ["角質ケア", "高保湿クリーム", "美白クリーム", "たるみケア"]
}


class ProductCollector:
    """商品データ収集クラス"""
    
    def __init__(self):
        """初期化"""
        # 環境変数チェック
        required_vars = ["RAKUTEN_APP_ID", "GSA_JSON_B64", "GSPREAD_KEY"]
        for var in required_vars:
            if not os.environ.get(var):
                raise ValueError(f"環境変数 {var} が設定されていません")
        
        # Google Sheets設定
        sa_json_b64 = os.environ["GSA_JSON_B64"]
        sa_info_json = base64.b64decode(sa_json_b64)
        sa_info = json.loads(sa_info_json)
        self.gc = gspread.service_account_from_dict(sa_info)
        self.sh = self.gc.open_by_key(os.environ["GSPREAD_KEY"])
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def search_products(self, keyword: str, max_products: int = 5) -> List[Product]:
        """商品検索"""
        print(f"検索中: {keyword}")
        
        params = {
            'applicationId': os.environ["RAKUTEN_APP_ID"],
            'keyword': keyword,
            'format': 'json',
            'hits': max_products,
            'sort': 'standard'
        }
        
        try:
            response = self.session.get(
                "https://app.rakuten.co.jp/services/api/IchibaItem/Search/20220601",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            products = []
            
            if "Items" not in data:
                return []

            for item_data in data["Items"]:
                try:
                    item = item_data["Item"]
                    
                    title = item.get("itemName", "")
                    product_url = item.get("itemUrl", "")
                    price = f"{item.get('itemPrice', 0):,}円"
                    image_url = ""
                    if item.get("mediumImageUrls"):
                        image_url = item["mediumImageUrls"][0].get("imageUrl", "")
                    shop_name = item.get("shopName", "")
                    rating = f"{item.get('reviewAverage', 0):.1f}"
                    review_count = f"{item.get('reviewCount', 0)}件"
                    
                    description = f"✨ {title[:30]}...\n\n価格: {price}\n⭐ 評価: {rating}\n\nおすすめです！"
                    
                    product = Product(
                        title=title,
                        url=product_url,
                        price=price,
                        image_url=image_url,
                        shop_name=shop_name,
                        rating=rating,
                        review_count=review_count,
                        description=description
                    )
                    
                    products.append(product)
                    
                except Exception as e:
                    print(f"商品パースエラー: {e}")
                    continue
                    
            print(f"取得した商品数: {len(products)}")
            return products
            
        except Exception as e:
            print(f"検索エラー: {e}")
            return []
    
    def save_to_sheets(self, products: List[Product], category: str) -> bool:
        """Google Sheetsに保存"""
        if not products:
            return False
            
        try:
            # シート取得または作成
            try:
                worksheet = self.sh.worksheet(category)
            except gspread.WorksheetNotFound:
                worksheet = self.sh.add_worksheet(title=category, rows=1000, cols=10)
                # ヘッダー追加
                headers = ["商品名", "商品URL", "価格", "ショップ名", "評価", "レビュー数", "紹介文", "画像URL", "更新日時"]
                worksheet.append_row(headers)
            
            # 既存データチェック（重複除去）
            existing_urls = set()
            try:
                existing_data = worksheet.get_all_values()[1:]  # ヘッダー除く
                existing_urls = {row[1] for row in existing_data if len(row) > 1}
            except:
                pass
            
            # 新しい商品のみ追加
            new_products = [p for p in products if p.url not in existing_urls]
            
            for product in new_products:
                row_data = [
                    product.title,
                    product.url,
                    product.price,
                    product.shop_name,
                    product.rating,
                    product.review_count,
                    product.description,
                    product.image_url,
                    time.strftime("%Y-%m-%d %H:%M:%S")
                ]
                worksheet.append_row(row_data)
                time.sleep(1)  # API制限対策
            
            print(f"新規保存: {len(new_products)}件")
            return True
            
        except Exception as e:
            print(f"保存エラー: {e}")
            return False
    
    def collect_all(self, products_per_keyword: int = 3):
        """全カテゴリ収集"""
        print("=== 商品データ収集開始 ===")
        total_collected = 0
        
        for age_group, keywords in KEYWORDS.items():
            print(f"\n年代: {age_group}")
            
            all_products = []
            for keyword in keywords:
                products = self.search_products(keyword, products_per_keyword)
                all_products.extend(products)
                time.sleep(random.uniform(1, 3))  # API制限対策
            
            # 重複除去
            unique_products = []
            seen_urls = set()
            for product in all_products:
                if product.url not in seen_urls:
                    unique_products.append(product)
                    seen_urls.add(product.url)
            
            # Google Sheetsに保存
            if self.save_to_sheets(unique_products, age_group):
                total_collected += len(unique_products)
            
            time.sleep(random.uniform(2, 5))
        
        print(f"\n✅ 収集完了: 合計 {total_collected} 商品")
        return total_collected


def main():
    """メイン実行"""
    try:
        collector = ProductCollector()
        collector.collect_all(products_per_keyword=3)
        return 0
    except Exception as e:
        print(f"エラー: {e}")
        return 1


if __name__ == "__main__":
    exit(main())