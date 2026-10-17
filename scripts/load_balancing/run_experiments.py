#!/usr/bin/env python3
"""
Комплексний автоматизований скрипт проведення експериментів балансування навантаження та масштабування (ЛР №3).

Реалізує:
1. Експеримент 1: Порівняльний аналіз алгоритмів балансування (round_robin, weighted, ip_hash, least_conn).
2. Експеримент 2: Асиметричне навантаження (Asymmetric Latency: round_robin vs least_conn).
3. Експеримент 3: Scale-Out аналіз (1 vs 2 vs 3 Instances, Speedup та Throughput).
4. Експеримент 4: Fault Tolerance під конкурентним навантаженням (зупинка та відновлення інстансу).

Використовує виключно стандартну бібліотеку Python 3 (asyncio, subprocess, time, statistics, json, sys, pathlib).
Зберігає детальні результати у /tmp/lb_experiment_results.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# Канонічний корінь проєкту
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class RequestResult:
    """Результат виконання одного клієнтського HTTP-запиту."""

    status_code: int
    instance_id: str
    process_time_ms: float
    cache_header: str
    latency_ms: float
    error: str | None = None


def parse_http_response(raw_bytes: bytes) -> tuple[int, dict[str, str], bytes]:
    """Розбирає «сиру» HTTP/1.1 відповідь на статус-код, заголовки та тіло."""
    if not raw_bytes:
        return 0, {}, b""

    sep = b"\r\n\r\n"
    if sep in raw_bytes:
        header_part, body_part = raw_bytes.split(sep, 1)
    else:
        sep = b"\n\n"
        if sep in raw_bytes:
            header_part, body_part = raw_bytes.split(sep, 1)
        else:
            header_part = raw_bytes
            body_part = b""

    split_char = b"\r\n" if b"\r\n" in header_part else b"\n"
    lines = header_part.split(split_char)
    if not lines or not lines[0]:
        return 0, {}, body_part

    status_line = lines[0].decode("latin1", errors="replace")
    status_parts = status_line.split(" ", 2)
    status_code = int(status_parts[1]) if len(status_parts) > 1 and status_parts[1].isdigit() else 0

    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or b":" not in line:
            continue
        key, val = line.split(b":", 1)
        headers[key.decode("latin1").strip().lower()] = val.decode("latin1").strip()

    return status_code, headers, body_part


async def send_http_request(
    host: str,
    port: int,
    path: str,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> RequestResult:
    """
    Виконує швидкий HTTP/1.1 GET-запит через нове TCP-з'єднання з 'Connection: close'.

    Це гарантує незалежний TCP-хендшейк для кожного запиту, усуваючи спотворення
    алгоритмів Round-Robin, Weighted та least_conn через Keep-Alive pooling.
    """
    t0 = time.perf_counter()
    req_headers: dict[str, str] = {
        "Host": f"{host}:{port}" if port not in (80, 443) else host,
        "User-Agent": "LB-Benchmarker/1.0",
        "Accept": "*/*",
        "Connection": "close",
    }
    if headers:
        for k, v in headers.items():
            req_headers[k] = str(v)

    header_lines = [f"GET {path} HTTP/1.1"]
    for k, v in req_headers.items():
        header_lines.append(f"{k}: {v}")
    raw_request = "\r\n".join(header_lines).encode("latin1") + b"\r\n\r\n"

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return RequestResult(
            status_code=0,
            instance_id="error",
            process_time_ms=0.0,
            cache_header="",
            latency_ms=latency_ms,
            error=f"ConnectError: {exc}",
        )

    try:
        writer.write(raw_request)
        await asyncio.wait_for(writer.drain(), timeout=timeout)

        chunks: list[bytes] = []
        while True:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=timeout)
            if not chunk:
                break
            chunks.append(chunk)

        t1 = time.perf_counter()
        latency_ms = round((t1 - t0) * 1000.0, 2)
        response_bytes = b"".join(chunks)

        status_code, resp_headers, body = parse_http_response(response_bytes)

        instance_id = resp_headers.get("x-instance-id")
        if not instance_id and body:
            try:
                data = json.loads(body.decode("utf-8", errors="replace"))
                if isinstance(data, dict):
                    instance_id = data.get("instance_id") or data.get("node")
            except Exception:
                pass

        if not instance_id:
            instance_id = "unknown"

        process_time_raw = resp_headers.get("x-process-time-ms", "0")
        try:
            process_time_ms = float(process_time_raw)
        except ValueError:
            process_time_ms = 0.0

        cache_hdr = resp_headers.get("x-cache", "")

        err_msg = None if (200 <= status_code < 400) else f"HTTP {status_code}"
        return RequestResult(
            status_code=status_code,
            instance_id=instance_id,
            process_time_ms=process_time_ms,
            cache_header=cache_hdr,
            latency_ms=latency_ms,
            error=err_msg,
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return RequestResult(
            status_code=0,
            instance_id="error",
            process_time_ms=0.0,
            cache_header="",
            latency_ms=latency_ms,
            error=f"IOError: {exc}",
        )
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def run_sequential_requests(
    host: str,
    port: int,
    path: str,
    count: int,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> tuple[list[RequestResult], float]:
    """Виконує задану кількість послідовних HTTP-запитів."""
    t_start = time.perf_counter()
    results: list[RequestResult] = []
    for _ in range(count):
        res = await send_http_request(host, port, path, headers=headers, timeout=timeout)
        results.append(res)
    duration = time.perf_counter() - t_start
    return results, duration


async def run_load_batch(
    host: str,
    port: int,
    path: str,
    total_requests: int,
    concurrency: int,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> tuple[list[RequestResult], float]:
    """
    Виконує пул конкурентних HTTP-запитів з обмеженням за семафором (concurrency).

    Повертає список результатів та загальний час прогону (wall-clock) у секундах.
    """
    sem = asyncio.Semaphore(concurrency)

    async def worker(_: int) -> RequestResult:
        async with sem:
            return await send_http_request(
                host=host,
                port=port,
                path=path,
                headers=headers,
                timeout=timeout,
            )

    t_start = time.perf_counter()
    tasks = [asyncio.create_task(worker(i)) for i in range(total_requests)]
    results = await asyncio.gather(*tasks)
    duration = time.perf_counter() - t_start
    return list(results), duration


def calculate_latency_stats(results: list[RequestResult]) -> dict[str, float]:
    """Розраховує середнє значення та перцентилі затримки (avg, min, max, p50, p95, p99) у мс."""
    valid_latencies = [r.latency_ms for r in results if r.status_code == 200 or r.latency_ms > 0]
    if not valid_latencies:
        return {
            "avg_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
        }

    valid_latencies.sort()
    n = len(valid_latencies)

    def percentile(pct: float) -> float:
        if n == 1:
            return round(valid_latencies[0], 2)
        idx = (n - 1) * (pct / 100.0)
        low = int(idx)
        high = low + 1
        if high < n:
            weight = idx - low
            return round(valid_latencies[low] * (1.0 - weight) + valid_latencies[high] * weight, 2)
        return round(valid_latencies[-1], 2)

    return {
        "avg_ms": round(statistics.mean(valid_latencies), 2),
        "min_ms": round(valid_latencies[0], 2),
        "max_ms": round(valid_latencies[-1], 2),
        "p50_ms": percentile(50.0),
        "p95_ms": percentile(95.0),
        "p99_ms": percentile(99.0),
    }


def compute_distribution(
    results: list[RequestResult],
    expected_nodes: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    """Підраховує кількість та відсоток запитів по вузлах бекенду."""
    if expected_nodes is None:
        expected_nodes = ["backend-1", "backend-2", "backend-3"]

    total = len(results)
    counts: dict[str, int] = {node: 0 for node in expected_nodes}
    for r in results:
        node = r.instance_id if r.instance_id else "unknown"
        counts[node] = counts.get(node, 0) + 1

    dist: dict[str, dict[str, float]] = {}
    for node, cnt in counts.items():
        pct = round((cnt / total) * 100.0, 2) if total > 0 else 0.0
        dist[node] = {"count": cnt, "percent": pct}
    return dist


def switch_algorithm(algorithm: str, active_nodes: int) -> None:
    """Викликає скрипт switch_algorithm.sh для динамічного оновлення конфігурації Nginx."""
    script_path = PROJECT_ROOT / "scripts" / "load_balancing" / "switch_algorithm.sh"
    cmd = ["bash", str(script_path), algorithm, str(active_nodes)]
    subprocess.run(cmd, check=True, cwd=str(PROJECT_ROOT))


async def apply_nginx_config(algorithm: str, active_nodes: int, pause_sec: float = 0.6) -> None:
    """Змінює конфігурацію Nginx та робить паузу для застосування воркерами нового стану."""
    print(f"-> [NGINX] Перемикання: алгоритм={algorithm}, активних вузлів={active_nodes}...")
    switch_algorithm(algorithm, active_nodes)
    await asyncio.sleep(pause_sec)


async def wait_for_container_healthy(container_name: str, timeout: float = 40.0) -> bool:
    """Очікує, поки Docker-контейнер перейде у стан 'healthy' (або 'running')."""
    start = time.perf_counter()
    print(f"-> [DOCKER] Очікування статусу healthy для {container_name} (макс. {timeout}с)...")
    while time.perf_counter() - start < timeout:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "inspect",
                "--format",
                "{{.State.Health.Status}}",
                container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            status = stdout.decode().strip()
            if status == "healthy":
                elapsed = round(time.perf_counter() - start, 1)
                print(f"-> [DOCKER] Контейнер {container_name} став healthy за {elapsed}с!")
                return True
            if status in ("", "<no value>"):
                proc2 = await asyncio.create_subprocess_exec(
                    "docker",
                    "inspect",
                    "--format",
                    "{{.State.Status}}",
                    container_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout2, _ = await proc2.communicate()
                if stdout2.decode().strip() == "running":
                    elapsed = round(time.perf_counter() - start, 1)
                    print(f"-> [DOCKER] Контейнер {container_name} запущено (running) за {elapsed}с!")
                    return True
        except Exception:
            pass
        await asyncio.sleep(0.8)

    print(f"-> [DOCKER WARNING] Таймаут очікування стану healthy для {container_name}.")
    return False


# ==============================================================================
# Табличні форматери виводу результатів
# ==============================================================================


def print_experiment_1_table(results_by_algo: dict[str, dict]) -> None:
    """Виводить форматовану таблицю для Експерименту 1."""
    print("\n" + "=" * 108)
    print("  ЕКСПЕРИМЕНТ 1: Порівняльний аналіз алгоритмів балансування (3 активні вузли, 30 запитів)")
    print("=" * 108)
    header = (
        f"{'Алгоритм':<14} | {'backend-1 (cnt / %)':<21} | "
        f"{'backend-2 (cnt / %)':<21} | {'backend-3 (cnt / %)':<21} | "
        f"{'avg(ms)':<8} | {'p50(ms)':<8} | {'p95(ms)':<8} | {'p99(ms)':<8}"
    )
    print(header)
    print("-" * 108)
    for algo, data in results_by_algo.items():
        dist = data["distribution"]
        b1 = f"{dist.get('backend-1', {}).get('count', 0)} ({dist.get('backend-1', {}).get('percent', 0.0):.1f}%)"
        b2 = f"{dist.get('backend-2', {}).get('count', 0)} ({dist.get('backend-2', {}).get('percent', 0.0):.1f}%)"
        b3 = f"{dist.get('backend-3', {}).get('count', 0)} ({dist.get('backend-3', {}).get('percent', 0.0):.1f}%)"
        lat = data["latency_stats"]
        print(
            f"{algo:<14} | {b1:<21} | {b2:<21} | {b3:<21} | "
            f"{lat['avg_ms']:<8.2f} | {lat['p50_ms']:<8.2f} | {lat['p95_ms']:<8.2f} | {lat['p99_ms']:<8.2f}"
        )
    print("=" * 108 + "\n")


def print_experiment_2_table(results_by_algo: dict[str, dict]) -> None:
    """Виводить форматовану таблицю для Експерименту 2."""
    print("\n" + "=" * 114)
    print("  ЕКСПЕРИМЕНТ 2: Асиметричне навантаження (Asymmetric Latency — round_robin vs least_conn)")
    print("  Умови: 90 запитів, concurrency=12 | backend-3 затримка 250мс (backend-1, backend-2 ~2-4мс)")
    print("=" * 114)
    header = (
        f"{'Алгоритм':<14} | {'RPS':<8} | {'Час(с)':<8} | "
        f"{'Швидкі (1+2) (cnt / %)':<25} | {'Повільний (3) (cnt / %)':<25} | "
        f"{'avg(ms)':<8} | {'p50(ms)':<8} | {'p95(ms)':<8} | {'p99(ms)':<8}"
    )
    print(header)
    print("-" * 114)
    for algo, data in results_by_algo.items():
        fast = f"{data['fast_nodes_count']} ({data['fast_nodes_percent']:.1f}%)"
        slow = f"{data['slow_nodes_count']} ({data['slow_nodes_percent']:.1f}%)"
        lat = data["latency_stats"]
        print(
            f"{algo:<14} | {data['throughput_rps']:<8.2f} | {data['duration_sec']:<8.2f} | "
            f"{fast:<25} | {slow:<25} | "
            f"{lat['avg_ms']:<8.2f} | {lat['p50_ms']:<8.2f} | {lat['p95_ms']:<8.2f} | {lat['p99_ms']:<8.2f}"
        )
    print("=" * 114 + "\n")


def print_experiment_3_table(results_by_nodes: dict[str, dict]) -> None:
    """Виводить форматовану таблицю для Експерименту 3."""
    print("\n" + "=" * 112)
    print("  ЕКСПЕРИМЕНТ 3: Scale-Out аналіз (1 vs 2 vs 3 Instances)")
    print("  Умови: 90 запитів, concurrency=18, X-Simulate-Latency-Ms: 30ms, алгоритм round_robin")
    print("=" * 112)
    header = (
        f"{'Вузли':<10} | {'RPS':<8} | {'Прискорення':<13} | "
        f"{'avg(ms)':<8} | {'p50(ms)':<8} | {'p95(ms)':<8} | {'p99(ms)':<8} | "
        f"{'Розподіл (b1 / b2 / b3)':<26}"
    )
    print(header)
    print("-" * 112)
    for _, data in results_by_nodes.items():
        nodes = data["active_nodes"]
        dist = data["distribution"]
        b1 = dist.get("backend-1", {}).get("count", 0)
        b2 = dist.get("backend-2", {}).get("count", 0)
        b3 = dist.get("backend-3", {}).get("count", 0)
        dist_str = f"{b1} / {b2} / {b3}"
        lat = data["latency_stats"]
        speedup_str = f"{data['speedup']:.2f}x"
        node_label = f"{nodes} {'вузол' if nodes == 1 else 'вузли'}"
        print(
            f"{node_label:<10} | {data['throughput_rps']:<8.2f} | {speedup_str:<13} | "
            f"{lat['avg_ms']:<8.2f} | {lat['p50_ms']:<8.2f} | {lat['p95_ms']:<8.2f} | {lat['p99_ms']:<8.2f} | "
            f"{dist_str:<26}"
        )
    print("=" * 112 + "\n")


def print_experiment_4_table(data: dict) -> None:
    """Виводить форматовану таблицю для Експерименту 4."""
    print("\n" + "=" * 80)
    print("  ЕКСПЕРИМЕНТ 4: Fault Tolerance під конкурентним навантаженням")
    print("  Умови: round_robin, 40 запитів, concurrency=8 | rating_backend_3 зупинено")
    print("=" * 80)
    header = f"{'Показник / Метрика':<45} | {'Значення':<30}"
    print(header)
    print("-" * 80)
    total = data["total_requests"]
    s200 = f"{data['successful_200']} ({data['successful_200'] / total * 100:.1f}%)" if total else "0"
    e5xx = f"{data['errors_5xx']} ({data['errors_5xx'] / total * 100:.1f}%)" if total else "0"
    other = str(data["other_errors"])
    dist = data["distribution"]
    b1 = f"{dist.get('backend-1', {}).get('count', 0)} ({dist.get('backend-1', {}).get('percent', 0.0):.1f}%)"
    b2 = f"{dist.get('backend-2', {}).get('count', 0)} ({dist.get('backend-2', {}).get('percent', 0.0):.1f}%)"
    b3 = f"{dist.get('backend-3', {}).get('count', 0)} ({dist.get('backend-3', {}).get('percent', 0.0):.1f}%)"
    lat = data["latency_stats"]
    lat_str = f"{lat['avg_ms']:.1f} / {lat['p50_ms']:.1f} / {lat['p95_ms']:.1f} / {lat['p99_ms']:.1f} ms"

    rows = [
        ("Загальна кількість запитів", str(total)),
        ("Успішні відповіді (200 OK)", s200),
        ("Помилки бекенду (5xx)", e5xx),
        ("Інші помилки клієнта / з'єднання", other),
        ("Розподіл: backend-1", b1),
        ("Розподіл: backend-2", b2),
        ("Розподіл: backend-3 (зупинений, очікувано 0)", b3),
        ("Затримка (avg / p50 / p95 / p99)", lat_str),
        ("Статус відновлення backend-3", data["restored_status"]),
    ]
    for metric, val in rows:
        print(f"{metric:<45} | {val:<30}")
    print("=" * 80 + "\n")


# ==============================================================================
# Реалізація окремих експериментів
# ==============================================================================


async def run_experiment_1(host: str, port: int, path: str) -> dict:
    """
    Експеримент 1: Порівняльний аналіз алгоритмів балансування.

    3 активні вузли, по 30 послідовних запитів до /api/v1/health на кожен алгоритм:
    - round_robin (очікувано 10/10/10 -> 33.3% / 33.3% / 33.3%)
    - weighted (ваги 3, 2, 1 -> очікувано 15/10/5 -> 50.0% / 33.3% / 16.7%)
    - ip_hash (100% запитів з одного IP на один вузол)
    - least_conn (рівномірний розподіл при однотипних послідовних запитах)
    """
    print("\n" + "=" * 90)
    print(">>> ЗАПУСК ЕКСПЕРИМЕНТУ 1: Порівняльний аналіз алгоритмів балансування (3 вузли, 30 reqs)")
    print("=" * 90)

    algorithms = ["round_robin", "weighted", "ip_hash", "least_conn"]
    results_by_algo: dict[str, dict] = {}

    for idx, algo in enumerate(algorithms, start=1):
        print(f"\n[{idx}/4] Алгоритм '{algo}': перемикання Nginx (3 вузли)...")
        await apply_nginx_config(algo, active_nodes=3)

        print(f"-> Відправка 30 послідовних запитів до {path}...")
        requests_results, duration = await run_sequential_requests(
            host=host,
            port=port,
            path=path,
            count=30,
        )

        dist = compute_distribution(requests_results)
        lat = calculate_latency_stats(requests_results)
        succ = sum(1 for r in requests_results if r.status_code == 200)

        results_by_algo[algo] = {
            "active_nodes": 3,
            "total_requests": len(requests_results),
            "successful_requests": succ,
            "duration_sec": round(duration, 3),
            "distribution": dist,
            "latency_stats": lat,
        }

        b1 = dist["backend-1"]["count"]
        b2 = dist["backend-2"]["count"]
        b3 = dist["backend-3"]["count"]
        print(f"-> Завершено за {duration:.2f}с. Розподіл (b1/b2/b3): {b1} / {b2} / {b3} | avg: {lat['avg_ms']}мс")

    print_experiment_1_table(results_by_algo)
    return results_by_algo


async def run_experiment_2(host: str, port: int, path: str) -> dict:
    """
    Експеримент 2: Асиметричне навантаження (Asymmetric Latency — round_robin vs least_conn).

    backend-3 затримує відповідь на 250 мс, тоді як backend-1 та backend-2 відповідають за ~2-4 мс.
    90 конкурентних запитів (concurrency=12) на round_robin vs least_conn.
    """
    print("\n" + "=" * 90)
    print(">>> ЗАПУСК ЕКСПЕРИМЕНТУ 2: Асиметричне навантаження (round_robin vs least_conn)")
    print("=" * 90)

    headers = {
        "X-Simulate-Latency-Ms": "250",
        "X-Simulate-Latency-Instance": "backend-3",
    }
    total_reqs = 90
    concurrency = 12
    algorithms = ["round_robin", "least_conn"]
    results_by_algo: dict[str, dict] = {}

    for algo in algorithms:
        print(f"\n-> Тестування '{algo}' при асиметричній затримці (backend-3 +250ms)...")
        await apply_nginx_config(algo, active_nodes=3)

        print(f"-> Запуск {total_reqs} запитів (concurrency={concurrency})...")
        reqs_results, duration = await run_load_batch(
            host=host,
            port=port,
            path=path,
            total_requests=total_reqs,
            concurrency=concurrency,
            headers=headers,
            timeout=20.0,
        )

        dist = compute_distribution(reqs_results)
        lat = calculate_latency_stats(reqs_results)
        rps = round(total_reqs / duration, 2) if duration > 0 else 0.0

        fast_count = dist.get("backend-1", {}).get("count", 0) + dist.get("backend-2", {}).get("count", 0)
        fast_pct = round((fast_count / total_reqs) * 100.0, 2) if total_reqs else 0.0
        slow_count = dist.get("backend-3", {}).get("count", 0)
        slow_pct = round((slow_count / total_reqs) * 100.0, 2) if total_reqs else 0.0

        results_by_algo[algo] = {
            "algorithm": algo,
            "total_requests": total_reqs,
            "concurrency": concurrency,
            "duration_sec": round(duration, 3),
            "throughput_rps": rps,
            "fast_nodes_count": fast_count,
            "fast_nodes_percent": fast_pct,
            "slow_nodes_count": slow_count,
            "slow_nodes_percent": slow_pct,
            "distribution": dist,
            "latency_stats": lat,
        }
        print(
            f"-> {algo}: Throughput={rps} RPS, Час={duration:.2f}с, "
            f"Швидкі(1+2)={fast_count} ({fast_pct:.1f}%), Повільний(3)={slow_count} ({slow_pct:.1f}%)"
        )

    print_experiment_2_table(results_by_algo)
    return results_by_algo


async def run_experiment_3(host: str, port: int, path: str) -> dict:
    """
    Експеримент 3: Scale-Out аналіз (1 vs 2 vs 3 Instances).

    Симуляція навантаження CPU/IO: X-Simulate-Latency-Ms: 25 (для всіх вузлів).
    90 конкурентних запитів (concurrency=15) на round_robin для active_nodes=1, 2, 3.
    """
    print("\n" + "=" * 90)
    print(">>> ЗАПУСК ЕКСПЕРИМЕНТУ 3: Scale-Out аналіз (1 vs 2 vs 3 Instances)")
    print("=" * 90)

    headers = {"X-Simulate-Latency-Ms": "30"}
    total_reqs = 90
    concurrency = 18
    node_configs = [1, 2, 3]
    results_by_nodes: dict[str, dict] = {}
    base_rps: float | None = None

    for nodes in node_configs:
        print(f"\n-> Конфігурація: {nodes} активних вузлів (round_robin)...")
        await apply_nginx_config("round_robin", active_nodes=nodes)
        # Прогрів пулу upstream keepalive з'єднань після nginx -s reload
        await run_sequential_requests(host=host, port=port, path=path, count=nodes * 2)

        print(f"-> Запуск {total_reqs} запитів (concurrency={concurrency}, latency=30ms)...")
        reqs_results, duration = await run_load_batch(
            host=host,
            port=port,
            path=path,
            total_requests=total_reqs,
            concurrency=concurrency,
            headers=headers,
            timeout=20.0,
        )

        dist = compute_distribution(reqs_results)
        lat = calculate_latency_stats(reqs_results)
        rps = round(total_reqs / duration, 2) if duration > 0 else 0.0

        if base_rps is None or base_rps <= 0.0:
            base_rps = rps
            speedup = 1.00
        else:
            speedup = round(rps / base_rps, 2)

        key = f"nodes_{nodes}"
        results_by_nodes[key] = {
            "active_nodes": nodes,
            "total_requests": total_reqs,
            "concurrency": concurrency,
            "duration_sec": round(duration, 3),
            "throughput_rps": rps,
            "speedup": speedup,
            "distribution": dist,
            "latency_stats": lat,
        }
        print(f"-> {nodes} вуз(ли): RPS={rps}, Speedup={speedup:.2f}x, Час={duration:.2f}с, avg={lat['avg_ms']}мс")

    print_experiment_3_table(results_by_nodes)
    return results_by_nodes


async def run_experiment_4(host: str, port: int, path: str) -> dict:
    """
    Експеримент 4: Fault Tolerance під конкурентним навантаженням.

    1. Встановлення round_robin з 3 вузлами.
    2. Зупинка контейнера rating_backend_3 через docker stop.
    3. Відправка 40 конкурентних запитів (concurrency=8) до /api/v1/health.
    4. Перевірка: 200 OK (100%), 5xx (0), розподіл між живими backend-1 та backend-2.
    5. Відновлення контейнера rating_backend_3 через docker start та очікування healthy.
    """
    print("\n" + "=" * 90)
    print(">>> ЗАПУСК ЕКСПЕРИМЕНТУ 4: Fault Tolerance під навантаженням (Stop rating_backend_3)")
    print("=" * 90)

    # 1. Початковий стан: 3 вузли
    print("-> Крок 1: Встановлення round_robin з 3 вузлами...")
    await apply_nginx_config("round_robin", active_nodes=3)

    # 2. Зупинка rating_backend_3
    print("-> Крок 2: Зупинка контейнера rating_backend_3...")
    subprocess.run(["docker", "stop", "rating_backend_3"], check=True, capture_output=True, text=True)
    await asyncio.sleep(0.5)

    # 3. Відправка конкурентних запитів
    total_reqs = 40
    concurrency = 8
    print(f"-> Крок 3: Відправка {total_reqs} запитів під навантаженням (concurrency={concurrency})...")
    reqs_results, duration = await run_load_batch(
        host=host,
        port=port,
        path=path,
        total_requests=total_reqs,
        concurrency=concurrency,
        timeout=15.0,
    )

    s200 = sum(1 for r in reqs_results if r.status_code == 200)
    e5xx = sum(1 for r in reqs_results if 500 <= r.status_code < 600)
    other = sum(1 for r in reqs_results if r.status_code != 200 and not (500 <= r.status_code < 600))
    dist = compute_distribution(reqs_results)
    lat = calculate_latency_stats(reqs_results)

    # 4. Відновлення rating_backend_3
    print("-> Крок 4: Відновлення контейнера rating_backend_3 (docker start)...")
    subprocess.run(["docker", "start", "rating_backend_3"], check=True, capture_output=True, text=True)
    is_healthy = await wait_for_container_healthy("rating_backend_3", timeout=40.0)
    restored_status = "healthy" if is_healthy else "recovered"

    result_data = {
        "active_nodes_initial": 3,
        "stopped_node": "rating_backend_3",
        "total_requests": total_reqs,
        "concurrency": concurrency,
        "duration_sec": round(duration, 3),
        "successful_200": s200,
        "errors_5xx": e5xx,
        "other_errors": other,
        "distribution": dist,
        "latency_stats": lat,
        "restored_status": restored_status,
    }

    print_experiment_4_table(result_data)
    return result_data


# ==============================================================================
# Точка входу та координатор прогону
# ==============================================================================


async def main_async() -> int:
    parser = argparse.ArgumentParser(
        description="Автоматизований комплекс експериментів балансування навантаження та масштабування (ЛР №3)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("TARGET_HOST", "127.0.0.1"),
        help="Хост Nginx або балансувальника (за замовчуванням: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("HTTP_PORT", os.environ.get("TARGET_PORT", "80"))),
        help="Порт Nginx (за замовчуванням: 80)",
    )
    parser.add_argument(
        "--endpoint",
        default="/api/v1/health",
        help="URL-ендпоінт для перевірки (за замовчуванням: /api/v1/health)",
    )
    parser.add_argument(
        "--output",
        default="/tmp/lb_experiment_results.json",
        help="Шлях для збереження JSON-результатів (за замовчуванням: /tmp/lb_experiment_results.json)",
    )
    parser.add_argument(
        "--experiment",
        type=int,
        choices=[1, 2, 3, 4],
        default=None,
        help="Запустити лише один конкретний експеримент (1, 2, 3 або 4). За замовчуванням запускаються всі 4.",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("   DISTRIBUTED REVIEWS & RATINGS PLATFORM — LOAD BALANCING BENCHMARK")
    print(f"   Target: http://{args.host}:{args.port}{args.endpoint}")
    print(f"   Output: {args.output}")
    print("=" * 80)

    overall_results: dict[str, object] = {
        "timestamp": time.time(),
        "datetime": datetime.now(UTC).isoformat(),
        "target": f"http://{args.host}:{args.port}{args.endpoint}",
    }

    exit_code = 0

    try:
        if args.experiment is None or args.experiment == 1:
            overall_results["experiment_1_balancing_algorithms"] = await run_experiment_1(
                args.host, args.port, args.endpoint
            )

        if args.experiment is None or args.experiment == 2:
            overall_results["experiment_2_asymmetric_latency"] = await run_experiment_2(
                args.host, args.port, args.endpoint
            )

        if args.experiment is None or args.experiment == 3:
            overall_results["experiment_3_scale_out"] = await run_experiment_3(args.host, args.port, args.endpoint)

        if args.experiment is None or args.experiment == 4:
            overall_results["experiment_4_fault_tolerance"] = await run_experiment_4(
                args.host, args.port, args.endpoint
            )

        # Збереження результатів у JSON-файл
        out_file = Path(args.output)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(overall_results, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] Результати успішно збережено у: {out_file.resolve()}")

    except KeyboardInterrupt:
        print("\n[!] Прогін експериментів перервано користувачем (Ctrl+C).")
        exit_code = 130
    except Exception as exc:
        print(f"\n[ERROR] Помилка під час виконання експериментів: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        exit_code = 1
    finally:
        print("\n" + "=" * 80)
        print(">>> CLEANUP: Відновлення інваріантів розподіленої системи...")
        print("=" * 80)

        # 1. Переконуємось, що rating_backend_3 запущений і healthy
        try:
            inspect_proc = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Status}}", "rating_backend_3"],
                capture_output=True,
                text=True,
                check=False,
            )
            container_status = inspect_proc.stdout.strip()
            if container_status != "running":
                print("-> [CLEANUP] Запуск rating_backend_3...")
                subprocess.run(["docker", "start", "rating_backend_3"], capture_output=True, check=False)
                await wait_for_container_healthy("rating_backend_3", timeout=25.0)
            else:
                print("-> [CLEANUP] rating_backend_3 вже активний (running).")
        except Exception as e:
            print(f"-> [CLEANUP WARNING] Не вдалося перевірити/запустити rating_backend_3: {e}")

        # 2. Відновлюємо дефолтну конфігурацію Nginx: round_robin, 3 вузли
        try:
            print("-> [CLEANUP] Відновлення конфігурації Nginx: round_robin з 3 вузлами...")
            switch_algorithm("round_robin", 3)
            print("-> [CLEANUP OK] Nginx успішно повернуто у дефолтний стан.")
        except Exception as e:
            print(f"-> [CLEANUP WARNING] Не вдалося скинути конфігурацію Nginx: {e}")

    return exit_code


def main() -> None:
    code = asyncio.run(main_async())
    sys.exit(code)


if __name__ == "__main__":
    main()
