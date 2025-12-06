"""
通知ユーティリティ

Chatwork、Discord、Slack、Windowsイベントログ、メールでの通知を提供
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import requests


class Notifier:
    """
    統合通知クラス

    複数の通知方法に対応:
    - Chatwork（推奨 - 日本で広く使われるビジネスチャット）
    - Discord Webhook
    - Slack Webhook
    - Windowsイベントログ
    - メール（SMTP）
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Args:
            config_path: 通知設定ファイルのパス（デフォルト: config/notifications.json）
        """
        if config_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent
            config_path = project_root / 'config' / 'notifications.json'

        self.config_path = config_path
        self.config = self._load_config()
        self.logger = logging.getLogger('notifier')

    def _load_config(self) -> Dict[str, Any]:
        """設定ファイルを読み込む"""
        if not self.config_path.exists():
            # デフォルト設定を返す
            return {
                'enabled': False,
                'method': 'chatwork',
                'chatwork': {
                    'api_token': '',
                    'room_id': ''
                },
                'discord': {
                    'webhook_url': ''
                },
                'slack': {
                    'webhook_url': ''
                },
                'email': {
                    'smtp_server': 'smtp.gmail.com',
                    'smtp_port': 587,
                    'from_email': '',
                    'to_email': '',
                    'password': ''
                },
                'events': {
                    'daemon_start': True,
                    'daemon_stop': True,
                    'task_success': False,
                    'task_completion': True,
                    'task_failure': True,
                    'retry_exhausted': True,
                    'service_restart': True,
                    'quota_exceeded': True,
                    'rate_limit_error': True
                }
            }

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"通知設定の読み込みに失敗: {e}")
            return {'enabled': False}

    def is_enabled(self, event_type: str) -> bool:
        """
        特定のイベントタイプで通知が有効か確認

        Args:
            event_type: イベントタイプ（例: 'daemon_start', 'task_failure'）

        Returns:
            bool: 有効ならTrue
        """
        if not self.config.get('enabled', False):
            return False

        events = self.config.get('events', {})
        return events.get(event_type, False)

    def notify(
        self,
        event_type: str,
        title: str,
        message: str,
        level: str = 'INFO'
    ) -> bool:
        """
        通知を送信

        Args:
            event_type: イベントタイプ（例: 'daemon_start', 'task_failure'）
            title: 通知タイトル
            message: 通知メッセージ
            level: ログレベル（INFO, WARNING, ERROR）

        Returns:
            bool: 成功時True
        """
        # 通知が無効または該当イベントが無効な場合はスキップ
        if not self.is_enabled(event_type):
            return True

        method = self.config.get('method', 'chatwork')

        try:
            if method == 'chatwork':
                return self._notify_chatwork(title, message, level)
            elif method == 'discord':
                return self._notify_discord(title, message, level)
            elif method == 'slack':
                return self._notify_slack(title, message, level)
            elif method == 'email':
                return self._notify_email(title, message, level)
            elif method == 'eventlog':
                return self._notify_eventlog(title, message, level)
            else:
                self.logger.warning(f"不明な通知方法: {method}")
                return False

        except Exception as e:
            self.logger.error(f"通知送信に失敗: {e}")
            return False

    def _notify_chatwork(self, title: str, message: str, level: str) -> bool:
        """Chatworkで通知"""
        chatwork_config = self.config.get('chatwork', {})
        api_token = chatwork_config.get('api_token', '')
        room_id = chatwork_config.get('room_id', '')

        if not api_token or not room_id:
            self.logger.warning("Chatwork APIトークンまたはルームIDが設定されていません")
            return False

        # レベルに応じた絵文字とアイコン
        emoji_info = {
            'INFO': {'icon': '✅', 'text': '[info]'},
            'WARNING': {'icon': '⚠️', 'text': '[!]'},
            'ERROR': {'icon': '❌', 'text': '[!!!]'}
        }
        emoji_data = emoji_info.get(level, {'icon': 'ℹ️', 'text': '[info]'})

        # メッセージを整形（Chatwork記法）
        full_message = f"{emoji_data['icon']} {emoji_data['text']}{title}\n{message}\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        headers = {
            'X-ChatWorkToken': api_token
        }
        data = {
            'body': full_message
        }

        try:
            response = requests.post(
                f'https://api.chatwork.com/v2/rooms/{room_id}/messages',
                headers=headers,
                data=data,
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.error(f"Chatwork送信エラー: {e}")
            return False

    def _notify_line(self, title: str, message: str, level: str) -> bool:
        """LINE Notifyで通知（2025年3月31日終了予定）"""
        token = self.config.get('line', {}).get('token', '')
        if not token:
            self.logger.warning("LINE Notifyトークンが設定されていません")
            return False

        # レベルに応じた絵文字
        emoji = {
            'INFO': '✅',
            'WARNING': '⚠️',
            'ERROR': '❌'
        }.get(level, 'ℹ️')

        # メッセージを整形
        full_message = f"{emoji} {title}\n\n{message}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        headers = {
            'Authorization': f'Bearer {token}'
        }
        data = {
            'message': full_message
        }

        try:
            response = requests.post(
                'https://notify-api.line.me/api/notify',
                headers=headers,
                data=data,
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.error(f"LINE Notify送信エラー: {e}")
            return False

    def _notify_discord(self, title: str, message: str, level: str) -> bool:
        """Discord Webhookで通知"""
        webhook_url = self.config.get('discord', {}).get('webhook_url', '')
        if not webhook_url:
            self.logger.warning("Discord Webhook URLが設定されていません")
            return False

        # レベルに応じた色
        color = {
            'INFO': 0x00ff00,  # 緑
            'WARNING': 0xffa500,  # オレンジ
            'ERROR': 0xff0000  # 赤
        }.get(level, 0x0000ff)

        embed = {
            'title': title,
            'description': message,
            'color': color,
            'timestamp': datetime.now().isoformat()
        }

        data = {
            'embeds': [embed]
        }

        try:
            response = requests.post(
                webhook_url,
                json=data,
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.error(f"Discord Webhook送信エラー: {e}")
            return False

    def _notify_slack(self, title: str, message: str, level: str) -> bool:
        """Slack Webhookで通知"""
        webhook_url = self.config.get('slack', {}).get('webhook_url', '')
        if not webhook_url:
            self.logger.warning("Slack Webhook URLが設定されていません")
            return False

        # レベルに応じた色
        color = {
            'INFO': 'good',  # 緑
            'WARNING': 'warning',  # オレンジ
            'ERROR': 'danger'  # 赤
        }.get(level, '#0000ff')

        attachment = {
            'title': title,
            'text': message,
            'color': color,
            'ts': int(datetime.now().timestamp())
        }

        data = {
            'attachments': [attachment]
        }

        try:
            response = requests.post(
                webhook_url,
                json=data,
                timeout=10
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.error(f"Slack Webhook送信エラー: {e}")
            return False

    def _notify_email(self, title: str, message: str, level: str) -> bool:
        """メール（SMTP）で通知"""
        email_config = self.config.get('email', {})

        required_keys = ['smtp_server', 'from_email', 'to_email', 'password']
        if not all(email_config.get(key) for key in required_keys):
            self.logger.warning("メール設定が不完全です")
            return False

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart()
            msg['From'] = email_config['from_email']
            msg['To'] = email_config['to_email']
            msg['Subject'] = f"[EC Auto] {title}"

            body = f"{message}\n\n送信時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            server = smtplib.SMTP(
                email_config['smtp_server'],
                email_config.get('smtp_port', 587)
            )
            server.starttls()
            server.login(email_config['from_email'], email_config['password'])
            server.send_message(msg)
            server.quit()

            return True
        except Exception as e:
            self.logger.error(f"メール送信エラー: {e}")
            return False

    def _notify_eventlog(self, title: str, message: str, level: str) -> bool:
        """Windowsイベントログに記録"""
        try:
            import win32evtlog
            import win32evtlogutil

            # イベントタイプのマッピング
            event_type_map = {
                'INFO': win32evtlog.EVENTLOG_INFORMATION_TYPE,
                'WARNING': win32evtlog.EVENTLOG_WARNING_TYPE,
                'ERROR': win32evtlog.EVENTLOG_ERROR_TYPE
            }

            event_type = event_type_map.get(level, win32evtlog.EVENTLOG_INFORMATION_TYPE)

            win32evtlogutil.ReportEvent(
                'EC Auto',
                1,
                eventType=event_type,
                strings=[title, message]
            )

            return True
        except ImportError:
            self.logger.warning("pywin32がインストールされていません。Windowsイベントログ機能を使用するにはインストールが必要です。")
            return False
        except Exception as e:
            self.logger.error(f"イベントログ記録エラー: {e}")
            return False


# 便利な関数
def create_default_config(output_path: Path):
    """デフォルトの通知設定ファイルを作成"""
    default_config = {
        "enabled": False,
        "method": "chatwork",
        "chatwork": {
            "api_token": "YOUR_CHATWORK_API_TOKEN_HERE",
            "room_id": "YOUR_ROOM_ID_HERE"
        },
        "discord": {
            "webhook_url": "https://discord.com/api/webhooks/YOUR_WEBHOOK_URL_HERE"
        },
        "slack": {
            "webhook_url": "https://hooks.slack.com/services/YOUR_WEBHOOK_URL_HERE"
        },
        "email": {
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "from_email": "your-email@gmail.com",
            "to_email": "your-email@gmail.com",
            "password": "your-app-password"
        },
        "events": {
            "daemon_start": True,
            "daemon_stop": True,
            "task_success": False,
            "task_completion": True,
            "task_failure": True,
            "retry_exhausted": True,
            "service_restart": True,
            "quota_exceeded": True,
            "rate_limit_error": True
        }
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(default_config, f, indent=2, ensure_ascii=False)
