from src.core import AccountDeactivatedException, InactiveEntityError
from src.modules.users.domain.events import (
    RoleCreatedEvent,
    RoleDeactivatedEvent,
    RoleDeletedEvent,
    RoleRestoredEvent,
    RoleUpdatedEvent,
    UserCreatedEvent,
    UserCredentialsChangedEvent,
    UserDeactivatedEvent,
    UserDeletedEvent,
    UserPasswordChangedEvent,
    UserRestoredEvent,
    UserUpdatedEvent,
    UserUsernameChangedEvent,
)
from src.modules.users.domain.exceptions import (
    InactiveRoleAssignmentError,
    PermissionNotFoundError,
    RoleAlreadyExistsError,
    RoleNotFoundError,
    SelfActionForbiddenError,
    SuperAdminProtectionError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from src.modules.users.domain.interfaces import (
    IAuthSessionGateway,
    IPermissionRepository,
    IRoleRepository,
    IUserRepository,
)
from src.modules.users.domain.models import (
    Permission,
    Role,
    User,
)
from src.modules.users.domain.services import (
    UserSecurityDomainService,
)

__all__ = [
    "AccountDeactivatedException",
    "IAuthSessionGateway",
    "IPermissionRepository",
    "IRoleRepository",
    "IUserRepository",
    "InactiveEntityError",
    "InactiveRoleAssignmentError",
    "Permission",
    "PermissionNotFoundError",
    "Role",
    "RoleAlreadyExistsError",
    "RoleCreatedEvent",
    "RoleDeactivatedEvent",
    "RoleDeletedEvent",
    "RoleNotFoundError",
    "RoleRestoredEvent",
    "RoleUpdatedEvent",
    "SelfActionForbiddenError",
    "SuperAdminProtectionError",
    "User",
    "UserAlreadyExistsError",
    "UserCreatedEvent",
    "UserCredentialsChangedEvent",
    "UserDeactivatedEvent",
    "UserDeletedEvent",
    "UserNotFoundError",
    "UserPasswordChangedEvent",
    "UserRestoredEvent",
    "UserSecurityDomainService",
    "UserUpdatedEvent",
    "UserUsernameChangedEvent",
]
