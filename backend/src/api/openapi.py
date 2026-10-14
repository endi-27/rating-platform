from __future__ import annotations

import enum
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, routing
from fastapi.openapi.utils import _get_api_route_for_openapi, get_openapi


def endpoint_permissions(
    *permissions: str | enum.Enum,
    base: str | enum.Enum | None = None,
    transitions: Mapping[str, str | enum.Enum] | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Формує структуру `openapi_extra` для явного документування дозволів.

    Використовується для стейт-машин та динамічних перевірок прав (Manual Override).
    """
    all_perms: list[str] = []
    base_code: str | None = None
    if base is not None:
        base_code = base.value if isinstance(base, enum.Enum) else base
        all_perms.append(base_code)

    for p in permissions:
        code = p.value if isinstance(p, enum.Enum) else p
        if code not in all_perms:
            all_perms.append(code)

    trans_dict: dict[str, str] = {}
    if transitions:
        for action, perm in transitions.items():
            t_code = perm.value if isinstance(perm, enum.Enum) else perm
            trans_dict[action] = t_code
            if t_code not in all_perms:
                all_perms.append(t_code)

    res: dict[str, Any] = {
        "x-requires-auth": True,
        "x-permissions": all_perms,
    }
    if base_code:
        res["x-required-permission"] = base_code
    elif all_perms:
        res["x-required-permission"] = all_perms[0]
    else:
        res["x-required-permission"] = None

    if trans_dict:
        res["x-state-machine-permissions"] = trans_dict

    if description:
        res["x-permission-description"] = description

    return res


def _inspect_route_auth(dependant: Any) -> tuple[bool, list[str]]:
    """Рекурсивно сканує дерево залежностей Dependant для виявлення вимог автентифікації.

    Повертає (requires_auth: bool, permissions: list[str]).
    """
    requires_auth = False
    perms: list[str] = []

    def _walk(dep: Any) -> None:
        nonlocal requires_auth
        call = getattr(dep, "call", None)
        if call is not None:
            perm = getattr(call, "required_permission", None)
            if perm is not None:
                requires_auth = True
                perm_str = str(perm)
                if perm_str not in perms:
                    perms.append(perm_str)
            elif getattr(call, "__name__", "") == "get_current_user":
                requires_auth = True

        for sub_dep in getattr(dep, "dependencies", []):
            _walk(sub_dep)

    _walk(dependant)
    return requires_auth, perms


def _build_permission_description(
    *,
    requires_auth: bool,
    perms: list[str],
    req_perm: str | None,
    state_machine_perms: dict[str, str] | None,
    original_description: str,
) -> str:
    """Формує Markdown-бейдж з інформацією про дозволи для Swagger UI."""
    if state_machine_perms:
        trans_rows = "\n".join(f"> - `{action}` ➔ `{p}`" for action, p in state_machine_perms.items())
        base_line = f"> 🔒 **Базовий дозвіл:** `{req_perm}`\n" if req_perm else ""
        badge = f"{base_line}> ⚙️ **Дозволи переходів стейт-машини:**\n{trans_rows}\n\n"
    elif perms:
        if len(perms) == 1:
            badge = f"> 🔒 **Необхідний дозвіл (Permission):** `{perms[0]}`\n\n"
        else:
            perms_str = ", ".join(f"`{p}`" for p in perms)
            badge = f"> 🔒 **Необхідні дозволи (Permissions):** {perms_str}\n\n"
    elif requires_auth:
        badge = "> 🔑 **Потрібна автентифікація** *(будь-який авторизований користувач)*\n\n"
    else:
        badge = "> 🌐 **Публічний ендпоінт** *(доступний без авторизації)*\n\n"

    return f"{badge}{original_description}".strip()


def setup_custom_openapi(app: FastAPI) -> None:
    """Налаштовує кастомну схему OpenAPI:

    1. Автоматичне просування специфікаційних розширень параметрів (x-allowed-sorting).
    2. Гібридне документування дозволів (Permissions) та автентифікації:
       - Автодетекшн через require_permission та get_current_user (Zero-Boilerplate).
       - Підтримка явного оверрайду для стейт-машин через openapi_extra / endpoint_permissions.
       - Генерація x-requires-auth, x-required-permission, x-permissions, x-state-machine-permissions.
       - Додавання security: [{"cookieAuth": [...]}, {"bearerAuth": [...]}] та описів помилок 401/403.
       - Візуальні бейджі у Swagger UI description.
    """

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )

        # 1. Реєстрація схем автентифікації в components
        components = openapi_schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        if "cookieAuth" not in security_schemes:
            security_schemes["cookieAuth"] = {
                "type": "apiKey",
                "in": "cookie",
                "name": "access_token",
                "description": "JWT access токен у HttpOnly Cookie",
            }
        if "bearerAuth" not in security_schemes:
            security_schemes["bearerAuth"] = {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "JWT access токен у форматі: Bearer <token>",
            }

        paths = openapi_schema.get("paths", {})

        # 2. Обхід маршрутів застосунку для збагачення метаданими дозволів (Permissions)
        for route_context in routing.iter_route_contexts(app.routes):
            api_route = _get_api_route_for_openapi(route_context)
            if api_route is None:
                continue

            path_format = api_route.path_format
            if path_format not in paths:
                continue

            for method in api_route.methods:
                m = method.lower()
                if m not in paths[path_format]:
                    continue

                operation = paths[path_format][m]
                if not isinstance(operation, dict):
                    continue

                # Перевірка наявності ручного оверрайду (Варіант 3 / Стейт-машини)
                has_manual_override = (
                    "x-permissions" in operation
                    or "x-required-permission" in operation
                    or "x-state-machine-permissions" in operation
                )

                if has_manual_override:
                    requires_auth = bool(operation.get("x-requires-auth", True))
                    raw_perms = operation.get("x-permissions")
                    if raw_perms is not None and isinstance(raw_perms, list):
                        perms = [str(p) for p in raw_perms]
                    elif "x-required-permission" in operation and operation["x-required-permission"]:
                        perms = [str(operation["x-required-permission"])]
                    else:
                        perms = []
                    req_perm = (
                        str(operation["x-required-permission"])
                        if operation.get("x-required-permission")
                        else (perms[0] if perms else None)
                    )
                    state_machine_perms = operation.get("x-state-machine-permissions")
                else:
                    requires_auth, perms = _inspect_route_auth(api_route.dependant)
                    req_perm = perms[0] if perms else None
                    state_machine_perms = None

                # Встановлення машинно-читаних метаданих
                operation["x-requires-auth"] = requires_auth
                operation["x-required-permission"] = req_perm
                operation["x-permissions"] = perms
                if state_machine_perms is not None:
                    operation["x-state-machine-permissions"] = state_machine_perms

                # Налаштування OpenAPI security
                if requires_auth:
                    operation["security"] = [
                        {"cookieAuth": perms},
                        {"bearerAuth": perms},
                    ]
                else:
                    operation["security"] = []

                # Додавання стандартних статусів відповідей
                responses = operation.setdefault("responses", {})
                if requires_auth and "401" not in responses:
                    responses["401"] = {
                        "description": "Потрібна автентифікація для доступу до цього ресурсу.",
                    }
                if (perms or state_machine_perms) and "403" not in responses:
                    if perms:
                        perm_str = ", ".join(f"'{p}'" for p in perms)
                        desc_403 = f"Недостатньо прав доступу (потрібен дозвіл: {perm_str})."
                    else:
                        desc_403 = "Недостатньо прав доступу для виконання цієї операції."
                    responses["403"] = {"description": desc_403}

                # Додавання візуального бейджа у description
                orig_desc = operation.get("description") or ""
                if not (orig_desc.startswith("> 🔒") or orig_desc.startswith("> 🔑") or orig_desc.startswith("> 🌐")):
                    operation["description"] = _build_permission_description(
                        requires_auth=requires_auth,
                        perms=perms,
                        req_perm=req_perm,
                        state_machine_perms=state_machine_perms,
                        original_description=orig_desc,
                    )

        # 3. Підняття x- розширень параметрів (x-allowed-sorting)
        for path_item in paths.values():
            if not isinstance(path_item, dict):
                continue
            for operation in path_item.values():
                if not isinstance(operation, dict):
                    continue
                parameters = operation.get("parameters")
                if not isinstance(parameters, list):
                    continue
                for param in parameters:
                    if not isinstance(param, dict):
                        continue
                    schema = param.get("schema")
                    if isinstance(schema, dict):
                        for key, val in schema.items():
                            if key.startswith("x-"):
                                param[key] = val

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
