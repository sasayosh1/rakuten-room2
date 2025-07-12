#!/usr/bin/env python3
"""楽天ROOM自動化システム - メインスクリプト"""

import argparse
import sys
from collector_optimized import ProductCollector
from poster import RoomPoster


def main():
    """メイン実行関数"""
    parser = argparse.ArgumentParser(description="楽天ROOM自動化システム")
    parser.add_argument(
        "--mode",
        choices=["collect", "post", "full"],
        default="collect",
        help="実行モード: collect(収集のみ), post(投稿のみ), full(収集+投稿)"
    )
    parser.add_argument(
        "--products",
        type=int,
        default=3,
        help="キーワードあたりの収集商品数 (デフォルト: 3)"
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=3,
        help="最大投稿数 (デフォルト: 3)"
    )
    
    args = parser.parse_args()
    
    print("=== 楽天ROOM自動化システム ===")
    print(f"実行モード: {args.mode}")
    print(f"商品収集数: {args.products}件/キーワード")
    print(f"最大投稿数: {args.max_posts}件")
    print("")
    
    try:
        if args.mode in ["collect", "full"]:
            print("📊 商品データ収集開始...")
            collector = ProductCollector()
            collected_count = collector.collect_all(args.products)
            print(f"✅ 収集完了: {collected_count}件")
            print("")
        
        if args.mode in ["post", "full"]:
            print("📝 楽天ROOM投稿開始...")
            poster = RoomPoster()
            poster.daily_limit = min(args.max_posts, 3)  # 最大3件に制限
            
            # 投稿可能数チェック
            daily_stats = poster.get_daily_stats()
            remaining = poster.daily_limit - daily_stats["posts"]
            
            if remaining <= 0:
                print("⚠️  本日の投稿制限に達しています")
                return 0
            
            # 商品取得と投稿
            products = poster.get_products_to_post(remaining)
            if products:
                posted_count = poster.post_to_room(products)
                print(f"✅ 投稿完了: {posted_count}件")
            else:
                print("⚠️  投稿する商品がありません")
        
        print("\n🎉 処理完了")
        return 0
        
    except Exception as e:
        print(f"\n❌ エラー: {e}")
        return 1


if __name__ == "__main__":
    exit(main())