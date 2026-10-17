#!/usr/bin/env bash
# ==============================================================================
# switch_algorithm.sh — Утиліта миттєвого перемикання алгоритмів балансування Nginx
# Лабораторна робота №3: Горизонтальне масштабування та балансування навантаження
#
# Використання:
#   bash scripts/load_balancing/switch_algorithm.sh <algorithm> [active_nodes]
#
# Параметри:
#   algorithm:    round_robin | least_conn | weighted | ip_hash
#   active_nodes: 1 | 2 | 3 (за замовчуванням: 3)
# ==============================================================================

set -euo pipefail

ALGORITHM="${1:-}"
ACTIVE_NODES="${2:-3}"

usage() {
    echo "Використання: $0 <algorithm> [active_nodes]"
    echo "  algorithm:    round_robin | least_conn | weighted | ip_hash"
    echo "  active_nodes: 1 | 2 | 3 (за замовчуванням: 3)"
    exit 1
}

if [[ -z "${ALGORITHM}" ]]; then
    echo "Помилка: Не вказано алгоритм балансування!" >&2
    usage
fi

case "${ALGORITHM}" in
    round_robin|least_conn|weighted|ip_hash)
        ;;
    *)
        echo "Помилка: Невідомий алгоритм '${ALGORITHM}'!" >&2
        usage
        ;;
esac

case "${ACTIVE_NODES}" in
    1|2|3)
        ;;
    *)
        echo "Помилка: Неприпустима кількість активних вузлів '${ACTIVE_NODES}' (дозволено 1, 2 або 3)!" >&2
        usage
        ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONF_FILE="${REPO_ROOT}/nginx/default.conf"

if [[ ! -f "${CONF_FILE}" ]]; then
    echo "Помилка: Файл конфігурації Nginx не знайдено за шляхом: ${CONF_FILE}" >&2
    exit 1
fi

UPSTREAM_DIRECTIVE=""
case "${ALGORITHM}" in
    round_robin)
        UPSTREAM_DIRECTIVE="    # Алгоритм балансування за замовчуванням: Round Robin"
        ;;
    least_conn)
        UPSTREAM_DIRECTIVE="    # Алгоритм балансування: Least Connections (ЛР №3)
    least_conn;"
        ;;
    weighted)
        UPSTREAM_DIRECTIVE="    # Алгоритм балансування: Weighted Round Robin (ЛР №3)"
        ;;
    ip_hash)
        UPSTREAM_DIRECTIVE="    # Алгоритм балансування: IP Hash (ЛР №3)
    ip_hash;"
        ;;
esac

UPSTREAM_SERVERS=""
if [[ "${ALGORITHM}" == "weighted" ]]; then
    case "${ACTIVE_NODES}" in
        1)
            UPSTREAM_SERVERS="    server backend_1:8000 weight=3 max_fails=2 fail_timeout=5s;"
            ;;
        2)
            UPSTREAM_SERVERS="    server backend_1:8000 weight=3 max_fails=2 fail_timeout=5s;
    server backend_2:8000 weight=2 max_fails=2 fail_timeout=5s;"
            ;;
        3)
            UPSTREAM_SERVERS="    server backend_1:8000 weight=3 max_fails=2 fail_timeout=5s;
    server backend_2:8000 weight=2 max_fails=2 fail_timeout=5s;
    server backend_3:8000 weight=1 max_fails=2 fail_timeout=5s;"
            ;;
    esac
else
    case "${ACTIVE_NODES}" in
        1)
            UPSTREAM_SERVERS="    server backend_1:8000 max_fails=2 fail_timeout=5s;"
            ;;
        2)
            UPSTREAM_SERVERS="    server backend_1:8000 max_fails=2 fail_timeout=5s;
    server backend_2:8000 max_fails=2 fail_timeout=5s;"
            ;;
        3)
            UPSTREAM_SERVERS="    server backend_1:8000 max_fails=2 fail_timeout=5s;
    server backend_2:8000 max_fails=2 fail_timeout=5s;
    server backend_3:8000 max_fails=2 fail_timeout=5s;"
            ;;
    esac
fi

# КРИТИЧНО ВАЖЛИВО для Docker bind-mount: записуємо оновлений вміст через
# cat > "${CONF_FILE}" << EOF для in-place перезапису без зміни inode файлу!
cat > "${CONF_FILE}" << EOF
# ==============================================================================
# Nginx Reverse Proxy & Load Balancer Configuration for FastAPI (ASGI / Uvicorn)
# ==============================================================================

# 1. Коректний мапінг заголовка Connection для WebSocket / SSE та HTTP/1.1 Keep-Alive
map \$http_upgrade \$connection_upgrade {
    default upgrade;
    ''      "";
}

# 2. Upstream-пул бекенд-серверів FastAPI
upstream fastapi_backend {
    # Спільна зона пам'яті для синхронізації Round-Robin та статусів пасивних healthcheck
    zone fastapi_backend 64k;

${UPSTREAM_DIRECTIVE}

${UPSTREAM_SERVERS}

    # Пул постійних з'єднань до воркерів Uvicorn (зменшує TCP handshake overhead)
    keepalive 32;
    keepalive_timeout 60s;
    keepalive_requests 1000;
}

server {
    listen 80;
    server_name localhost 127.0.0.1 _;

    # Приховуємо версію Nginx у заголовках помилок та Server
    server_tokens off;

    # Максимальний розмір тіла запиту (завантаження файлів / великих JSON)
    client_max_body_size 20M;
    client_body_timeout 30s;
    client_header_timeout 30s;

    # Базові заголовки безпеки (Security Headers)
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Gzip-стиснення текстових та JSON-відповідей API
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 5;
    gzip_min_length 256;
    gzip_types
        application/json
        application/problem+json
        application/javascript
        text/plain
        text/css
        text/xml;

    # Внутрішній healthcheck самого Nginx-контейнера
    location = /nginx-health {
        access_log off;
        default_type text/plain;
        return 200 "healthy\n";
    }

    # Проксування всіх запитів (REST API, /docs, /redoc, /openapi.json, /) на FastAPI
    location / {
        proxy_pass http://fastapi_backend;

        # HTTP/1.1 та підтримка Keep-Alive / WebSocket / SSE
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection \$connection_upgrade;

        # Стандартні проксі-заголовки для FastAPI (ProxyHeadersMiddleware / Uvicorn)
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$http_host;
        proxy_set_header X-Forwarded-Port \$server_port;

        # Наскрізне трасування запитів (Request ID передається у request_logger_middleware)
        proxy_set_header X-Request-ID \$request_id;

        # Перемикання на інший живий upstream-вузол у разі збою (Fault Tolerance)
        proxy_next_upstream error timeout http_502 http_503 http_504;
        proxy_next_upstream_tries 2;
        proxy_next_upstream_timeout 10s;

        # Таймаути взаємодії з FastAPI
        proxy_connect_timeout 1s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        # Буферизація відповідей
        proxy_buffering on;
        proxy_buffer_size 16k;
        proxy_buffers 4 32k;
        proxy_busy_buffers_size 64k;
    }
}
EOF

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^rating_nginx$'; then
    echo "Перевірка конфігурації Nginx у контейнері rating_nginx..."
    docker exec rating_nginx nginx -t
    echo "Перезавантаження конфігурації Nginx (nginx -s reload)..."
    docker exec rating_nginx nginx -s reload
    echo "✔ Алгоритм успішно змінено на '${ALGORITHM}' (${ACTIVE_NODES} активних вузлів), Nginx перезавантажено."
else
    echo "✔ Файл конфігурації '${CONF_FILE}' оновлено для '${ALGORITHM}' (${ACTIVE_NODES} активних вузлів). Контейнер rating_nginx наразі не запущений."
fi
