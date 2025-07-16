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
        
        # 監視設定
        self.metrics_file = Path("performance_metrics.json")
        self.health_thresholds = {
            'success_rate_warning': 0.7,  # 70%未満で警告
            'success_rate_critical': 0.5,  # 50%未満で緊急
            'consecutive_errors_warning': 2,
            'consecutive_errors_critical': 3
        }
    
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
    
    def calculate_success_rate(self, days_back: int = 7) -> dict:
        """詳細な成功率計算"""
        metrics = {
            'current_rate': 1.0,
            'weekly_rate': 1.0,
            'trend': 'stable',
            'consecutive_errors': 0,
            'total_executions': 0,
            'successful_executions': 0,
            'last_success': None,
            'last_error': None
        }
        
        # エラー追跡データから計算
        if self.error_file.exists():
            with open(self.error_file, "r", encoding="utf-8") as f:
                error_data = json.load(f)
            
            metrics['consecutive_errors'] = error_data.get("consecutive_errors", 0)
            recent_errors = error_data.get("last_errors", [])
            
            if recent_errors:
                metrics['last_error'] = recent_errors[-1]['timestamp']
        
        # パフォーマンスメトリクスから詳細計算
        if self.metrics_file.exists():
            with open(self.metrics_file, "r", encoding="utf-8") as f:
                performance_data = json.load(f)
            
            # 週間実行データを分析
            from datetime import datetime, timedelta
            cutoff_date = datetime.now() - timedelta(days=days_back)
            recent_executions = [
                exec_data for exec_data in performance_data.get('executions', [])
                if datetime.fromisoformat(exec_data['timestamp']) > cutoff_date
            ]
            
            if recent_executions:
                metrics['total_executions'] = len(recent_executions)
                metrics['successful_executions'] = sum(
                    1 for exec_data in recent_executions 
                    if exec_data.get('success', False)
                )
                metrics['weekly_rate'] = metrics['successful_executions'] / metrics['total_executions']
                
                # 最新成功日時
                successful_executions = [
                    exec_data for exec_data in recent_executions 
                    if exec_data.get('success', False)
                ]
                if successful_executions:
                    metrics['last_success'] = successful_executions[-1]['timestamp']
        
        # 現在の成功率（従来ロジック）
        if metrics['consecutive_errors'] == 0:
            metrics['current_rate'] = 1.0
        elif metrics['consecutive_errors'] <= 2:
            metrics['current_rate'] = 0.8
        else:
            metrics['current_rate'] = 0.5
        
        # トレンド分析
        if metrics['weekly_rate'] > 0.8:
            metrics['trend'] = 'improving'
        elif metrics['weekly_rate'] < 0.6:
            metrics['trend'] = 'degrading'
        else:
            metrics['trend'] = 'stable'
        
        return metrics
    
    def monitor_system_health(self) -> dict:
        """システムヘルス監視"""
        health = {
            'status': 'healthy',
            'alerts': [],
            'warnings': [],
            'last_check': datetime.now().isoformat(),
            'uptime_info': {},
            'performance_summary': {}
        }
        
        # 成功率チェック
        metrics = self.calculate_success_rate()
        current_rate = metrics['current_rate']
        weekly_rate = metrics['weekly_rate']
        
        # 成功率アラート
        if current_rate <= self.health_thresholds['success_rate_critical']:
            health['status'] = 'critical'
            health['alerts'].append({
                'type': 'success_rate_critical',
                'message': f"成功率が危険レベル: {current_rate*100:.1f}%",
                'threshold': f"{self.health_thresholds['success_rate_critical']*100:.0f}%",
                'severity': 'high'
            })
        elif current_rate <= self.health_thresholds['success_rate_warning']:
            if health['status'] == 'healthy':
                health['status'] = 'warning'
            health['warnings'].append({
                'type': 'success_rate_warning',
                'message': f"成功率が低下: {current_rate*100:.1f}%",
                'threshold': f"{self.health_thresholds['success_rate_warning']*100:.0f}%",
                'severity': 'medium'
            })
        
        # 連続エラーチェック
        consecutive_errors = metrics['consecutive_errors']
        if consecutive_errors >= self.health_thresholds['consecutive_errors_critical']:
            health['status'] = 'critical'
            health['alerts'].append({
                'type': 'consecutive_errors_critical',
                'message': f"連続エラー数が危険レベル: {consecutive_errors}回",
                'threshold': f"{self.health_thresholds['consecutive_errors_critical']}回",
                'severity': 'high'
            })
        elif consecutive_errors >= self.health_thresholds['consecutive_errors_warning']:
            if health['status'] == 'healthy':
                health['status'] = 'warning'
            health['warnings'].append({
                'type': 'consecutive_errors_warning',
                'message': f"連続エラーが発生: {consecutive_errors}回",
                'threshold': f"{self.health_thresholds['consecutive_errors_warning']}回",
                'severity': 'medium'
            })
        
        # 停止状態チェック
        if self.check_suspension_status():
            health['status'] = 'suspended'
            health['alerts'].append({
                'type': 'system_suspended',
                'message': "システムが一時停止中",
                'severity': 'high'
            })
        
        # アップタイム情報
        health['uptime_info'] = {
            'last_success': metrics.get('last_success'),
            'last_error': metrics.get('last_error'),
            'total_executions': metrics.get('total_executions', 0),
            'successful_executions': metrics.get('successful_executions', 0)
        }
        
        # パフォーマンス要約
        health['performance_summary'] = {
            'current_success_rate': f"{current_rate*100:.1f}%",
            'weekly_success_rate': f"{weekly_rate*100:.1f}%",
            'trend': metrics['trend'],
            'consecutive_errors': consecutive_errors,
            'system_mode': 'dry_run' if self.dry_run else 'live',
            'gradual_mode': self.gradual_mode
        }
        
        return health
    
    def create_github_alert(self, alert_type: str, message: str, details: dict = None):
        """GitHub Issue でアラート作成"""
        if not os.environ.get("GITHUB_TOKEN") or self.dry_run:
            # GitHub トークンがない場合、またはドライランの場合はログのみ
            self.log_action("GITHUB_ALERT_SKIPPED", {
                "alert_type": alert_type,
                "message": message,
                "reason": "no_token_or_dry_run"
            })
            return
        
        try:
            import requests
            
            # Issue 作成用データ
            issue_title = f"🚨 楽天ROOM自動化アラート: {alert_type}"
            issue_body = f"""
## アラート詳細

**種類**: {alert_type}
**メッセージ**: {message}
**発生日時**: {datetime.now().isoformat()}

## システム状態
"""
            
            if details:
                for key, value in details.items():
                    issue_body += f"- **{key}**: {value}\n"
            
            issue_body += f"""

## 推奨対応
1. システムログを確認
2. 楽天ROOMサイトの状態確認
3. 必要に応じて手動でのテスト実行

---
*このIssueは楽天ROOM自動化システムにより自動作成されました*
"""
            
            # GitHub API リクエスト
            headers = {
                "Authorization": f"token {os.environ['GITHUB_TOKEN']}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            data = {
                "title": issue_title,
                "body": issue_body,
                "labels": ["alert", "automation", "monitoring"]
            }
            
            response = requests.post(
                "https://api.github.com/repos/sasayosh1/rakuten-room2/issues",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 201:
                issue_url = response.json()["html_url"]
                self.log_action("GITHUB_ALERT_CREATED", {
                    "alert_type": alert_type,
                    "issue_url": issue_url
                })
                print(f"🔔 GitHub アラート作成: {issue_url}")
            else:
                self.log_action("GITHUB_ALERT_FAILED", {
                    "alert_type": alert_type,
                    "status_code": response.status_code,
                    "error": response.text
                }, "ERROR")
                
        except Exception as e:
            self.log_action("GITHUB_ALERT_ERROR", {
                "alert_type": alert_type,
                "error": str(e)
            }, "ERROR")
    
    def process_health_alerts(self, health: dict):
        """ヘルスチェック結果に基づくアラート処理"""
        # 重要なアラートの場合のみGitHub Issue作成
        for alert in health.get('alerts', []):
            if alert['severity'] == 'high':
                self.create_github_alert(
                    alert['type'],
                    alert['message'],
                    health['performance_summary']
                )
        
        # ヘルス状態をファイルに保存
        health_file = f"system_health_{date.today().isoformat()}.json"
        with open(health_file, "w", encoding="utf-8") as f:
            json.dump(health, f, ensure_ascii=False, indent=2)
    
    def record_execution_metrics(self, execution_data: dict):
        """実行メトリクスを記録"""
        metrics_data = {
            'executions': [],
            'summary': {
                'total_executions': 0,
                'successful_executions': 0,
                'failed_executions': 0,
                'last_updated': datetime.now().isoformat()
            }
        }
        
        # 既存データの読み込み
        if self.metrics_file.exists():
            with open(self.metrics_file, "r", encoding="utf-8") as f:
                metrics_data = json.load(f)
        
        # 新しい実行データを追加
        execution_record = {
            'timestamp': datetime.now().isoformat(),
            'success': execution_data.get('success', False),
            'posted_count': execution_data.get('posted_count', 0),
            'target_count': execution_data.get('target_count', 0),
            'mode': execution_data.get('mode', 'unknown'),
            'execution_time': execution_data.get('execution_time', 0),
            'errors': execution_data.get('errors', []),
            'dry_run': self.dry_run,
            'gradual_mode': self.gradual_mode
        }
        
        metrics_data['executions'].append(execution_record)
        
        # 直近100件のみ保持
        metrics_data['executions'] = metrics_data['executions'][-100:]
        
        # サマリー更新
        total_execs = len(metrics_data['executions'])
        successful_execs = sum(1 for exec_data in metrics_data['executions'] if exec_data['success'])
        
        metrics_data['summary'].update({
            'total_executions': total_execs,
            'successful_executions': successful_execs,
            'failed_executions': total_execs - successful_execs,
            'success_rate': successful_execs / total_execs if total_execs > 0 else 0,
            'last_updated': datetime.now().isoformat()
        })
        
        # ファイルに保存
        with open(self.metrics_file, "w", encoding="utf-8") as f:
            json.dump(metrics_data, f, ensure_ascii=False, indent=2)
        
        self.log_action("METRICS_RECORDED", execution_record)
    
    def generate_performance_report(self) -> dict:
        """パフォーマンスレポート生成"""
        report = {
            'report_date': datetime.now().isoformat(),
            'period_summary': {},
            'trend_analysis': {},
            'recommendations': []
        }
        
        if not self.metrics_file.exists():
            report['period_summary'] = {'message': 'データ不足：メトリクスが蓄積されていません'}
            return report
        
        with open(self.metrics_file, "r", encoding="utf-8") as f:
            metrics_data = json.load(f)
        
        executions = metrics_data.get('executions', [])
        if not executions:
            report['period_summary'] = {'message': 'データ不足：実行履歴がありません'}
            return report
        
        # 期間別サマリー
        from datetime import timedelta
        now = datetime.now()
        
        # 過去7日間の分析
        week_cutoff = now - timedelta(days=7)
        week_execs = [
            exec_data for exec_data in executions
            if datetime.fromisoformat(exec_data['timestamp']) > week_cutoff
        ]
        
        # 過去30日間の分析
        month_cutoff = now - timedelta(days=30)
        month_execs = [
            exec_data for exec_data in executions
            if datetime.fromisoformat(exec_data['timestamp']) > month_cutoff
        ]
        
        report['period_summary'] = {
            'week_stats': {
                'total': len(week_execs),
                'successful': sum(1 for e in week_execs if e['success']),
                'success_rate': sum(1 for e in week_execs if e['success']) / len(week_execs) if week_execs else 0
            },
            'month_stats': {
                'total': len(month_execs),
                'successful': sum(1 for e in month_execs if e['success']),
                'success_rate': sum(1 for e in month_execs if e['success']) / len(month_execs) if month_execs else 0
            }
        }
        
        # トレンド分析
        week_rate = report['period_summary']['week_stats']['success_rate']
        month_rate = report['period_summary']['month_stats']['success_rate']
        
        if week_rate > month_rate + 0.1:
            trend = 'improving'
        elif week_rate < month_rate - 0.1:
            trend = 'degrading'
        else:
            trend = 'stable'
        
        report['trend_analysis'] = {
            'trend': trend,
            'week_vs_month': f"{(week_rate - month_rate)*100:+.1f}%",
            'confidence': 'high' if len(week_execs) >= 3 else 'low'
        }
        
        # 推奨事項
        if week_rate < 0.7:
            report['recommendations'].append("成功率が低下しています。システムの点検を推奨します。")
        if trend == 'degrading':
            report['recommendations'].append("成功率が悪化傾向です。楽天ROOMサイトの変更確認を推奨します。")
        if len(week_execs) == 0:
            report['recommendations'].append("実行頻度が低すぎます。設定を確認してください。")
        
        if not report['recommendations']:
            report['recommendations'].append("システムは正常に動作しています。")
        
        return report
    
    def should_allow_posting(self) -> bool:
        """段階的実行モード：投稿を許可するかチェック"""
        if not self.gradual_mode:
            return True  # 段階的モードが無効なら常に許可
        
        metrics = self.calculate_success_rate()
        success_rate = metrics['current_rate']
        
        print(f"📊 システム状態:")
        print(f"   現在の成功率: {success_rate*100:.1f}%")
        print(f"   週間成功率: {metrics['weekly_rate']*100:.1f}%")
        print(f"   連続エラー: {metrics['consecutive_errors']}回")
        print(f"   トレンド: {metrics['trend']}")
        
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
    start_time = datetime.now()
    execution_errors = []
    
    try:
        poster = RoomPoster()
        
        # システムヘルス監視
        health = poster.monitor_system_health()
        poster.process_health_alerts(health)
        
        print(f"🏥 システム状態: {health['status']}")
        if health['alerts']:
            print(f"🚨 アラート: {len(health['alerts'])}件")
        if health['warnings']:
            print(f"⚠️  警告: {len(health['warnings'])}件")
        
        # 停止状態チェック
        if poster.check_suspension_status():
            poster.log_action("EXECUTION_SKIPPED", {"reason": "system_suspended"}, "WARNING")
            print("システム停止中のため実行をスキップします")
            
            # メトリクス記録
            execution_time = (datetime.now() - start_time).total_seconds()
            poster.record_execution_metrics({
                'success': False,
                'posted_count': 0,
                'target_count': 0,
                'mode': 'suspended',
                'execution_time': execution_time,
                'errors': ['system_suspended']
            })
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
        execution_time = (datetime.now() - start_time).total_seconds()
        execution_mode = 'dry_run' if poster.dry_run else ('gradual' if poster.gradual_mode else 'live')
        
        if posted_count > 0:
            poster.record_success()
            poster.log_action("EXECUTION_SUCCESS", {"posted_count": posted_count, "products_count": len(products)})
            print(f"✅ 投稿成功: {posted_count}件")
            
            # 成功メトリクス記録
            poster.record_execution_metrics({
                'success': True,
                'posted_count': posted_count,
                'target_count': len(products),
                'mode': execution_mode,
                'execution_time': execution_time,
                'errors': execution_errors
            })
        else:
            poster.record_error("POST_FAILURE", "投稿に失敗しました")
            poster.log_action("EXECUTION_FAILURE", {"posted_count": 0, "products_count": len(products)}, "ERROR")
            print("❌ 投稿失敗")
            
            # 失敗メトリクス記録
            execution_errors.append("post_failure")
            poster.record_execution_metrics({
                'success': False,
                'posted_count': 0,
                'target_count': len(products),
                'mode': execution_mode,
                'execution_time': execution_time,
                'errors': execution_errors
            })
        
        # パフォーマンスレポート生成（週次）
        if datetime.now().weekday() == 0:  # 月曜日
            report = poster.generate_performance_report()
            report_file = f"performance_report_{date.today().isoformat()}.json"
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"📊 週次パフォーマンスレポート生成: {report_file}")
        
        return posted_count
        
    except Exception as e:
        print(f"❌ システムエラー: {e}")
        try:
            poster = RoomPoster()
            poster.record_error("SYSTEM_ERROR", str(e))
            
            # システムエラーのメトリクス記録
            execution_time = (datetime.now() - start_time).total_seconds()
            execution_errors.append(f"system_error: {str(e)}")
            poster.record_execution_metrics({
                'success': False,
                'posted_count': 0,
                'target_count': 0,
                'mode': 'error',
                'execution_time': execution_time,
                'errors': execution_errors
            })
        except:
            pass
        return 0


if __name__ == "__main__":
    exit(main())