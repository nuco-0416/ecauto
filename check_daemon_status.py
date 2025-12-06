"""デーモンの実行状態を確認するスクリプト"""

import sys
from pathlib import Path
from datetime import datetime

# パスを追加
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ロックファイルを確認
lock_file = Path(__file__).parent / 'logs' / 'sync_inventory_daemon.lock'
log_file = Path(__file__).parent / 'logs' / 'sync_inventory.log'

print("\n" + "=" * 70)
print("デーモン実行状態チェック")
print("=" * 70)

# ロックファイルの確認
if lock_file.exists():
    print(f"\n[OK] ロックファイル存在: {lock_file}")
    try:
        with open(lock_file, 'r') as f:
            pid = f.read().strip()
            print(f"   PID: {pid}")
    except:
        print("   [WARN] ロックファイルが読めません（デーモンが使用中）")

    # ロックファイルの更新時刻
    mtime = datetime.fromtimestamp(lock_file.stat().st_mtime)
    age_minutes = (datetime.now() - mtime).total_seconds() / 60
    print(f"   最終更新: {mtime.strftime('%Y-%m-%d %H:%M:%S')} ({age_minutes:.1f}分前)")
else:
    print("\n[NG] ロックファイルなし → デーモンは停止中")

# ログファイルの確認
if log_file.exists():
    print(f"\n[LOG] ログファイル: {log_file}")

    # ログファイルの更新時刻
    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
    age_minutes = (datetime.now() - mtime).total_seconds() / 60
    print(f"   最終更新: {mtime.strftime('%Y-%m-%d %H:%M:%S')} ({age_minutes:.1f}分前)")

    # 最後の10行を読む
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        last_lines = lines[-10:] if len(lines) >= 10 else lines

    print("\n   最新ログ（最後の5行）:")
    for line in last_lines[-5:]:
        print(f"   {line.rstrip()}")

    # 実行中かどうかを判断
    last_line = last_lines[-1] if last_lines else ""

    if "在庫同期を開始します" in last_line:
        print("\n[実行中] 状態: 在庫同期処理中の可能性")
        print("   [警告] SP-APIを呼び出している可能性があります！")
    elif "サマリー" in last_line or "完了" in last_line:
        print("\n[完了] 状態: 最後の実行は正常に完了")
        print("   次回実行: 3時間後")
    elif "SIGINT" in last_line:
        print("\n[停止] 状態: 手動停止（Ctrl+C）")
    elif "ERROR" in last_line or "エラー" in last_line:
        print("\n[エラー] 状態: エラーで停止")
    else:
        print("\n[不明] 状態: 不明（ログを確認してください）")
else:
    print("\n[NG] ログファイルなし")

# 推奨アクション
print("\n" + "=" * 70)
print("推奨アクション")
print("=" * 70)

if lock_file.exists():
    print("""
デーモンが実行中です。以下のいずれかを選択してください：

【オプション1】デーモンを停止してから手動でキャッシュ補完
  1. デーモンを停止: Ctrl+C（実行中のターミナル）
  2. キャッシュ補完を実行:
     python inventory/scripts/validate_and_fill_cache.py --platform base
  3. デーモンを再起動

【オプション2】デーモンに任せる（推奨）
  - デーモンがキャッシュミス時に自動的にSP-APIで補完します
  - 771件の補完には約27分かかります
  - 待つだけで自動的に解決します

【オプション3】デーモンの状態を詳しく確認
  - ログファイルをリアルタイムで監視:
    tail -f logs/sync_inventory.log
""")
else:
    print("""
デーモンが停止中です。以下の方法でキャッシュを補完できます：

【推奨】手動でキャッシュ補完を実行
  python inventory/scripts/validate_and_fill_cache.py --platform base

【または】デーモンを起動して自動補完
  python scheduled_tasks/sync_inventory_daemon.py --interval 10800
""")

print("=" * 70)
print()
