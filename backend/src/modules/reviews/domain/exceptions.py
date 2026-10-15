from uuid import UUID

from src.core.exceptions import ConflictException, DomainException, NotFoundException


class TargetNotFoundException(NotFoundException):
    """Об'єкт оцінювання (Target) не знайдено."""

    default_error_code = "TARGET_NOT_FOUND"
    default_message = "Об'єкт оцінювання не знайдено."

    def __init__(self, target_id_or_slug: UUID | str) -> None:
        super().__init__(
            message=f"Об'єкт оцінювання '{target_id_or_slug}' не знайдено.",
            details={"target": str(target_id_or_slug)},
        )


class TargetSlugAlreadyExistsException(ConflictException):
    """Спроба створити об'єкт оцінювання з уже зайнятим slug."""

    default_error_code = "TARGET_SLUG_ALREADY_EXISTS"
    default_message = "Об'єкт з таким URL-ідентифікатором (slug) вже існує."

    def __init__(self, slug: str) -> None:
        super().__init__(
            message=f"Об'єкт оцінювання зі slug '{slug}' вже існує.",
            details={"slug": slug},
        )


class ReviewNotFoundException(NotFoundException):
    """Відгук не знайдено."""

    default_error_code = "REVIEW_NOT_FOUND"
    default_message = "Відгук не знайдено."

    def __init__(self, review_id: UUID) -> None:
        super().__init__(
            message=f"Відгук '{review_id}' не знайдено.",
            details={"review_id": str(review_id)},
        )


class ReviewAlreadyExistsException(ConflictException):
    """Користувач вже залишив відгук на цей об'єкт (правило One Review)."""

    default_error_code = "REVIEW_ALREADY_EXISTS"
    default_message = "Ви вже залишили відгук на цей об'єкт. Для зміни оцінки скористайтеся редагуванням."

    def __init__(self, target_id: UUID, user_id: UUID) -> None:
        super().__init__(
            message="Користувач вже має активний відгук для цього об'єкта.",
            details={"target_id": str(target_id), "user_id": str(user_id)},
        )


class InvalidScoreException(DomainException):
    """Оцінка виходить за допустимі межі 1..5."""

    default_error_code = "INVALID_SCORE"
    default_message = "Оцінка повинна бути цілим числом від 1 до 5 зірок."

    def __init__(self, score: int) -> None:
        super().__init__(
            message=f"Оцінка {score} є неприпустимою (дозволено від 1 до 5).",
            details={"score": score},
        )


class SelfReviewVoteForbiddenException(ConflictException):
    """Спроба оцінити корисність власного відгуку."""

    default_error_code = "SELF_REVIEW_VOTE_FORBIDDEN"
    default_message = "Заборонено голосувати за власний відгук."


class ReviewVoteAlreadyExistsException(ConflictException):
    """Спроба проголосувати повторно тим самим користувачем."""

    default_error_code = "REVIEW_VOTE_ALREADY_EXISTS"
    default_message = "Ви вже віддали свій голос за цей відгук."


class UserNotFoundException(NotFoundException):
    """Користувача не знайдено в системі."""

    default_error_code = "USER_NOT_FOUND"
    default_message = "Користувача не знайдено."

    def __init__(self, user_id: UUID) -> None:
        super().__init__(
            message=f"Користувача з ID '{user_id}' не знайдено.",
            details={"user_id": str(user_id)},
        )
