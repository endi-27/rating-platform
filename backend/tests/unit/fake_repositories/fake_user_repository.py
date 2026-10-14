from uuid import UUID

from src.modules.users.domain import IUserRepository, User


class FakeUserRepository(IUserRepository):
    def __init__(self, initial_users: list[User] | None = None) -> None:
        self.users: dict[UUID, User] = {u.id: u for u in (initial_users or [])}

    async def get_by_id(self, user_id: UUID, /) -> User | None:
        return self.users.get(user_id)

    async def get_by_username(self, username: str) -> User | None:
        for u in self.users.values():
            if u.username.lower() == username.lower():
                return u
        return None

    async def exists_by_username(self, username: str, *, exclude_user_id: UUID | None = None) -> bool:
        return any(
            u.username.lower() == username.lower() and (exclude_user_id is None or u.id != exclude_user_id)
            for u in self.users.values()
        )

    async def save(self, user: User) -> None:
        self.users[user.id] = user

    async def delete_by_id(self, user_id: UUID) -> bool:
        return self.users.pop(user_id, None) is not None
