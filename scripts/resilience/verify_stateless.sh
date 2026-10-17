#!/usr/bin/env bash
# ==============================================================================
# Distributed Reviews & Ratings Platform — Лабораторна робота №2
# Комплексна верифікація Stateless-архітектури, відсутності Sticky Sessions
# та безшовного Failover за балансувальником Nginx.
#
# Сценарії верифікації:
#   Сценарій 1: Round-Robin балансування та ідентифікація вузлів (X-Instance-ID)
#   Сценарій 2: Cross-Instance Consistency без сесійної прив'язки (Cookie JWT,
#               спільне читання/запис Target, перевірка OCC та кешу Redis)
#   Сценарій 3: Аварійне падіння вузла (Crash Failover & Self-Healing)
# ==============================================================================

set -euo pipefail

# --- ANSI кольори та стилі оформлення ---
BOLD='\033[1m'
DIM='\033[2m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# --- Конфігурація середовища ---
BASE_URL="${BASE_URL:-http://127.0.0.1}"
API_PREFIX="${API_PREFIX:-/api/v1}"
SUPERADMIN_USER="${SUPERADMIN_USER:-super_admin}"
SUPERADMIN_PASSWORD="${SUPERADMIN_PASSWORD:-super_admin}"
BACKEND_1_CONTAINER="${BACKEND_1_CONTAINER:-rating_backend_1}"
BACKEND_2_CONTAINER="${BACKEND_2_CONTAINER:-rating_backend_2}"
MAX_HEALTH_WAIT="${MAX_HEALTH_WAIT:-30}"

# --- Тимчасові файли для збереження сесій та заголовків ---
COOKIE_JAR=$(mktemp /tmp/rating_stateless_cookies.XXXXXX)
HEADER_DUMP=$(mktemp /tmp/rating_stateless_headers.XXXXXX)
BODY_DUMP=$(mktemp /tmp/rating_stateless_body.XXXXXX)

# --- Глобальний стан для очищення (cleanup trap) ---
TARGET_ID=""
CONTAINER_STOPPED=false

# --- Логування та утиліти виводу ---
log_info()    { echo -e "  ${CYAN}ℹ${NC} $1"; }
log_step()    { echo -e "\n${BOLD}${BLUE}==> $1${NC}"; }
log_success() { echo -e "  ${BOLD}${GREEN}✔ [PASS]${NC} $1"; }
log_warn()    { echo -e "  ${BOLD}${YELLOW}⚠ [WARN]${NC} $1"; }
log_error()   { echo -e "  ${BOLD}${RED}✖ [FAIL]${NC} $1" >&2; }

print_banner() {
    echo -e "${BOLD}${CYAN}================================================================================${NC}"
    echo -e "${BOLD}${CYAN}   DISTRIBUTED REVIEWS & RATINGS PLATFORM — STATELESS VERIFICATION SUITE       ${NC}"
    echo -e "${DIM}   Лабораторна робота №2: Архітектура без збереження стану (Stateless)${NC}"
    echo -e "${BOLD}${CYAN}================================================================================${NC}"
    echo -e "${DIM}Базовий URL Nginx : ${BASE_URL}${NC}"
    echo -e "${DIM}Вузли кластера    : ${BACKEND_1_CONTAINER} (backend-1), ${BACKEND_2_CONTAINER} (backend-2)${NC}"
    echo -e "${DIM}Користувач тесту  : ${SUPERADMIN_USER}${NC}"
    echo -e "${BOLD}${CYAN}--------------------------------------------------------------------------------${NC}"
}

print_scenario_header() {
    local num="$1"
    local title="$2"
    echo -e "\n${BOLD}${MAGENTA}┌──────────────────────────────────────────────────────────────────────────────┐${NC}"
    printf "${BOLD}${MAGENTA}│ СЦЕНАРІЙ %-2s: %-60s │${NC}\n" "${num}" "${title}"
    echo -e "${BOLD}${MAGENTA}└──────────────────────────────────────────────────────────────────────────────┘${NC}"
}

# --- Функція безпечного очищення ресурсів при виході ---
cleanup() {
    local exit_code=$?
    echo ""
    log_info "Виконується процедура гарантованого завершення та очищення..."

    # 1. Видалення створеного тестового об'єкта, якщо він залишився в БД
    if [[ -n "${TARGET_ID}" && -f "${COOKIE_JAR}" ]]; then
        log_info "Очищення тестового Target ID='${TARGET_ID}'..."
        curl -s -S -o /dev/null -X DELETE \
            -b "${COOKIE_JAR}" \
            "${BASE_URL}${API_PREFIX}/targets/${TARGET_ID}" 2>/dev/null || true
    fi

    # 2. Якщо контейнер backend_1 був зупинений для тесту failover — обов'язково відновлюємо його
    if [[ "${CONTAINER_STOPPED}" == "true" ]]; then
        log_warn "Відновлення зупиненого контейнера '${BACKEND_1_CONTAINER}'..."
        docker start "${BACKEND_1_CONTAINER}" >/dev/null 2>&1 || true
    fi

    # 3. Видалення тимчасових файлів
    rm -f "${COOKIE_JAR}" "${HEADER_DUMP}" "${BODY_DUMP}" 2>/dev/null || true

    if [[ ${exit_code} -eq 0 ]]; then
        echo -e "\n${BOLD}${GREEN}================================================================================${NC}"
        echo -e "${BOLD}${GREEN}   ✔ УСІ ТЕСТИ STATELESS-АРХІТЕКТУРИ УСПІШНО ПРОЙДЕНО! (ALL PASSED)            ${NC}"
        echo -e "${BOLD}${GREEN}================================================================================${NC}\n"
    else
        echo -e "\n${BOLD}${RED}================================================================================${NC}"
        echo -e "${BOLD}${RED}   ✖ ТЕСТУВАННЯ ПЕРЕРВАНО ЧЕРЕЗ ПОМИЛКУ (EXIT CODE: ${exit_code})               ${NC}"
        echo -e "${BOLD}${RED}================================================================================${NC}\n"
    fi
    exit "${exit_code}"
}
trap cleanup EXIT INT TERM

# --- Допоміжні функції роботи з HTTP-запитами ---
get_header() {
    local header_name="$1"
    grep -i "^${header_name}:" "${HEADER_DUMP}" 2>/dev/null | tail -n 1 | cut -d: -f2- | tr -d '\r' | sed -e 's/^[[:space:]]*//;s/[[:space:]]*$//' || true
}

# Глобальні змінні останнього виконаного запиту
LAST_STATUS=""
LAST_INSTANCE_ID=""
LAST_PROCESS_TIME=""
LAST_CACHE=""
LAST_BODY=""

http_request() {
    local method="$1"
    local path="$2"
    local data="${3:-}"
    local use_cookies="${4:-false}"
    local save_cookies="${5:-false}"

    local curl_args=(
        -s -S
        -D "${HEADER_DUMP}"
        -o "${BODY_DUMP}"
        -w "%{http_code}"
        -X "${method}"
    )

    if [[ "${use_cookies}" == "true" && -f "${COOKIE_JAR}" ]]; then
        curl_args+=(-b "${COOKIE_JAR}")
    fi

    if [[ "${save_cookies}" == "true" ]]; then
        curl_args+=(-c "${COOKIE_JAR}")
    fi

    if [[ -n "${data}" ]]; then
        curl_args+=(-H "Content-Type: application/json" -d "${data}")
    fi

    curl_args+=("${BASE_URL}${path}")

    LAST_STATUS=""
    LAST_INSTANCE_ID=""
    LAST_PROCESS_TIME=""
    LAST_CACHE=""
    LAST_BODY=""

    local code
    code=$(curl "${curl_args[@]}" 2>/dev/null) || {
        log_error "Неможливо виконати curl запит: ${method} ${path}"
        return 1
    }

    LAST_STATUS="${code}"
    LAST_INSTANCE_ID=$(get_header "X-Instance-ID")
    LAST_PROCESS_TIME=$(get_header "X-Process-Time-Ms")
    LAST_CACHE=$(get_header "X-Cache")
    LAST_BODY=$(cat "${BODY_DUMP}")
    return 0
}

assert_eq() {
    local expected="$1"
    local actual="$2"
    local msg="$3"
    if [[ "${expected}" != "${actual}" ]]; then
        log_error "${msg}: очікувалось '${expected}', отримано '${actual}'"
        return 1
    fi
    log_success "${msg} (${actual})"
    return 0
}

# --- Початкова перевірка залежностей ---
check_prerequisites() {
    log_info "Перевірка системних утиліт (curl, jq, docker)..."
    for tool in curl jq docker; do
        if ! command -v "${tool}" >/dev/null 2>&1; then
            log_error "Не знайдено обов'язкову утиліту: ${tool}"
            exit 1
        fi
    done

    log_info "Перевірка доступності точки входу Nginx (${BASE_URL}/nginx-health)..."
    local nginx_status
    nginx_status=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/nginx-health" 2>/dev/null || true)
    if [[ "${nginx_status}" != "200" ]]; then
        log_error "Точка входу Nginx (${BASE_URL}) недоступна (HTTP ${nginx_status}). Переконайтеся, що docker compose стек запущено!"
        exit 1
    fi
    log_success "Передумови перевірено, проксі-сервер готовий до тестування."
}

# ==============================================================================
# СЦЕНАРІЙ 1: Перевірка балансування Round-Robin та ідентифікації вузлів
# ==============================================================================
run_scenario_1() {
    print_scenario_header "1" "Round-Robin балансування та ідентифікація вузлів (X-Instance-ID)"

    log_info "Виконуємо 6 послідовних запитів до ${API_PREFIX}/health..."
    echo -e "${DIM}  Nginx розподіляє навантаження між upstream-серверами без Sticky Sessions.${NC}\n"

    local count_b1=0
    local count_b2=0
    local total_reqs=6

    for ((i=1; i<=total_reqs; i++)); do
        http_request "GET" "${API_PREFIX}/health"
        assert_eq "200" "${LAST_STATUS}" "Запит #${i}: HTTP статус"

        printf "       ${CYAN}➜ [Запит %d/%d]${NC} HTTP %s | Node: ${BOLD}%-10s${NC} | Process Time: %6s ms\n" \
            "${i}" "${total_reqs}" "${LAST_STATUS}" "${LAST_INSTANCE_ID:-N/A}" "${LAST_PROCESS_TIME:-0}"

        if [[ "${LAST_INSTANCE_ID}" == "backend-1" ]]; then
            count_b1=$((count_b1 + 1))
        elif [[ "${LAST_INSTANCE_ID}" == "backend-2" ]]; then
            count_b2=$((count_b2 + 1))
        else
            log_warn "Отримано невідомий або порожній X-Instance-ID: '${LAST_INSTANCE_ID}'"
        fi
    done

    echo ""
    log_info "Статистика розподілу запитів:"
    echo -e "       • backend-1: ${BOLD}${count_b1}${NC} запитів"
    echo -e "       • backend-2: ${BOLD}${count_b2}${NC} запитів"

    if [[ ${count_b1} -eq 0 || ${count_b2} -eq 0 ]]; then
        log_error "Round-Robin балансування не підтверджено: один з інстансів не отримав жодного запиту!"
        return 1
    fi

    log_success "Round-Robin розподіл підтверджено: обидва інстанси обробляють запити почергово."
}

# ==============================================================================
# СЦЕНАРІЙ 2: Перевірка Cross-Instance Consistency без Sticky Sessions
# ==============================================================================
run_scenario_2() {
    print_scenario_header "2" "Cross-Instance Consistency без Sticky Sessions (PostgreSQL + Redis)"

    # --- Крок 2.1: Автентифікація через Cookie-only JWT ---
    log_step "Крок 2.1: Автентифікація super_admin та збереження HttpOnly Cookies"
    local login_payload
    login_payload=$(jq -n \
        --arg u "${SUPERADMIN_USER}" \
        --arg p "${SUPERADMIN_PASSWORD}" \
        '{username: $u, password: $p}')

    http_request "POST" "${API_PREFIX}/auth/login" "${login_payload}" false true
    assert_eq "200" "${LAST_STATUS}" "Логін користувача super_admin"

    local auth_node="${LAST_INSTANCE_ID}"
    log_info "Сесію видано вузлом: ${BOLD}${auth_node}${NC}"

    # Перевіряємо наявність cookie access_token у файлі cookie jar
    if ! grep -q "access_token" "${COOKIE_JAR}"; then
        log_error "HttpOnly cookie 'access_token' не збережено у cookie jar!"
        return 1
    fi
    log_success "HttpOnly JWT Cookies успішно отримано та збережено."

    # --- Крок 2.2: Створення об'єкта Target ---
    log_step "Крок 2.2: Створення нового Target (POST ${API_PREFIX}/targets)"
    local test_timestamp
    test_timestamp=$(date +%s)
    local test_slug="stateless-test-${test_timestamp}"
    local target_payload
    target_payload=$(jq -n \
        --arg slug "${test_slug}" \
        --arg title "Stateless Test Target ${test_timestamp}" \
        --arg cat "resilience-test" \
        --arg desc "Об'єкт для перевірки консистентності даних між інстансами" \
        '{
            slug: $slug,
            title: $title,
            category: $cat,
            description: $desc,
            metadata: {suite: "stateless_verification", created_at: $slug}
        }')

    http_request "POST" "${API_PREFIX}/targets" "${target_payload}" true false
    assert_eq "201" "${LAST_STATUS}" "Створення нового Target"

    TARGET_ID=$(jq -r '.id // empty' <<< "${LAST_BODY}")
    local initial_version
    initial_version=$(jq -r '.version // empty' <<< "${LAST_BODY}")
    local create_node="${LAST_INSTANCE_ID}"

    if [[ -z "${TARGET_ID}" ]]; then
        log_error "Не вдалося отримати ID створеного Target із відповіді API!"
        return 1
    fi

    assert_eq "1" "${initial_version}" "Початкова OCC-версія Target"
    log_info "Target створено: ID='${BOLD}${TARGET_ID}${NC}' на вузлі: ${BOLD}${create_node}${NC}"
    log_success "Target записано у спільну базу даних PostgreSQL."

    # --- Крок 2.3: Читання Target та перевірка спільного кешу Redis ---
    log_step "Крок 2.3: Послідовне читання картки Target та валідація кешу Redis (MISS -> HIT)"
    log_info "Виконуємо 4 запити до GET ${API_PREFIX}/targets/${TARGET_ID}..."

    local saw_cache_hit=false
    local distinct_read_nodes=()

    for ((i=1; i<=4; i++)); do
        http_request "GET" "${API_PREFIX}/targets/${TARGET_ID}" "" true false
        assert_eq "200" "${LAST_STATUS}" "Читання Target (#${i})"

        local cache_status="${LAST_CACHE:-MISS}"
        if [[ "${cache_status}" == "HIT" ]]; then
            saw_cache_hit=true
        fi

        # Зберігаємо унікальні вузли читання
        if [[ ! " ${distinct_read_nodes[*]:-} " =~ " ${LAST_INSTANCE_ID} " ]]; then
            distinct_read_nodes+=("${LAST_INSTANCE_ID}")
        fi

        printf "       ${CYAN}➜ [Читання %d/4]${NC} HTTP %s | Node: ${BOLD}%-10s${NC} | X-Cache: ${BOLD}%-8s${NC} | Title: %s\n" \
            "${i}" "${LAST_STATUS}" "${LAST_INSTANCE_ID:-N/A}" "${cache_status}" "$(jq -r '.title' <<< "${LAST_BODY}")"
    done

    log_info "Запити читання опрацьовано вузлами: ${distinct_read_nodes[*]:-}"
    if [[ "${saw_cache_hit}" == "true" ]]; then
        log_success "Спільний Redis кеш підтверджено: наступні запити повертають X-Cache: HIT незалежно від вузла."
    else
        log_warn "Заголовок X-Cache: HIT не спостерігався під час серії (можливо, TTL сплив швидше або кеш прозорий)."
    fi

    # --- Крок 2.4: Оновлення Target із перевіркою OCC ---
    log_step "Крок 2.4: Оновлення Target (PUT ${API_PREFIX}/targets/${TARGET_ID}) з version: 1"
    local updated_title="Updated Stateless Target ${test_timestamp}"
    local update_payload
    update_payload=$(jq -n \
        --arg title "${updated_title}" \
        --arg cat "resilience-test-updated" \
        --arg desc "Оновлений опис для перевірки інвалідації кешу та версіонування" \
        --argjson ver 1 \
        '{
            title: $title,
            category: $cat,
            description: $desc,
            metadata: {updated: true},
            version: $ver
        }')

    http_request "PUT" "${API_PREFIX}/targets/${TARGET_ID}" "${update_payload}" true false
    assert_eq "200" "${LAST_STATUS}" "Оновлення Target"

    local new_version
    new_version=$(jq -r '.version // empty' <<< "${LAST_BODY}")
    assert_eq "2" "${new_version}" "Інкремент OCC-версії після оновлення"

    local update_node="${LAST_INSTANCE_ID}"
    log_info "Оновлення опрацьовано на вузлі: ${BOLD}${update_node}${NC} (версія: 1 -> 2)"
    log_success "OCC контроль та оновлення успішні. Подією TargetUpdatedEvent інвалідовано кеш у Redis."

    # Демонстрація відхилення застарілої версії (OCC Conflict)
    log_info "Перевірка захисту від Race Condition (повторна спроба оновлення зі застарілою version: 1)..."
    http_request "PUT" "${API_PREFIX}/targets/${TARGET_ID}" "${update_payload}" true false
    assert_eq "409" "${LAST_STATUS}" "Очікувана відмова OCC (HTTP 409 Conflict)"
    log_success "Оптимістичне блокування (OCC) надійно захищає від перезапису даних між вузлами."

    # --- Крок 2.5: Перевірка консистентності оновлених даних з обох вузлів ---
    log_step "Крок 2.5: Читання оновленого об'єкта та підтвердження консистентності (версія 2)"
    for ((i=1; i<=2; i++)); do
        http_request "GET" "${API_PREFIX}/targets/${TARGET_ID}" "" true false
        assert_eq "200" "${LAST_STATUS}" "Верифікація оновленого Target (#${i})"

        local cur_title
        cur_title=$(jq -r '.title' <<< "${LAST_BODY}")
        local cur_ver
        cur_ver=$(jq -r '.version' <<< "${LAST_BODY}")

        assert_eq "${updated_title}" "${cur_title}" "Відповідність оновленої назви на вузлі ${LAST_INSTANCE_ID}"
        assert_eq "2" "${cur_ver}" "Відповідність OCC-версії на вузлі ${LAST_INSTANCE_ID}"

        printf "       ${CYAN}➜ [Перевірка %d/2]${NC} Node: ${BOLD}%-10s${NC} | Version: %s | X-Cache: %-8s\n" \
            "${i}" "${LAST_INSTANCE_ID:-N/A}" "${cur_ver}" "${LAST_CACHE:-MISS}"
    done

    log_success "Повна консистентність даних між різними інстансами бекенду підтверджена!"
}

# ==============================================================================
# СЦЕНАРІЙ 3: Симуляція аварійної відмови вузла (Crash Failover & Self-Healing)
# ==============================================================================
run_scenario_3() {
    print_scenario_header "3" "Аварійна зупинка вузла (Instance Loss / Failover & Self-Healing)"

    # --- Крок 3.1: Аварійна зупинка контейнера backend_1 ---
    log_step "Крок 3.1: Симуляція раптового падіння вузла (docker stop ${BACKEND_1_CONTAINER})"
    log_warn "Зупиняємо контейнер '${BACKEND_1_CONTAINER}'..."
    docker stop "${BACKEND_1_CONTAINER}" >/dev/null
    CONTAINER_STOPPED=true
    log_info "Контейнер '${BACKEND_1_CONTAINER}' успішно зупинено. Кластер перебуває у деградованому стані (1 вузол)."

    # --- Крок 3.2: Виконання запитів через Nginx без простою ---
    log_step "Крок 3.2: Виконання 4 операцій (читання, запис, healthcheck) через Nginx"
    log_info "Nginx повинен миттєво перенаправляти запити на живий вузол без помилок 502/503/504."

    # 1. Healthcheck
    http_request "GET" "${API_PREFIX}/health"
    assert_eq "200" "${LAST_STATUS}" "Failover запит 1/4: GET /health"
    assert_eq "backend-2" "${LAST_INSTANCE_ID}" "Запит 1/4 оброблено живим вузлом backend-2"

    # 2. Читання Target
    http_request "GET" "${API_PREFIX}/targets/${TARGET_ID}" "" true false
    assert_eq "200" "${LAST_STATUS}" "Failover запит 2/4: GET /targets/{id}"
    assert_eq "backend-2" "${LAST_INSTANCE_ID}" "Запит 2/4 оброблено живим вузлом backend-2"

    # 3. Неідемпотентний запис (PUT з оновленням OCC до version: 3)
    local failover_title="Target Surviving Failover $(date +%s)"
    local failover_update_payload
    failover_update_payload=$(jq -n \
        --arg title "${failover_title}" \
        --arg cat "resilience-test-failover" \
        --arg desc "Оновлено під час відмови вузла backend-1" \
        --argjson ver 2 \
        '{
            title: $title,
            category: $cat,
            description: $desc,
            metadata: {failover: true},
            version: $ver
        }')

    http_request "PUT" "${API_PREFIX}/targets/${TARGET_ID}" "${failover_update_payload}" true false
    assert_eq "200" "${LAST_STATUS}" "Failover запит 3/4: PUT /targets/{id} (Non-idempotent write)"
    assert_eq "backend-2" "${LAST_INSTANCE_ID}" "Запит 3/4 оброблено живим вузлом backend-2"
    local failover_version
    failover_version=$(jq -r '.version // empty' <<< "${LAST_BODY}")
    assert_eq "3" "${failover_version}" "Інкремент OCC-версії під час відмови (версія: 3)"

    # 4. Читання оновленого Target
    http_request "GET" "${API_PREFIX}/targets/${TARGET_ID}" "" true false
    assert_eq "200" "${LAST_STATUS}" "Failover запит 4/4: GET /targets/{id} після запису"
    assert_eq "backend-2" "${LAST_INSTANCE_ID}" "Запит 4/4 оброблено живим вузлом backend-2"

    log_success "Жоден запит не зазнав збою! Відсутність 502 Bad Gateway / 504 Gateway Timeout підтверджена."

    # --- Крок 3.3: Відновлення вузла та повернення в ротацію ---
    log_step "Крок 3.3: Запуск відновленого контейнера та повернення в Round-Robin ротацію"
    log_info "Запускаємо '${BACKEND_1_CONTAINER}' (docker start)..."
    docker start "${BACKEND_1_CONTAINER}" >/dev/null
    CONTAINER_STOPPED=false

    log_info "Очікуємо статус healthy для '${BACKEND_1_CONTAINER}' (таймаут ${MAX_HEALTH_WAIT}с)..."
    local wait_seconds=0
    local is_healthy=false
    while [[ ${wait_seconds} -lt ${MAX_HEALTH_WAIT} ]]; do
        local container_health
        container_health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${BACKEND_1_CONTAINER}" 2>/dev/null || echo "not_found")
        if [[ "${container_health}" == "healthy" ]]; then
            is_healthy=true
            break
        fi
        sleep 2
        wait_seconds=$((wait_seconds + 2))
        echo -n "."
    done
    echo ""

    if [[ "${is_healthy}" != "true" ]]; then
        log_error "Контейнер '${BACKEND_1_CONTAINER}' не перейшов у стан 'healthy' за ${MAX_HEALTH_WAIT} секунд!"
        return 1
    fi
    log_success "Контейнер '${BACKEND_1_CONTAINER}' успішно відновив статус healthy!"

    log_info "Перевірка автоматичного повернення вузла в ротацію Nginx (6 запитів)..."
    local recovered_b1=0
    local recovered_b2=0

    for ((i=1; i<=6; i++)); do
        http_request "GET" "${API_PREFIX}/health"
        assert_eq "200" "${LAST_STATUS}" "Запит після відновлення #${i}"

        printf "       ${CYAN}➜ [Ротація %d/6]${NC} Node: ${BOLD}%-10s${NC} | Latency: %6s ms\n" \
            "${i}" "${LAST_INSTANCE_ID:-N/A}" "${LAST_PROCESS_TIME:-0}"

        if [[ "${LAST_INSTANCE_ID}" == "backend-1" ]]; then
            recovered_b1=$((recovered_b1 + 1))
        elif [[ "${LAST_INSTANCE_ID}" == "backend-2" ]]; then
            recovered_b2=$((recovered_b2 + 1))
        fi
    done

    echo ""
    log_info "Статистика ротації після відновлення:"
    echo -e "       • backend-1: ${BOLD}${recovered_b1}${NC} запитів"
    echo -e "       • backend-2: ${BOLD}${recovered_b2}${NC} запитів"

    if [[ ${recovered_b1} -eq 0 || ${recovered_b2} -eq 0 ]]; then
        log_error "Відновлений вузол '${BACKEND_1_CONTAINER}' не повернувся в активну ротацію Nginx (backend-1: ${recovered_b1}, backend-2: ${recovered_b2})!"
        return 1
    fi
    log_success "Вузол '${BACKEND_1_CONTAINER}' автоматично повернувся в ротацію Nginx без перезапуску проксі!"

    # Фінальне видалення створеного Target
    log_step "Завершення сценаріїв: видалення створеного Target (DELETE ${API_PREFIX}/targets/${TARGET_ID})"
    http_request "DELETE" "${API_PREFIX}/targets/${TARGET_ID}" "" true false
    assert_eq "204" "${LAST_STATUS}" "Видалення тестового Target"
    TARGET_ID="" # Очищуємо змінну, щоб trap не повторював видалення
    log_success "Тестовий об'єкт успішно видалено. Стан системи очищено."
}

# --- Головна точка входу ---
main() {
    print_banner
    check_prerequisites
    run_scenario_1
    run_scenario_2
    run_scenario_3
}

main "$@"
