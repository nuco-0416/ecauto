"""
ログユーティリティ

構造化ログ、ファイルローテーション、コンソール出力を提供
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
import sys


def setup_logger(
    name: str,
    log_file: Optional[Path] = None,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console_output: bool = True
) -> logging.Logger:
    """
    構造化ログを設定する

    Args:
        name: ロガー名（通常はモジュール名やデーモン名）
        log_file: ログファイルのパス（指定しない場合は logs/{name}.log）
        level: ログレベル（デフォルト: INFO）
        max_bytes: ログファイルの最大サイズ（デフォルト: 10MB）
        backup_count: ローテーションで保持する古いログファイル数（デフォルト: 5）
        console_output: コンソールにも出力するか（デフォルト: True）

    Returns:
        logging.Logger: 設定済みのロガー

    使用例:
        >>> from shared.utils.logger import setup_logger
        >>> logger = setup_logger('my_daemon')
        >>> logger.info('デーモン起動')
        >>> logger.error('エラー発生', exc_info=True)
    """
    # ロガーを取得（既存のロガーがあれば再利用）
    logger = logging.getLogger(name)

    # 既にハンドラが設定されている場合はそのまま返す
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # ログファイルのパスを決定
    if log_file is None:
        # デフォルトは logs/{name}.log
        log_dir = Path(__file__).resolve().parent.parent.parent / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f'{name}.log'
    else:
        # 親ディレクトリを作成
        log_file.parent.mkdir(parents=True, exist_ok=True)

    # フォーマッター
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # ファイルハンドラ（ローテーション付き）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # ログの二重出力を防ぐため、ルートロガーへの伝播を無効化
    # 理由: 下記でルートロガーにもハンドラーを追加しているため、
    # propagate=Trueだとログが二重に出力される
    logger.propagate = False

    # コンソールハンドラ（オプション）
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # ISSUE #011対応: ルートloggerにもhandlerを設定
    # これにより、すべての子logger（__name__を使用しているlogger）も
    # 自動的にログを出力するようになる
    root_logger = logging.getLogger()

    # ルートloggerにまだhandlerが設定されていない場合のみ追加
    if not root_logger.handlers:
        root_logger.setLevel(level)
        root_logger.addHandler(file_handler)
        if console_output:
            root_logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    既存のロガーを取得（設定済みの場合）

    Args:
        name: ロガー名

    Returns:
        logging.Logger: ロガー

    Note:
        setup_logger() を先に呼び出す必要があります
    """
    return logging.getLogger(name)


# 便利なログレベル定数
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL
