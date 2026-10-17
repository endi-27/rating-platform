import pytest
from uuid6 import uuid7

from src.core.exceptions import (
    DomainException,
    InactiveEntityError,
    ResourceAlreadyActiveException,
    ResourceAlreadyInactiveException,
)
from src.modules.reviews.domain.models import Target


def test_target_creation_happy_path() -> None:
    user_id = uuid7()
    target = Target.create(
        slug="inception-2010",
        title="Inception",
        category="movie",
        description="A thief who steals corporate secrets through dream-sharing technology.",
        metadata={"director": "Christopher Nolan", "year": 2010},
        created_by_id=user_id,
    )

    assert target.id is not None
    assert target.slug == "inception-2010"
    assert target.title == "Inception"
    assert target.category == "movie"
    assert target.description == "A thief who steals corporate secrets through dream-sharing technology."
    assert target.metadata == {"director": "Christopher Nolan", "year": 2010}
    assert target.created_by_id == user_id
    assert target.is_active is True
    assert target.version == 1
    assert target.created_at is not None
    assert target.updated_at is None


def test_target_slug_and_category_normalization() -> None:
    target = Target.create(
        slug="  The-Matrix-1999  ",
        title="  The Matrix  ",
        category="  Sci-Fi-Movie  ",
    )
    assert target.slug == "the-matrix-1999"
    assert target.title == "The Matrix"
    assert target.category == "sci-fi-movie"


def test_target_validation_errors() -> None:
    # Empty slug
    with pytest.raises(DomainException, match="URL-ідентифікатор"):
        Target(
            id=uuid7(),
            slug="   ",
            title="Valid Title",
            category="movie",
        )

    # Empty title
    with pytest.raises(DomainException, match="Назва об'єкта повинна містити"):
        Target(
            id=uuid7(),
            slug="valid-slug",
            title="",
            category="movie",
        )

    # Title too long (> 255)
    with pytest.raises(DomainException, match="Назва об'єкта повинна містити"):
        Target(
            id=uuid7(),
            slug="valid-slug",
            title="A" * 256,
            category="movie",
        )

    # Empty category
    with pytest.raises(DomainException, match="Категорія повинна містити"):
        Target(
            id=uuid7(),
            slug="valid-slug",
            title="Valid Title",
            category="",
        )

    # Category too long (> 100)
    with pytest.raises(DomainException, match="Категорія повинна містити"):
        Target(
            id=uuid7(),
            slug="valid-slug",
            title="Valid Title",
            category="C" * 101,
        )


def test_target_update_details_happy_path() -> None:
    target = Target.create(
        slug="interstellar-2014",
        title="Interstellar",
        category="movie",
        description="Old description",
    )

    target.update_details(
        title="Interstellar (IMAX)",
        category="cinema",
        description="A team of explorers travel through a wormhole in space.",
        metadata={"runtime": 169},
    )

    assert target.title == "Interstellar (IMAX)"
    assert target.category == "cinema"
    assert target.description == "A team of explorers travel through a wormhole in space."
    assert target.metadata == {"runtime": 169}
    assert target.updated_at is not None


def test_target_update_details_validation() -> None:
    target = Target.create(slug="dune-2021", title="Dune", category="movie")

    with pytest.raises(DomainException, match="Назва об'єкта"):
        target.update_details(title="")

    with pytest.raises(DomainException, match="Назва об'єкта"):
        target.update_details(title=" " * 5)

    with pytest.raises(DomainException, match="Категорія повинна"):
        target.update_details(category="")

    # Update on inactive entity raises InactiveEntityError
    target.soft_delete()
    with pytest.raises(InactiveEntityError):
        target.update_details(title="New Dune")


def test_target_soft_delete_and_restore() -> None:
    target = Target.create(slug="oppenheimer-2023", title="Oppenheimer", category="movie")
    assert target.is_active is True

    target.soft_delete()
    assert target.is_active is False
    assert target.deleted_at is not None

    # Cannot delete already deleted
    with pytest.raises(ResourceAlreadyInactiveException):
        target.soft_delete()

    target.restore()
    assert target.is_active is True
    assert target.deleted_at is None

    # Cannot restore already active
    with pytest.raises(ResourceAlreadyActiveException):
        target.restore()


def test_target_update_details_title_max_length_and_whitespace_description() -> None:
    target = Target.create(slug="dune-2021", title="Dune", category="movie", description="Original desc")

    with pytest.raises(DomainException, match="Назва об'єкта"):
        target.update_details(title="A" * 256)

    target.update_details(description="   ")
    assert target.description is None


def test_target_update_details_category_max_length_and_partial_updates() -> None:
    target = Target.create(
        slug="blade-runner-2049",
        title="Blade Runner 2049",
        category="movie",
        description="   ",
    )
    assert target.description is None

    with pytest.raises(DomainException, match="Категорія повинна"):
        target.update_details(category="c" * 101)

    # Partial update with None values preserves existing fields
    target.update_details(metadata={"Oscar": True})
    assert target.title == "Blade Runner 2049"
    assert target.category == "movie"
    assert target.metadata == {"Oscar": True}
