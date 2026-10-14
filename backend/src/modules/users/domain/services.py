from uuid import UUID

from src.modules.users.domain.exceptions import (
    SelfActionForbiddenError,
)


class UserSecurityDomainService:
    """
    Чистий доменний сервіс перевірки повноважень дій між двома сутностями користувачів
    (ініціатор дії / Actor проти цільового користувача / Target).
    """

    @staticmethod
    def ensure_not_self_action(actor_id: UUID, target_id: UUID, action_title: str) -> None:
        """Заборона саморуйнівних дій над власним обліковим записом."""
        if actor_id == target_id or str(actor_id) == str(target_id):
            raise SelfActionForbiddenError(f"Ви не можете {action_title} власний обліковий запис.")

    @staticmethod
    def ensure_not_self_role(
        actor_role_id: UUID,
        target_role_id: UUID,
        action_title: str = "модифікувати",
    ) -> None:
        """Заборона виконання дій над власною призначеною роллю."""
        if actor_role_id == target_role_id or str(actor_role_id) == str(target_role_id):
            raise SelfActionForbiddenError(f"Ви не можете {action_title} власну призначену роль.")
