from uuid import UUID

from uuid6 import uuid7

from src.core import CurrentUser, CurrentUserRole, IUnitOfWork, UserAlreadyExistsException
from src.modules.auth.domain import IUserAuthGateway
from src.modules.users import UserCredentialsDTO
from src.modules.users.domain.models import Role, User
from tests.unit.fake_repositories.fake_user_repository import FakeUserRepository


class FakeUserAuthGateway(IUserAuthGateway):
    def __init__(self, user_repo: FakeUserRepository) -> None:
        self._user_repo = user_repo

    async def get_credentials_by_username(self, username: str) -> UserCredentialsDTO | None:
        user = await self._user_repo.get_by_username(username)
        if not user:
            return None
        return UserCredentialsDTO(
            id=user.id,
            username=user.username,
            password_hash=user.password_hash,
            role_code=user.role.code if user.role else "",
            is_active=user.is_active,
        )

    async def get_credentials_by_id(self, user_id: UUID) -> UserCredentialsDTO | None:
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            return None
        return UserCredentialsDTO(
            id=user.id,
            username=user.username,
            password_hash=user.password_hash,
            role_code=user.role.code if user.role else "",
            is_active=user.is_active,
        )

    async def get_cached_current_user(self, user_id: UUID) -> CurrentUser | None:
        user = await self._user_repo.get_by_id(user_id)
        if not user:
            return None
        return CurrentUser(
            id=user.id,
            username=user.username,
            name=user.name,
            role_id=user.role_id,
            role=CurrentUserRole(
                id=user.role.id,
                code=user.role.code,
                name=user.role.name,
            )
            if user.role
            else None,
            effective_permissions=user.effective_permissions,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    async def register_public_user(
        self,
        username: str,
        name: str,
        password: str,
        *,
        external_uow: IUnitOfWork | None = None,
    ) -> UserCredentialsDTO:
        if await self._user_repo.exists_by_username(username):
            raise UserAlreadyExistsException(f"Користувач з логіном '{username}' вже існує.")

        role = Role(id=uuid7(), code="user", name="Користувач")
        user = User.register(
            username=username,
            name=name,
            password_hash=password + "_hash",
            role=role,
        )
        await self._user_repo.save(user)
        return UserCredentialsDTO(
            id=user.id,
            username=user.username,
            password_hash=user.password_hash,
            role_code=role.code,
            is_active=user.is_active,
        )
