#!/bin/bash
#
# Yahoo!オークション コンテナ起動スクリプト
#
# 使用方法:
#   ./start_container.sh yahoo_01           # コンテナ起動
#   ./start_container.sh yahoo_01 --build   # イメージ再ビルドして起動
#   ./start_container.sh --all              # 全コンテナ起動
#   ./start_container.sh --stop yahoo_01    # コンテナ停止
#   ./start_container.sh --logs yahoo_01    # ログ表示
#

set -e

# スクリプトのディレクトリに移動
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="$(dirname "$SCRIPT_DIR")"

cd "$DOCKER_DIR"

# ヘルプ表示
show_help() {
    echo "Yahoo!オークション コンテナ管理スクリプト"
    echo ""
    echo "使用方法:"
    echo "  $0 <account_id>           指定アカウントのコンテナを起動"
    echo "  $0 <account_id> --build   イメージを再ビルドして起動"
    echo "  $0 --all                  全コンテナを起動"
    echo "  $0 --stop <account_id>    指定コンテナを停止"
    echo "  $0 --stop-all             全コンテナを停止"
    echo "  $0 --logs <account_id>    指定コンテナのログを表示"
    echo "  $0 --status               コンテナ状態を表示"
    echo "  $0 --help                 このヘルプを表示"
    echo ""
    echo "例:"
    echo "  $0 yahoo_01"
    echo "  $0 yahoo_01 --build"
    echo "  $0 --all"
    echo "  $0 --logs yahoo_01"
}

# 引数チェック
if [ $# -eq 0 ]; then
    show_help
    exit 1
fi

# コマンド処理
case "$1" in
    --help|-h)
        show_help
        exit 0
        ;;

    --all)
        echo "全コンテナを起動中..."
        if [ "$2" = "--build" ]; then
            docker compose up -d --build
        else
            docker compose up -d
        fi
        echo ""
        echo "起動状況:"
        docker compose ps
        ;;

    --stop)
        if [ -z "$2" ]; then
            echo "エラー: アカウントIDを指定してください"
            exit 1
        fi
        echo "コンテナを停止中: $2"
        docker compose stop "$2"
        ;;

    --stop-all)
        echo "全コンテナを停止中..."
        docker compose down
        ;;

    --logs)
        if [ -z "$2" ]; then
            echo "エラー: アカウントIDを指定してください"
            exit 1
        fi
        docker compose logs -f "$2"
        ;;

    --status)
        echo "コンテナ状態:"
        docker compose ps
        ;;

    *)
        ACCOUNT_ID="$1"
        BUILD_FLAG=""

        if [ "$2" = "--build" ]; then
            BUILD_FLAG="--build"
        fi

        echo "コンテナを起動中: $ACCOUNT_ID"
        echo ""

        if [ -n "$BUILD_FLAG" ]; then
            echo "イメージを再ビルドしています..."
            docker compose up -d --build "$ACCOUNT_ID"
        else
            docker compose up -d "$ACCOUNT_ID"
        fi

        echo ""
        echo "起動状況:"
        docker compose ps "$ACCOUNT_ID"
        echo ""
        echo "ログ確認: $0 --logs $ACCOUNT_ID"
        ;;
esac
