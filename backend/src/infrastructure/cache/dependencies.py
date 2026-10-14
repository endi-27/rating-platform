from __future__ import annotations

from fastapi_cache import FastAPICache

from src.core import logger, settings


def get_cache_dependency_graph() -> dict[str, tuple[str, ...]]:
    """
    Декларативна матриця залежностей просторів імен кешу (Namespace Dependency Graph).
    Визначає каскадну інвалідацію: при зміні сутності в одному просторі автоматично
    очищуються всі залежні від неї простори імен.
    """
    ns = settings.cache.namespace
    return {
        # Користувачі, ролі та дозволи
        ns.permissions: (ns.permissions, ns.roles, ns.users),
        ns.roles: (ns.roles, ns.users),
        ns.users: (ns.users,),
        # Таргети та відгуки
        ns.targets: (ns.targets,),
        ns.reviews: (ns.reviews, ns.targets),
    }


async def clear_cache_with_dependencies(namespace: str) -> list[str]:
    """
    Каскадна інвалідація кешу за матрицею залежностей.
    Очищує цільовий namespace та всі зареєстровані залежні від нього простори імен.
    Повертає список очищених просторів імен.
    """
    graph = get_cache_dependency_graph()
    targets = list(dict.fromkeys(graph.get(namespace, (namespace,))))

    for target in targets:
        try:
            await FastAPICache.clear(namespace=target)
        except Exception as exc:
            logger.warning(
                "Помилка очищення кешу для простору імен '{target}': {err}",
                target=target,
                err=str(exc),
            )

    logger.debug("Очищено кеш для просторів імен: {targets}", targets=targets)
    return targets
