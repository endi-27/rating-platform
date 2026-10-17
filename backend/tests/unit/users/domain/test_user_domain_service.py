from uuid import UUID

import pytest
from uuid6 import uuid7

from src.modules.users.domain.exceptions import SelfActionForbiddenError
from src.modules.users.domain.services import UserSecurityDomainService


def test_ensure_not_self_action_happy_path() -> None:
    actor_id = uuid7()
    target_id = uuid7()
    # Should not raise
    UserSecurityDomainService.ensure_not_self_action(actor_id, target_id, "деактивувати")


def test_ensure_not_self_action_raises_on_same_id() -> None:
    user_id = uuid7()
    with pytest.raises(SelfActionForbiddenError) as exc_info:
        UserSecurityDomainService.ensure_not_self_action(user_id, user_id, "деактивувати")
    assert "Ви не можете деактивувати власний обліковий запис." in str(exc_info.value)


def test_ensure_not_self_action_raises_on_same_str_uuid() -> None:
    user_id = uuid7()
    same_id_copy = UUID(str(user_id))
    with pytest.raises(SelfActionForbiddenError) as exc_info:
        UserSecurityDomainService.ensure_not_self_action(user_id, same_id_copy, "видалити")
    assert "Ви не можете видалити власний обліковий запис." in str(exc_info.value)


def test_ensure_not_self_role_happy_path() -> None:
    actor_role_id = uuid7()
    target_role_id = uuid7()
    # Should not raise
    UserSecurityDomainService.ensure_not_self_role(actor_role_id, target_role_id)


def test_ensure_not_self_role_raises_on_same_role() -> None:
    role_id = uuid7()
    with pytest.raises(SelfActionForbiddenError) as exc_info:
        UserSecurityDomainService.ensure_not_self_role(role_id, role_id)
    assert "Ви не можете модифікувати власну призначену роль." in str(exc_info.value)


def test_ensure_not_self_role_raises_with_custom_action_title() -> None:
    role_id = uuid7()
    same_role_copy = UUID(str(role_id))
    with pytest.raises(SelfActionForbiddenError) as exc_info:
        UserSecurityDomainService.ensure_not_self_role(role_id, same_role_copy, "деактивувати")
    assert "Ви не можете деактивувати власну призначену роль." in str(exc_info.value)
