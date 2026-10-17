#!/usr/bin/env python3
"""
Асинхронний тестовий скрипт для проведення експериментів з розподіленим кешуванням (ЛР №4).

Реалізує:
1. Фаза 1: Порівняння Cold vs Hot Latency (Targets endpoint & Rating aggregate endpoint).
   - Розрахунок метрик: avg, p50, p95, p99, min, max, throughput_rps, speedup.
2. Фаза 2: Тестування Event-Driven інвалідації кешу (мутація PUT -> скидання кешу подією).
3. Фаза 3: Graceful Degradation / Fallback Testing (відключення Redis -> X-Cache: FALLBACK -> відновлення).

Автономність:
- Виключно стандартні модулі Python 3 (asyncio, urllib, json, time, statistics, os, sys, subprocess, uuid).
- Форматований кольоровий ANSI вивід.
- Експорт структурованих результатів у JSON (/tmp/cache_experiment_results.json).
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
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


# ANSI кольори та стилі для оформлення термінального виводу
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"

    # Кольори переднього плану
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Яскраві кольори
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Фонові кольори
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"
    BG_RED = "\033[41m"
    BG_YELLOW = "\033[43m"


def colorize(text: str, color_code: str) -> str:
    """Огортає текст у відповідні ANSI escape-послідовності."""
    return f"{color_code}{text}{Colors.RESET}"


@dataclass
class HTTPResponse:
    """Структурована відповідь HTTP-клієнта."""

    status_code: int
    headers: dict[str, str]
    body: str
    latency_ms: float
    instance_id: str = "unknown"
    process_time_ms: float = 0.0
    cache_header: str = ""
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 400

    @property
    def json(self) -> dict[str, Any]:
        try:
            data = json.loads(self.body)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


@dataclass
class BenchmarkStats:
    """Статистичні показники серії HTTP-запитів."""

    count: int = 0
    hits: int = 0
    misses: int = 0
    fallbacks: int = 0
    errors: int = 0
    avg_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    total_time_s: float = 0.0
    throughput_rps: float = 0.0

    @classmethod
    def compute(
        cls,
        responses: list[HTTPResponse],
        wall_time_s: float,
    ) -> BenchmarkStats:
        if not responses:
            return cls()

        count = len(responses)
        latencies = [r.latency_ms for r in responses]
        latencies.sort()

        hits = sum(1 for r in responses if r.cache_header.upper() == "HIT")
        misses = sum(1 for r in responses if r.cache_header.upper() == "MISS")
        fallbacks = sum(1 for r in responses if r.cache_header.upper() == "FALLBACK")
        errors = sum(1 for r in responses if not r.is_success)

        def get_percentile(sorted_list: list[float], pct: float) -> float:
            if not sorted_list:
                return 0.0
            idx = (len(sorted_list) - 1) * (pct / 100.0)
            low = int(idx)
            high = min(low + 1, len(sorted_list) - 1)
            weight = idx - low
            return round(sorted_list[low] * (1.0 - weight) + sorted_list[high] * weight, 2)

        avg_ms = round(statistics.mean(latencies), 2)
        p50_ms = round(statistics.median(latencies), 2)
        p95_ms = get_percentile(latencies, 95.0)
        p99_ms = get_percentile(latencies, 99.0)
        min_ms = round(latencies[0], 2)
        max_ms = round(latencies[-1], 2)

        rps = round(count / wall_time_s, 2) if wall_time_s > 0 else 0.0

        return cls(
            count=count,
            hits=hits,
            misses=misses,
            fallbacks=fallbacks,
            errors=errors,
            avg_ms=avg_ms,
            p50_ms=p50_ms,
            p95_ms=p95_ms,
            p99_ms=p99_ms,
            min_ms=min_ms,
            max_ms=max_ms,
            total_time_s=round(wall_time_s, 3),
            throughput_rps=rps,
        )


def decode_chunked_body(raw_bytes: bytes) -> bytes:
    """Декодує тіло відповіді Transfer-Encoding: chunked."""
    chunks: list[bytes] = []
    pos = 0
    total_len = len(raw_bytes)
    while pos < total_len:
        crlf = raw_bytes.find(b"\r\n", pos)
        if crlf == -1:
            chunks.append(raw_bytes[pos:])
            break
        size_str = raw_bytes[pos:crlf].split(b";")[0].strip()
        if not size_str:
            break
        try:
            chunk_size = int(size_str, 16)
        except ValueError:
            chunks.append(raw_bytes[pos:])
            break
        if chunk_size == 0:
            break
        start_chunk = crlf + 2
        end_chunk = start_chunk + chunk_size
        chunks.append(raw_bytes[start_chunk:end_chunk])
        pos = end_chunk + 2
    return b"".join(chunks)


class AsyncHttpClient:
    """
    Легковажний асинхронний HTTP/1.1 клієнт на базі asyncio.open_connection.

    Не потребує зовнішніх залежностей. Автоматично підтримує Cookie jar,
    заголовки X-Cache, X-Instance-ID, X-Process-Time-Ms та точні таймінги.
    """

    def __init__(self, base_url: str = "http://127.0.0.1") -> None:
        self.base_url = base_url.rstrip("/")
        parsed = urllib.parse.urlsplit(self.base_url)
        self.default_host = parsed.hostname or "127.0.0.1"
        self.default_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self.default_scheme = parsed.scheme or "http"
        self.cookies: dict[str, str] = {}

    def set_cookie(self, key: str, value: str) -> None:
        self.cookies[key] = value

    def clear_cookies(self) -> None:
        self.cookies.clear()

    async def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | str | bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> HTTPResponse:
        """Виконує асинхронний HTTP-запит."""
        if path.startswith("http://") or path.startswith("https://"):
            full_url = path
            parsed = urllib.parse.urlsplit(full_url)
            host = parsed.hostname or self.default_host
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            req_path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        else:
            host = self.default_host
            port = self.default_port
            req_path = path if path.startswith("/") else f"/{path}"

        req_headers: dict[str, str] = {
            "Host": f"{host}:{port}" if port not in (80, 443) else host,
            "User-Agent": "Cache-Benchmark-Suite/1.0",
            "Accept": "application/json",
            "Connection": "close",
        }

        # Cookie jar
        if self.cookies:
            cookie_str = "; ".join(f"{k}={v}" for k, v in self.cookies.items())
            req_headers["Cookie"] = cookie_str

        # Додаткові заголовки
        if headers:
            for k, v in headers.items():
                req_headers[k] = v

        # Серіалізація тіла
        body_bytes = b""
        if body is not None:
            if isinstance(body, (dict, list)):
                body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
                req_headers["Content-Type"] = "application/json; charset=utf-8"
            elif isinstance(body, str):
                body_bytes = body.encode("utf-8")
            elif isinstance(body, bytes):
                body_bytes = body
            req_headers["Content-Length"] = str(len(body_bytes))

        # Побудова HTTP/1.1 запиту
        header_lines = [f"{method.upper()} {req_path} HTTP/1.1"]
        for k, v in req_headers.items():
            header_lines.append(f"{k}: {v}")
        raw_request = "\r\n".join(header_lines).encode("latin1") + b"\r\n\r\n" + body_bytes

        t0 = time.perf_counter()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout,
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return HTTPResponse(
                status_code=0,
                headers={},
                body="",
                latency_ms=elapsed_ms,
                error=f"ConnectionError: {exc}",
            )

        try:
            writer.write(raw_request)
            await asyncio.wait_for(writer.drain(), timeout=timeout)

            chunks: list[bytes] = []
            while True:
                chunk = await asyncio.wait_for(reader.read(8192), timeout=timeout)
                if not chunk:
                    break
                chunks.append(chunk)

            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            raw_response = b"".join(chunks)
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return HTTPResponse(
                status_code=0,
                headers={},
                body="",
                latency_ms=elapsed_ms,
                error=f"IOError: {exc}",
            )
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        # Парсинг HTTP відповіді
        sep = b"\r\n\r\n" if b"\r\n\r\n" in raw_response else b"\n\n"
        if sep in raw_response:
            hdr_part, body_part = raw_response.split(sep, 1)
        else:
            hdr_part, body_part = raw_response, b""

        split_char = b"\r\n" if b"\r\n" in hdr_part else b"\n"
        lines = hdr_part.split(split_char)
        if not lines or not lines[0]:
            return HTTPResponse(
                status_code=0,
                headers={},
                body="",
                latency_ms=elapsed_ms,
                error="EmptyResponse",
            )

        status_line = lines[0].decode("latin1", errors="replace")
        status_parts = status_line.split(" ", 2)
        status_code = int(status_parts[1]) if len(status_parts) > 1 and status_parts[1].isdigit() else 0

        resp_headers: dict[str, str] = {}
        for line in lines[1:]:
            if not line or b":" not in line:
                continue
            k, v = line.split(b":", 1)
            key = k.decode("latin1").strip().lower()
            val = v.decode("latin1").strip()
            resp_headers[key] = val

            # Автоматичне вилучення cookies із Set-Cookie
            if key == "set-cookie":
                cookie_segment = val.split(";")[0].strip()
                if "=" in cookie_segment:
                    c_name, c_val = cookie_segment.split("=", 1)
                    self.cookies[c_name.strip()] = c_val.strip()

        # Декодування chunked при потребі
        if resp_headers.get("transfer-encoding", "").lower() == "chunked":
            body_part = decode_chunked_body(body_part)

        body_str = body_part.decode("utf-8", errors="replace")

        # Вилучення службових заголовків
        instance_id = resp_headers.get("x-instance-id", "unknown")
        process_time_raw = resp_headers.get("x-process-time-ms", "0")
        try:
            process_time_ms = float(process_time_raw)
        except ValueError:
            process_time_ms = 0.0

        cache_header = resp_headers.get("x-cache", "").upper()

        return HTTPResponse(
            status_code=status_code,
            headers=resp_headers,
            body=body_str,
            latency_ms=elapsed_ms,
            instance_id=instance_id,
            process_time_ms=process_time_ms,
            cache_header=cache_header,
        )


def run_command(cmd: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    """Виконує команду оболонки через subprocess та повертає (code, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:
        return 1, "", str(exc)


class CacheBenchmarkSuite:
    """
    Комплексний тест розподіленого кешування (Лабораторна робота №4).
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1",
        username: str = "super_admin",
        password: str = "super_admin",
        hot_requests_count: int = 50,
        concurrency: int = 5,
        fallback_requests_count: int = 20,
        export_path: str = "/tmp/cache_experiment_results.json",
        skip_docker: bool = False,
    ) -> None:
        self.base_url = base_url
        self.username = username
        self.password = password
        self.hot_requests_count = hot_requests_count
        self.concurrency = concurrency
        self.fallback_requests_count = fallback_requests_count
        self.export_path = export_path
        self.skip_docker = skip_docker

        self.client = AsyncHttpClient(base_url)
        self.test_target_id: str | None = None
        self.test_target_slug: str | None = None
        self.test_target_version: int = 1
        self.redis_was_stopped: bool = False

        # Підсумкові результати для збереження
        self.results: dict[str, Any] = {
            "metadata": {
                "timestamp": datetime.now(UTC).isoformat(),
                "base_url": self.base_url,
                "hot_requests_count": self.hot_requests_count,
                "concurrency": self.concurrency,
                "fallback_requests_count": self.fallback_requests_count,
            },
            "phase1_cold_vs_hot": {},
            "phase2_event_invalidation": {},
            "phase3_fallback_degradation": {},
            "summary": {},
            "status": "NOT_STARTED",
        }

    # -------------------------------------------------------------------------
    # Допоміжні методи API
    # -------------------------------------------------------------------------

    async def authenticate(self) -> bool:
        """Автентифікація в системі та отримання access_token cookie."""
        print(colorize("\n[1/4] Автентифікація користувача...", Colors.BOLD + Colors.CYAN))
        login_payload = {
            "username": self.username,
            "password": self.password,
            "is_remember_me": False,
        }
        resp = await self.client.request("POST", "/api/v1/auth/login", body=login_payload)
        if resp.status_code == 200 and "access_token" in self.client.cookies:
            print(
                f"  {colorize('✓', Colors.BRIGHT_GREEN)} Авторизовано як '{self.username}' "
                f"(access_token збережено, час: {resp.latency_ms}ms)"
            )
            return True
        else:
            print(
                f"  {colorize('✗', Colors.BRIGHT_RED)} Помилка авторизації (HTTP {resp.status_code}): {resp.body[:150]}"
            )
            return False

    async def create_test_target(self) -> bool:
        """Створення тестового об'єкта Target."""
        slug_uid = uuid4().hex[:8]
        self.test_target_slug = f"cache-bench-{slug_uid}"
        payload = {
            "slug": self.test_target_slug,
            "title": f"Bench Target {slug_uid}",
            "category": "benchmark",
            "description": "Lab 4 distributed caching latency benchmark target",
            "metadata": {"test_suite": "lab4", "benchmark": True},
        }
        resp = await self.client.request("POST", "/api/v1/targets", body=payload)
        if resp.status_code == 201:
            data = resp.json
            self.test_target_id = data.get("id")
            self.test_target_version = data.get("version", 1)
            print(
                f"  {colorize('✓', Colors.BRIGHT_GREEN)} Тестовий Target створено: "
                f"id={self.test_target_id}, slug={self.test_target_slug}, version={self.test_target_version}"
            )
            return True
        else:
            print(
                f"  {colorize('✗', Colors.BRIGHT_RED)} Не вдалося створити Target (HTTP {resp.status_code}): "
                f"{resp.body[:150]}"
            )
            return False

    async def delete_test_target(self) -> None:
        """Видалення тестового Target."""
        if not self.test_target_id:
            return
        resp = await self.client.request("DELETE", f"/api/v1/targets/{self.test_target_id}")
        if resp.status_code in (200, 204):
            print(f"  {colorize('✓', Colors.BRIGHT_GREEN)} Тестовий Target {self.test_target_id} успішно видалено.")
        else:
            print(f"  {colorize('!', Colors.YELLOW)} Видалення Target повернуло код HTTP {resp.status_code}")

    # -------------------------------------------------------------------------
    # Робота з Docker (Керування станом Redis)
    # -------------------------------------------------------------------------

    def stop_redis(self) -> bool:
        """Зупинка контейнера Redis."""
        print(f"  {colorize('⚡', Colors.YELLOW)} Зупинка контейнера 'rating_redis' (docker stop)...")
        code, out, err = run_command(["docker", "stop", "rating_redis"])
        if code == 0:
            self.redis_was_stopped = True
            print(f"  {colorize('✓', Colors.BRIGHT_GREEN)} Контейнер 'rating_redis' зупинено.")
            return True
        else:
            print(f"  {colorize('✗', Colors.BRIGHT_RED)} Помилка зупинки Redis: {err or out}")
            return False

    def start_redis(self) -> bool:
        """Запуск контейнера Redis."""
        print(f"  {colorize('⚡', Colors.CYAN)} Відновлення роботи Redis (docker start rating_redis)...")
        code, out, err = run_command(["docker", "start", "rating_redis"])
        if code == 0:
            print(f"  {colorize('✓', Colors.BRIGHT_GREEN)} Контейнер 'rating_redis' запущено.")
            return True
        else:
            print(f"  {colorize('✗', Colors.BRIGHT_RED)} Помилка запуску Redis: {err or out}")
            return False

    def wait_redis_healthy(self, timeout_sec: int = 30) -> bool:
        """Очікування переходу контейнера Redis у стан healthy."""
        print(f"  {colorize('⏳', Colors.CYAN)} Очікування переходу Redis у стан 'healthy' (до {timeout_sec}s)...")
        t_start = time.perf_counter()
        while time.perf_counter() - t_start < timeout_sec:
            code, out, _ = run_command(["docker", "inspect", "--format={{.State.Health.Status}}", "rating_redis"])
            status = out.strip().lower()
            if status == "healthy":
                self.redis_was_stopped = False
                elapsed = round(time.perf_counter() - t_start, 1)
                print(f"  {colorize('✓', Colors.BRIGHT_GREEN)} Redis готовий до роботи (healthy, {elapsed}s).")
                return True
            time.sleep(1)
        print(f"  {colorize('✗', Colors.BRIGHT_RED)} Таймаут очікування 'healthy' для Redis!")
        return False

    # -------------------------------------------------------------------------
    # Генерація навантаження
    # -------------------------------------------------------------------------

    async def execute_batch(
        self,
        path: str,
        count: int,
        concurrency: int = 5,
        desc: str = "Batch",
    ) -> tuple[list[HTTPResponse], BenchmarkStats]:
        """Виконує пакет конкурентних або послідовних запитів із контролем concurrency."""
        sem = asyncio.Semaphore(concurrency)
        responses: list[HTTPResponse] = []

        async def worker(idx: int) -> HTTPResponse:
            async with sem:
                return await self.client.request("GET", path)

        t_start = time.perf_counter()
        tasks = [asyncio.create_task(worker(i)) for i in range(count)]
        responses = await asyncio.gather(*tasks)
        wall_time = time.perf_counter() - t_start

        stats = BenchmarkStats.compute(responses, wall_time)
        return responses, stats

    # -------------------------------------------------------------------------
    # Фаза 1: Порівняння Cold vs Hot Latency
    # -------------------------------------------------------------------------

    async def run_phase_1(self) -> bool:
        """
        Фаза 1: Cold vs Hot Latency Comparison
        1. Target Details: 1st Cold (MISS) vs 50 Hot (HIT)
        2. Target Rating: 1st Cold (MISS) vs 50 Hot (HIT)
        3. Розрахунок Speedup (cold_latency / hot_latency_avg).
        """
        print(
            colorize(
                "\n" + "=" * 80 + "\n ФАЗА 1: Порівняння Cold vs Hot Latency (Redis Caching Benchmark)\n" + "=" * 80,
                Colors.BOLD + Colors.BLUE,
            )
        )

        target_url = f"/api/v1/targets/{self.test_target_id}"
        rating_url = f"/api/v1/targets/{self.test_target_id}/rating"

        # ---------------------------------------------------------
        # 1.1 Target Endpoint: Cold Request
        # ---------------------------------------------------------
        print(colorize("\n[1.1] Target Details: 1-й Cold Request (очікується X-Cache: MISS)", Colors.BOLD))
        cold_target_resp = await self.client.request("GET", target_url)
        is_cold_miss = cold_target_resp.cache_header.upper() == "MISS"
        status_icon = (
            colorize("✓ PASSED", Colors.BRIGHT_GREEN) if is_cold_miss else colorize("✗ FAILED", Colors.BRIGHT_RED)
        )

        print(
            f"  Статус: {cold_target_resp.status_code} | "
            f"X-Cache: {colorize(cold_target_resp.cache_header or 'NONE', Colors.YELLOW)} | "
            f"Latency: {cold_target_resp.latency_ms}ms | {status_icon}"
        )

        # ---------------------------------------------------------
        # 1.2 Target Endpoint: 50 Hot Requests
        # ---------------------------------------------------------
        print(
            colorize(
                f"\n[1.2] Target Details: Серія з {self.hot_requests_count} Hot Requests "
                f"(concurrency={self.concurrency}, очікується X-Cache: HIT)",
                Colors.BOLD,
            )
        )
        _, hot_target_stats = await self.execute_batch(
            target_url,
            count=self.hot_requests_count,
            concurrency=self.concurrency,
            desc="Hot Target",
        )

        speedup_target = (
            round(cold_target_resp.latency_ms / hot_target_stats.avg_ms, 2) if hot_target_stats.avg_ms > 0 else 0.0
        )

        # ---------------------------------------------------------
        # 1.3 Target Rating Endpoint: Cold Request
        # ---------------------------------------------------------
        print(colorize("\n[1.3] Target Rating: 1-й Cold Request (очікується X-Cache: MISS)", Colors.BOLD))
        cold_rating_resp = await self.client.request("GET", rating_url)
        is_rating_cold_miss = cold_rating_resp.cache_header.upper() == "MISS"
        status_rating_icon = (
            colorize("✓ PASSED", Colors.BRIGHT_GREEN)
            if is_rating_cold_miss
            else colorize("✗ FAILED", Colors.BRIGHT_RED)
        )

        print(
            f"  Статус: {cold_rating_resp.status_code} | "
            f"X-Cache: {colorize(cold_rating_resp.cache_header or 'NONE', Colors.YELLOW)} | "
            f"Latency: {cold_rating_resp.latency_ms}ms | {status_rating_icon}"
        )

        # ---------------------------------------------------------
        # 1.4 Target Rating Endpoint: 50 Hot Requests
        # ---------------------------------------------------------
        print(
            colorize(
                f"\n[1.4] Target Rating: Серія з {self.hot_requests_count} Hot Requests "
                f"(concurrency={self.concurrency}, очікується X-Cache: HIT)",
                Colors.BOLD,
            )
        )
        _, hot_rating_stats = await self.execute_batch(
            rating_url,
            count=self.hot_requests_count,
            concurrency=self.concurrency,
            desc="Hot Rating",
        )

        speedup_rating = (
            round(cold_rating_resp.latency_ms / hot_rating_stats.avg_ms, 2) if hot_rating_stats.avg_ms > 0 else 0.0
        )

        # ---------------------------------------------------------
        # Таблиця результатів Фази 1
        # ---------------------------------------------------------
        print(colorize("\n┌" + "─" * 78 + "┐", Colors.CYAN))
        print(
            colorize(
                f"│ {'Ендпоінт':<22} │ {'Cold Lat':<9} │ {'Hot Avg':<9} │ {'p50 / p95':<13} │ {'RPS':<8} │ {'Speedup':<7} │",  # noqa: E501
                Colors.BOLD + Colors.CYAN,
            )
        )
        print(colorize("├" + "─" * 78 + "┤", Colors.CYAN))

        target_p = f"{hot_target_stats.p50_ms}/{hot_target_stats.p95_ms}ms"
        print(
            f"│ {'GET /targets/{id}':<22} │ "
            f"{cold_target_resp.latency_ms:>7}ms │ "
            f"{hot_target_stats.avg_ms:>7}ms │ "
            f"{target_p:>13} │ "
            f"{hot_target_stats.throughput_rps:>8} │ "
            f"{colorize(f'{speedup_target}x', Colors.BRIGHT_GREEN):>16} │"
        )

        rating_p = f"{hot_rating_stats.p50_ms}/{hot_rating_stats.p95_ms}ms"
        print(
            f"│ {'GET .../rating':<22} │ "
            f"{cold_rating_resp.latency_ms:>7}ms │ "
            f"{hot_rating_stats.avg_ms:>7}ms │ "
            f"{rating_p:>13} │ "
            f"{hot_rating_stats.throughput_rps:>8} │ "
            f"{colorize(f'{speedup_rating}x', Colors.BRIGHT_GREEN):>16} │"
        )
        print(colorize("└" + "─" * 78 + "┘", Colors.CYAN))

        # Збереження результатів
        self.results["phase1_cold_vs_hot"] = {
            "target_details": {
                "cold": {
                    "status_code": cold_target_resp.status_code,
                    "cache_header": cold_target_resp.cache_header,
                    "latency_ms": cold_target_resp.latency_ms,
                    "is_miss": is_cold_miss,
                },
                "hot": asdict(hot_target_stats),
                "speedup": speedup_target,
            },
            "target_rating": {
                "cold": {
                    "status_code": cold_rating_resp.status_code,
                    "cache_header": cold_rating_resp.cache_header,
                    "latency_ms": cold_rating_resp.latency_ms,
                    "is_miss": is_rating_cold_miss,
                },
                "hot": asdict(hot_rating_stats),
                "speedup": speedup_rating,
            },
        }

        success = is_cold_miss and is_rating_cold_miss and hot_target_stats.hits > 0
        return success

    # -------------------------------------------------------------------------
    # Фаза 2: Тестування Event-Driven інвалідації кешу
    # -------------------------------------------------------------------------

    async def run_phase_2(self) -> bool:
        """
        Фаза 2: Event-Driven Cache Invalidation
        1. Виконати PUT /api/v1/targets/{id} із новим title.
        2. Зробити наступний GET /api/v1/targets/{id}: перевірити X-Cache: MISS та новий title.
        3. Зробити ще один GET /api/v1/targets/{id}: перевірити X-Cache: HIT.
        """
        print(
            colorize(
                "\n" + "=" * 80 + "\n ФАЗА 2: Тестування Event-Driven інвалідації кешу Redis\n" + "=" * 80,
                Colors.BOLD + Colors.BLUE,
            )
        )

        target_url = f"/api/v1/targets/{self.test_target_id}"
        new_title = f"Updated Benchmark Target [{uuid4().hex[:6]}]"

        print(colorize("\n[2.1] Виконання мутації: PUT /api/v1/targets/{id}", Colors.BOLD))
        update_payload = {
            "title": new_title,
            "category": "benchmark",
            "description": "Target description after event-driven invalidation",
            "metadata": {"test_suite": "lab4", "updated": True},
            "version": self.test_target_version,
        }

        put_resp = await self.client.request("PUT", target_url, body=update_payload)
        if put_resp.status_code != 200:
            print(
                f"  {colorize('✗ FAILED', Colors.BRIGHT_RED)} Помилка оновлення об'єкта (HTTP {put_resp.status_code}): "
                f"{put_resp.body[:150]}"
            )
            return False

        updated_data = put_resp.json
        self.test_target_version = updated_data.get("version", self.test_target_version + 1)
        print(
            f"  {colorize('✓', Colors.BRIGHT_GREEN)} Об'єкт оновлено (HTTP 200). "
            f"Нова назва: '{new_title}', версія: {self.test_target_version}"
        )

        # ---------------------------------------------------------
        # 2.2 Перевірка скидання кешу (очікується MISS і актуальні дані)
        # ---------------------------------------------------------
        print(colorize("\n[2.2] Перевірка інвалідації: GET /api/v1/targets/{id} після мутації", Colors.BOLD))
        get_post_mutation = await self.client.request("GET", target_url)
        data_post = get_post_mutation.json

        is_miss = get_post_mutation.cache_header.upper() == "MISS"
        is_title_updated = data_post.get("title") == new_title

        check_miss_icon = (
            colorize("✓ MISS", Colors.BRIGHT_GREEN) if is_miss else colorize("✗ NOT MISS", Colors.BRIGHT_RED)
        )
        check_title_icon = (
            colorize("✓ MATCH", Colors.BRIGHT_GREEN) if is_title_updated else colorize("✗ MISMATCH", Colors.BRIGHT_RED)
        )

        print(
            f"  Статус: {get_post_mutation.status_code} | "
            f"X-Cache: {get_post_mutation.cache_header} ({check_miss_icon}) | "
            f"Оновлений title: {check_title_icon} | "
            f"Latency: {get_post_mutation.latency_ms}ms"
        )

        # ---------------------------------------------------------
        # 2.3 Перевірка повторного наповнення кешу (очікується HIT)
        # ---------------------------------------------------------
        print(colorize("\n[2.3] Перевірка повторного кешування: GET /api/v1/targets/{id}", Colors.BOLD))
        get_subsequent = await self.client.request("GET", target_url)
        is_hit = get_subsequent.cache_header.upper() == "HIT"
        check_hit_icon = colorize("✓ HIT", Colors.BRIGHT_GREEN) if is_hit else colorize("✗ NOT HIT", Colors.BRIGHT_RED)

        print(
            f"  Статус: {get_subsequent.status_code} | "
            f"X-Cache: {get_subsequent.cache_header} ({check_hit_icon}) | "
            f"Latency: {get_subsequent.latency_ms}ms"
        )

        phase2_passed = is_miss and is_title_updated and is_hit
        verdict = colorize("PASSED", Colors.BRIGHT_GREEN) if phase2_passed else colorize("FAILED", Colors.BRIGHT_RED)
        print(f"\n  Підсумок Фази 2: {verdict}")

        self.results["phase2_event_invalidation"] = {
            "mutation_put_status": put_resp.status_code,
            "post_mutation_get": {
                "status_code": get_post_mutation.status_code,
                "cache_header": get_post_mutation.cache_header,
                "latency_ms": get_post_mutation.latency_ms,
                "is_miss": is_miss,
                "title_matched": is_title_updated,
            },
            "subsequent_get": {
                "status_code": get_subsequent.status_code,
                "cache_header": get_subsequent.cache_header,
                "latency_ms": get_subsequent.latency_ms,
                "is_hit": is_hit,
            },
            "passed": phase2_passed,
        }

        return phase2_passed

    # -------------------------------------------------------------------------
    # Фаза 3: Graceful Degradation / Fallback Testing
    # -------------------------------------------------------------------------

    async def run_phase_3(self) -> bool:
        """
        Фаза 3: Graceful Degradation / Fallback Testing
        1. docker stop rating_redis
        2. Серія з 20 запитів: перевірка 200 OK (0% 5xx) та X-Cache: FALLBACK
        3. docker start rating_redis + очікування healthy
        4. Запит до GET: перевірка відновлення кешу (MISS -> HIT).
        """
        print(
            colorize(
                "\n" + "=" * 80 + "\n"
                " ФАЗА 3: Graceful Degradation та Fallback-тестування при відмові Redis\n" + "=" * 80,
                Colors.BOLD + Colors.BLUE,
            )
        )

        if self.skip_docker:
            print(colorize("  [!] Пропущено через прапорець --skip-docker.", Colors.YELLOW))
            self.results["phase3_fallback_degradation"] = {"skipped": True}
            return True

        target_url = f"/api/v1/targets/{self.test_target_id}"

        # ---------------------------------------------------------
        # 3.1 Зупинка Redis
        # ---------------------------------------------------------
        print(colorize("\n[3.1] Симуляція відмови розподіленого кешу:", Colors.BOLD))
        if not self.stop_redis():
            return False

        # Невелика пауза для фіксації відсутності сокета
        await asyncio.sleep(1.0)

        # ---------------------------------------------------------
        # 3.2 Серія з fallback_requests_count запитів
        # ---------------------------------------------------------
        print(
            colorize(
                f"\n[3.2] Навантаження в режимі Fallback: {self.fallback_requests_count} запитів "
                f"(очікується 0% 5xx, заголовок X-Cache: FALLBACK)",
                Colors.BOLD,
            )
        )

        responses, fallback_stats = await self.execute_batch(
            target_url,
            count=self.fallback_requests_count,
            concurrency=2,
            desc="Fallback Batch",
        )

        # Перевірка результатів Fallback
        all_200 = all(r.status_code == 200 for r in responses)
        all_fallback = all(r.cache_header.upper() == "FALLBACK" for r in responses)
        fallback_ratio = (
            round((fallback_stats.fallbacks / fallback_stats.count) * 100.0, 1) if fallback_stats.count > 0 else 0.0
        )

        icon_200 = (
            colorize("✓ 100% 200 OK", Colors.BRIGHT_GREEN)
            if all_200
            else colorize(f"✗ {fallback_stats.errors} помилок", Colors.BRIGHT_RED)
        )
        icon_fb = (
            colorize(f"✓ {fallback_ratio}% FALLBACK", Colors.BRIGHT_GREEN)
            if all_fallback
            else colorize(f"✗ {fallback_ratio}% FALLBACK", Colors.BRIGHT_RED)
        )

        print(
            f"  Успішність HTTP: {icon_200} | Статус кешу: {icon_fb} | Fallback Avg Latency: {fallback_stats.avg_ms}ms"
        )

        # ---------------------------------------------------------
        # 3.3 Відновлення Redis
        # ---------------------------------------------------------
        print(colorize("\n[3.3] Відновлення роботи кластера Redis:", Colors.BOLD))
        if not self.start_redis():
            return False

        if not self.wait_redis_healthy(timeout_sec=30):
            return False

        # Пауза для відновлення пулу з'єднань у бекендах
        await asyncio.sleep(1.5)

        # ---------------------------------------------------------
        # 3.4 Перевірка повернення до штатного кешування
        # ---------------------------------------------------------
        print(colorize("\n[3.4] Валідація самовідновлення (Self-Healing Cache):", Colors.BOLD))
        recovery_1 = await self.client.request("GET", target_url)
        print(
            f"  1-й запит після рестарту: HTTP {recovery_1.status_code} | "
            f"X-Cache: {colorize(recovery_1.cache_header, Colors.YELLOW)} | "
            f"Latency: {recovery_1.latency_ms}ms"
        )

        recovery_2 = await self.client.request("GET", target_url)
        is_recovered_hit = recovery_2.cache_header.upper() == "HIT"
        icon_rec = (
            colorize("✓ HIT (КЕШ ВІДНОВЛЕНО)", Colors.BRIGHT_GREEN)
            if is_recovered_hit
            else colorize("✗ NOT HIT", Colors.BRIGHT_RED)
        )

        print(
            f"  2-й запит після рестарту: HTTP {recovery_2.status_code} | "
            f"X-Cache: {colorize(recovery_2.cache_header, Colors.BRIGHT_GREEN)} | "
            f"Latency: {recovery_2.latency_ms}ms | {icon_rec}"
        )

        phase3_passed = all_200 and all_fallback and is_recovered_hit
        verdict = colorize("PASSED", Colors.BRIGHT_GREEN) if phase3_passed else colorize("FAILED", Colors.BRIGHT_RED)
        print(f"\n  Підсумок Фази 3: {verdict}")

        self.results["phase3_fallback_degradation"] = {
            "all_200_ok": all_200,
            "all_fallback_headers": all_fallback,
            "fallback_stats": asdict(fallback_stats),
            "recovered_to_hit": is_recovered_hit,
            "passed": phase3_passed,
        }

        return phase3_passed

    # -------------------------------------------------------------------------
    # Загальний запуск тестів
    # -------------------------------------------------------------------------

    async def run(self) -> bool:
        """Повний цикл виконання бенчмарк-сюїти."""
        banner = (
            "\n" + "#" * 80 + "\n"
            "#  DISTRIBUTED REVIEWS & RATINGS PLATFORM — LAB 4 CACHING BENCHMARK SUITE       #\n"
            "#" * 80
        )
        print(colorize(banner, Colors.BOLD + Colors.BRIGHT_CYAN))
        print(f"  Час старту: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  Base URL:   {self.base_url}")
        print(
            f"  Параметри:  Hot Requests: {self.hot_requests_count}, Concurrency: {self.concurrency}, Fallback Requests: {self.fallback_requests_count}"  # noqa: E501
        )

        overall_success = False
        try:
            # 1. Авторизація
            if not await self.authenticate():
                self.results["status"] = "AUTH_FAILED"
                return False

            # 2. Створення цільового об'єкта
            if not await self.create_test_target():
                self.results["status"] = "TARGET_CREATION_FAILED"
                return False

            # 3. Фаза 1
            p1_ok = await self.run_phase_1()

            # 4. Фаза 2
            p2_ok = await self.run_phase_2()

            # 5. Фаза 3
            p3_ok = await self.run_phase_3()

            overall_success = p1_ok and p2_ok and p3_ok
            self.results["status"] = "PASSED" if overall_success else "FAILED"

        finally:
            # Блок гарантованого відновлення та очищення
            print(colorize("\n[4/4] Завершення та очищення середовища...", Colors.BOLD + Colors.CYAN))
            if self.redis_was_stopped:
                print(colorize("  [!] Виявлено зупинений Redis під час cleanup. Відновлення...", Colors.YELLOW))
                self.start_redis()
                self.wait_redis_healthy(15)

            await self.delete_test_target()

            # Експорт результатів у JSON
            self.export_results()

        # Фінальний звіт у консоль
        self.print_final_summary(overall_success)
        return overall_success

    def export_results(self) -> None:
        """Зберігає структуровані результати у JSON-файл."""
        try:
            export_dir = os.path.dirname(self.export_path)
            if export_dir and not os.path.exists(export_dir):
                os.makedirs(export_dir, exist_ok=True)

            with open(self.export_path, "w", encoding="utf-8") as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            print(f"  {colorize('✓', Colors.BRIGHT_GREEN)} Результати експортовано у: {self.export_path}")
        except Exception as exc:
            print(f"  {colorize('!', Colors.RED)} Помилка запису файлу {self.export_path}: {exc}")

    def print_final_summary(self, success: bool) -> None:
        """Виводить фінальну підсумкову таблицю та вердикт."""
        p1 = self.results.get("phase1_cold_vs_hot", {})
        p2 = self.results.get("phase2_event_invalidation", {})
        p3 = self.results.get("phase3_fallback_degradation", {})

        p1_speedup = p1.get("target_details", {}).get("speedup", 0.0)
        p1_rating_speedup = p1.get("target_rating", {}).get("speedup", 0.0)

        print("\n" + "=" * 80)
        print(colorize(" ПІДСУМКОВИЙ ЗВІТ ЕКСПЕРИМЕНТУ (LAB 4 CACHING SUITE)", Colors.BOLD + Colors.CYAN))
        print("=" * 80)
        print(
            f"  1. Cold vs Hot Latency:      Target Speedup: {colorize(f'{p1_speedup}x', Colors.BRIGHT_GREEN)} | Rating Speedup: {colorize(f'{p1_rating_speedup}x', Colors.BRIGHT_GREEN)}"  # noqa: E501
        )
        print(
            f"  2. Event-Driven Invalidate:  {colorize('УСПІШНО (MISS -> HIT)', Colors.BRIGHT_GREEN) if p2.get('passed') else colorize('НЕ ВДАЛОСЯ', Colors.BRIGHT_RED)}"  # noqa: E501
        )
        print(
            f"  3. Graceful Fallback (Redis): {colorize('УСПІШНО (100% 200 OK + FALLBACK -> RECOVERED)', Colors.BRIGHT_GREEN) if p3.get('passed') else colorize('НЕ ВДАЛОСЯ', Colors.BRIGHT_RED)}"  # noqa: E501
        )
        print("-" * 80)

        if success:
            verdict_badge = colorize(
                "  ✓ ВСІ ТЕСТИ ЛАБОРАТОРНОЇ РОБОТИ №4 УСПІШНО ПРОЙДЕНО  ", Colors.BOLD + Colors.BG_GREEN + Colors.WHITE
            )
        else:
            verdict_badge = colorize(
                "  ✗ ТЕСТУВАННЯ ЗАВЕРШИЛОСЯ З ПОМИЛКАМИ  ", Colors.BOLD + Colors.BG_RED + Colors.WHITE
            )
        print(f"\n{verdict_badge}\n")


# -----------------------------------------------------------------------------
# Точка входу в CLI
# -----------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark Suite для Лабораторної роботи №4: Розподілене кешування (Pure Python 3)."
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("BASE_URL", "http://127.0.0.1"),
        help="Базовий URL платформи (за замовчуванням: http://127.0.0.1 або $BASE_URL)",
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("SUPERADMIN_USER", "super_admin"),
        help="Логін адміністратора (за замовчуванням: super_admin або $SUPERADMIN_USER)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("SUPERADMIN_PASSWORD", "super_admin"),
        help="Пароль адміністратора (за замовчуванням: super_admin або $SUPERADMIN_PASSWORD)",
    )
    parser.add_argument(
        "--hot-requests",
        type=int,
        default=50,
        help="Кількість гарячих запитів у Фазі 1 (за замовчуванням: 50)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Рівень конкурентності для пакетних запитів (за замовчуванням: 5)",
    )
    parser.add_argument(
        "--fallback-requests",
        type=int,
        default=20,
        help="Кількість запитів у режимі Fallback у Фазі 3 (за замовчуванням: 20)",
    )
    parser.add_argument(
        "--export-file",
        default="/tmp/cache_experiment_results.json",
        help="Шлях до JSON-файлу для збереження результатів (за замовчуванням: /tmp/cache_experiment_results.json)",
    )
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Пропустити фазу зупинки/запуску контейнера Redis (для середовищ без Docker CLI)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    suite = CacheBenchmarkSuite(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        hot_requests_count=args.hot_requests,
        concurrency=args.concurrency,
        fallback_requests_count=args.fallback_requests,
        export_path=args.export_file,
        skip_docker=args.skip_docker,
    )
    success = asyncio.run(suite.run())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
