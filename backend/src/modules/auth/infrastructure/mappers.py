from src.modules.auth.domain import RefreshToken
from src.modules.auth.infrastructure.models import RefreshTokenModel


class RefreshTokenMapper:
    """Мапер між RefreshToken (Domain) та RefreshTokenModel (ORM)."""

    @staticmethod
    def to_domain(model: RefreshTokenModel) -> RefreshToken:
        return RefreshToken(
            id=model.id,
            user_id=model.user_id,
            token_hash=model.token_hash,
            issued_at=model.issued_at,
            expires_at=model.expires_at,
            max_session_expiration=model.max_session_expiration,
            is_revoked=model.is_revoked,
            is_remember_me=model.is_remember_me,
        )

    @staticmethod
    def to_orm(domain: RefreshToken) -> RefreshTokenModel:
        return RefreshTokenModel(
            id=domain.id,
            user_id=domain.user_id,
            token_hash=domain.token_hash,
            issued_at=domain.issued_at,
            expires_at=domain.expires_at,
            max_session_expiration=domain.max_session_expiration,
            is_revoked=domain.is_revoked,
            is_remember_me=domain.is_remember_me,
        )

    @staticmethod
    def update_to_orm(orm: RefreshTokenModel, domain: RefreshToken) -> None:
        """Оновлення мутабельних полів існуючої ORM моделі зі стану доменної сутності."""
        orm.expires_at = domain.expires_at
        orm.max_session_expiration = domain.max_session_expiration
        orm.is_revoked = domain.is_revoked
        orm.is_remember_me = domain.is_remember_me
