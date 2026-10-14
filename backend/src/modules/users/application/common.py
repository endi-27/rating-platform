from collections.abc import Sequence
from uuid import UUID

from src.modules.users.domain import (
    IPermissionRepository,
    Permission,
    PermissionNotFoundError,
)


async def resolve_permissions(
    permission_repo: IPermissionRepository,
    permission_ids: Sequence[UUID] | None,
) -> list[Permission]:
    """
    Завантажує дозволи за списком ID з обов'язковою перевіркою повноти.

    Якщо хоча б один із переданих ідентифікаторів відсутній у базі даних,
    операція переривається винятком PermissionNotFoundError, запобігаючи
    мовчазній втраті прав (silent partial success).
    """
    if not permission_ids:
        return []

    unique_requested_ids = list(dict.fromkeys(permission_ids))
    found_permissions = await permission_repo.get_by_ids(unique_requested_ids)

    found_ids = {p.id for p in found_permissions}
    requested_ids_set = set(unique_requested_ids)

    if len(found_ids) != len(requested_ids_set):
        missing_ids = requested_ids_set - found_ids
        sorted_missing = sorted(str(item_id) for item_id in missing_ids)
        raise PermissionNotFoundError(f"Дозволи з наступними ID не знайдено в системі: {', '.join(sorted_missing)}")

    return found_permissions
