#!/usr/bin/env bash
# ==============================================================================
# run_all.sh — Універсальний раннер навантажувальних випробувань (k6 + Docker)
# Лабораторна робота №5: Load & Performance Baseline
#
# Використання:
#   ./load-tests/run_all.sh [SCENARIO] [OPTIONS...] [-- K6_EXTRA_ARGS...]
#
# Приклади:
#   ./load-tests/run_all.sh all
#   ./load-tests/run_all.sh A -u 50 -d 30s
#   ./load-tests/run_all.sh B -e BASE_URL=http://127.0.0.1
#   ./load-tests/run_all.sh scenario_c_workflow.js
# ==============================================================================

set -euo pipefail

# ANSI Кольори для термінального виводу
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Визначення абсолютних шляхів
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LOAD_TESTS_DIR="${SCRIPT_DIR}"

# Параметри за замовчуванням
SCENARIO_TARGET="all"
BASE_URL="${BASE_URL:-http://127.0.0.1}"
VUS=""
DURATION=""
SUMMARY_EXPORT=""
declare -a ENV_VARS=()
declare -a EXTRA_K6_ARGS=()

usage() {
    echo -e "${BOLD}Використання:${NC}"
    echo -e "  $0 [SCENARIO] [OPTIONS...] [-- K6_EXTRA_ARGS...]"
    echo -e ""
    echo -e "${BOLD}Сценарії (SCENARIO):${NC}"
    echo -e "  ${CYAN}A, a, read, scenario_a${NC}          Scenario A: Read-Intensive (Catalog & Caching)"
    echo -e "  ${CYAN}B, b, write, scenario_b${NC}        Scenario B: Write-Intensive (User Auth & DB Locks)"
    echo -e "  ${CYAN}C, c, workflow, scenario_c${NC}    Scenario C: Complex End-to-End Workflow"
    echo -e "  ${CYAN}all${NC}                             Запустити всі сценарії послідовно (A -> B -> C) [дефолт]"
    echo -e "  ${CYAN}<filename>.js${NC}                   Запустити вказаний JS-файл з директорії load-tests/"
    echo -e ""
    echo -e "${BOLD}Опції (OPTIONS):${NC}"
    echo -e "  ${GREEN}-u, --vus NUM${NC}                  Кількість віртуальних користувачів (VUs)"
    echo -e "  ${GREEN}-d, --duration DURATION${NC}        Тривалість тесту (наприклад: 10s, 30s, 1m)"
    echo -e "  ${GREEN}-b, --base-url URL${NC}             Базовий URL API (за замовчуванням: http://127.0.0.1)"
    echo -e "  ${GREEN}-e, --env KEY=VALUE${NC}            Змінна середовища для передачі в k6"
    echo -e "  ${GREEN}-o, --summary FILE${NC}             Експорт підсумкових метрик k6 у JSON-файл"
    echo -e "  ${GREEN}-h, --help${NC}                     Відобразити цю довідку"
    echo -e ""
    echo -e "${BOLD}Приклади:${NC}"
    echo -e "  $0 all"
    echo -e "  $0 A -u 50 -d 15s"
    echo -e "  $0 B --env TARGET_ID=01a14e52-b501-718f-b96b-e55e221a1460"
    echo -e "  $0 C -- -v --no-thresholds"
    exit 0
}

# Розбір аргументів командного рядка
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            ;;
        -u|--vus)
            VUS="$2"
            shift 2
            ;;
        -d|--duration)
            DURATION="$2"
            shift 2
            ;;
        -b|--base-url)
            BASE_URL="$2"
            shift 2
            ;;
        -o|--summary)
            SUMMARY_EXPORT="$2"
            shift 2
            ;;
        -e|--env)
            ENV_VARS+=("-e" "$2")
            shift 2
            ;;
        --)
            shift
            while [[ $# -gt 0 ]]; do
                EXTRA_K6_ARGS+=("$1")
                shift
            done
            break
            ;;
        -*)
            echo -e "${RED}[ERROR] Невідомий прапорець: $1${NC}" >&2
            usage
            ;;
        *)
            if [[ -z "${SCENARIO_TARGET_SET:-}" ]]; then
                SCENARIO_TARGET="$1"
                SCENARIO_TARGET_SET="1"
            else
                EXTRA_K6_ARGS+=("$1")
            fi
            shift
            ;;
    esac
done

# Перевірка наявності Docker
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${RED}[ERROR] Утиліту 'docker' не знайдено в PATH. Встановіть Docker для запуску k6!${NC}" >&2
    exit 1
fi

# Перевірка запущеного Docker daemon
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}[ERROR] Docker daemon не запущений або у вас немає прав доступу!${NC}" >&2
    exit 1
fi

# Перевірка наявності образу grafana/k6
if ! docker images --format '{{.Repository}}:{{.Tag}}' | grep -q '^grafana/k6:latest'; then
    echo -e "${YELLOW}[INFO] Образ grafana/k6:latest не знайдено локально. Завантаження...${NC}"
    docker pull grafana/k6:latest
fi

echo -e "${BOLD}${BLUE}================================================================================${NC}"
echo -e "${BOLD}${CYAN}   DISTRIBUTED RATINGS PLATFORM — LOAD TESTING SUITE (k6 RUNNER)               ${NC}"
echo -e "${BOLD}${BLUE}================================================================================${NC}"
echo -e "  ${BOLD}Repo Root:${NC}      ${REPO_ROOT}"
echo -e "  ${BOLD}Load Tests Dir:${NC} ${LOAD_TESTS_DIR}"
echo -e "  ${BOLD}Target Base URL:${NC}${BASE_URL}"
echo -e "  ${BOLD}Scenario Mode:${NC}  ${SCENARIO_TARGET}"
if [[ -n "${VUS}" ]]; then
    echo -e "  ${BOLD}VUs Override:${NC}   ${VUS}"
fi
if [[ -n "${DURATION}" ]]; then
    echo -e "  ${BOLD}Duration Override:${NC} ${DURATION}"
fi
echo -e "${BLUE}--------------------------------------------------------------------------------${NC}"

# Функція виконання окремого k6 сценарію
run_single_scenario() {
    local scenario_name="$1"
    local js_file="$2"

    if [[ ! -f "${LOAD_TESTS_DIR}/${js_file}" ]]; then
        echo -e "${RED}[ERROR] Файл сценарію не знайдено: ${LOAD_TESTS_DIR}/${js_file}${NC}" >&2
        return 1
    fi

    echo -e "\n${BOLD}${GREEN}>>> Запуск ${scenario_name} (${js_file})...${NC}"

    local docker_cmd=(
        docker run --rm -i
        --network="host"
        -v "${LOAD_TESTS_DIR}:/load-tests:z"
        --user "$(id -u):$(id -g)"
        -e "BASE_URL=${BASE_URL}"
    )

    if [[ -n "${VUS}" ]]; then
        docker_cmd+=("-e" "VUS=${VUS}")
    fi
    if [[ -n "${DURATION}" ]]; then
        docker_cmd+=("-e" "DURATION=${DURATION}")
    fi
    if [[ ${#ENV_VARS[@]} -gt 0 ]]; then
        docker_cmd+=("${ENV_VARS[@]}")
    fi

    docker_cmd+=("grafana/k6:latest" "run")

    # Прапорці k6 (мають іти після 'grafana/k6:latest run')
    if [[ -n "${VUS}" ]]; then
        docker_cmd+=("-u" "${VUS}")
    fi
    if [[ -n "${DURATION}" ]]; then
        docker_cmd+=("-d" "${DURATION}")
    fi
    if [[ -n "${SUMMARY_EXPORT}" ]]; then
        docker_cmd+=("--summary-export=${SUMMARY_EXPORT}")
    fi
    if [[ ${#EXTRA_K6_ARGS[@]} -gt 0 ]]; then
        docker_cmd+=("${EXTRA_K6_ARGS[@]}")
    fi

    docker_cmd+=("/load-tests/${js_file}")

    echo -e "${DIM}Виконується команда:${NC} ${docker_cmd[*]}"
    "${docker_cmd[@]}"
}

# Визначення списку сценаріїв для запуску
declare -a SCENARIOS_TO_RUN=()

case "${SCENARIO_TARGET}" in
    A|a|read|scenario_a|scenario_a_read.js)
        SCENARIOS_TO_RUN+=("Scenario A (Read-Intensive):scenario_a_read.js")
        ;;
    B|b|write|scenario_b|scenario_b_write.js)
        SCENARIOS_TO_RUN+=("Scenario B (Write-Intensive):scenario_b_write.js")
        ;;
    C|c|workflow|scenario_c|scenario_c_workflow.js)
        SCENARIOS_TO_RUN+=("Scenario C (Complex Workflow):scenario_c_workflow.js")
        ;;
    all)
        SCENARIOS_TO_RUN+=(
            "Scenario A (Read-Intensive):scenario_a_read.js"
            "Scenario B (Write-Intensive):scenario_b_write.js"
            "Scenario C (Complex Workflow):scenario_c_workflow.js"
        )
        ;;
    *.js)
        SCENARIOS_TO_RUN+=("Custom Scenario (${SCENARIO_TARGET}):${SCENARIO_TARGET}")
        ;;
    *)
        echo -e "${RED}[ERROR] Невідомий сценарій: '${SCENARIO_TARGET}'. Дозволено: A, B, C, all або шлях до .js файлу.${NC}" >&2
        usage
        ;;
esac

TOTAL_FAILED=0
START_TIME=$(date +%s)

for item in "${SCENARIOS_TO_RUN[@]}"; do
    scenario_label="${item%%:*}"
    scenario_file="${item##*:}"

    if ! run_single_scenario "${scenario_label}" "${scenario_file}"; then
        echo -e "${RED}[FAIL] Сценарій '${scenario_label}' завершився з помилкою!${NC}"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
    else
        echo -e "${GREEN}[OK] Сценарій '${scenario_label}' успішно виконано.${NC}"
    fi
done

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

echo -e "\n${BOLD}${BLUE}================================================================================${NC}"
echo -e "${BOLD}Підсумок виконання навантажувальних тестів (k6):${NC}"
echo -e "  Загальний час:       ${ELAPSED}s"
echo -e "  Всього сценаріїв:    ${#SCENARIOS_TO_RUN[@]}"
echo -e "  Успішно:             $(( ${#SCENARIOS_TO_RUN[@]} - TOTAL_FAILED ))"
echo -e "  Провалено:           ${TOTAL_FAILED}"
echo -e "${BLUE}================================================================================${NC}"

if [[ ${TOTAL_FAILED} -eq 0 ]]; then
    echo -e "${BOLD}${GREEN}✔ ВСІ НАВАНТАЖУВАЛЬНІ СЦЕНАРІЇ УСПІШНО ПРОЙДЕНО.${NC}\n"
    exit 0
else
    echo -e "${BOLD}${RED}✗ ТЕСТУВАННЯ ЗАВЕРШИЛОСЯ З ПОМИЛКАМИ (провалено: ${TOTAL_FAILED}).${NC}\n"
    exit 1
fi
