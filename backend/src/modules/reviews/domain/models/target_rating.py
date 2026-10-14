from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from src.modules.reviews.domain.exceptions import InvalidScoreException


@dataclass(kw_only=True)
class TargetRating:
    """
    Доменна сутність агрегованого рейтингу об'єкта (TargetRating).
    Слугує високопродуктивною проекцією (Read-optimized Projection) для швидкої видачі оцінок.
    """

    target_id: UUID
    total_reviews: int = 0
    average_score: Decimal = Decimal("0.00")
    bayesian_score: Decimal = Decimal("0.00")
    star_1_count: int = 0
    star_2_count: int = 0
    star_3_count: int = 0
    star_4_count: int = 0
    star_5_count: int = 0
    last_calculated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    version: int = 1

    @classmethod
    def create_empty(cls, target_id: UUID) -> "TargetRating":
        """Фабричний метод створення початкового порожнього рейтингу для нового тарґету."""
        return cls(target_id=target_id)

    def _validate_score(self, score: int) -> None:
        if not (1 <= score <= 5):
            raise InvalidScoreException(score)

    def _recalculate_average(self) -> None:
        """Перерахунок середнього арифметичного значення на основі гістограми зірок."""
        total = self.star_1_count + self.star_2_count + self.star_3_count + self.star_4_count + self.star_5_count
        self.total_reviews = total

        if total == 0:
            self.average_score = Decimal("0.00")
            self.bayesian_score = Decimal("0.00")
            return

        weighted_sum = (
            1 * self.star_1_count
            + 2 * self.star_2_count
            + 3 * self.star_3_count
            + 4 * self.star_4_count
            + 5 * self.star_5_count
        )
        avg = Decimal(weighted_sum) / Decimal(total)
        self.average_score = avg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def apply_new_review(self, score: int) -> None:
        """Атомарне додавання нової оцінки в агрегат."""
        self._validate_score(score)

        if score == 1:
            self.star_1_count += 1
        elif score == 2:
            self.star_2_count += 1
        elif score == 3:
            self.star_3_count += 1
        elif score == 4:
            self.star_4_count += 1
        elif score == 5:
            self.star_5_count += 1

        self._recalculate_average()
        self.last_calculated_at = datetime.now(UTC)

    def apply_updated_review(self, old_score: int, new_score: int) -> None:
        """Оновлення агрегату при зміні оцінки у відгуку."""
        self._validate_score(old_score)
        self._validate_score(new_score)

        if old_score == new_score:
            return

        # Віднімаємо стару
        if old_score == 1:
            self.star_1_count = max(0, self.star_1_count - 1)
        elif old_score == 2:
            self.star_2_count = max(0, self.star_2_count - 1)
        elif old_score == 3:
            self.star_3_count = max(0, self.star_3_count - 1)
        elif old_score == 4:
            self.star_4_count = max(0, self.star_4_count - 1)
        elif old_score == 5:
            self.star_5_count = max(0, self.star_5_count - 1)

        # Додаємо нову
        if new_score == 1:
            self.star_1_count += 1
        elif new_score == 2:
            self.star_2_count += 1
        elif new_score == 3:
            self.star_3_count += 1
        elif new_score == 4:
            self.star_4_count += 1
        elif new_score == 5:
            self.star_5_count += 1

        self._recalculate_average()
        self.last_calculated_at = datetime.now(UTC)

    def apply_deleted_review(self, score: int) -> None:
        """Віднімання оцінки при видаленні або приховуванні відгуку."""
        self._validate_score(score)

        if score == 1:
            self.star_1_count = max(0, self.star_1_count - 1)
        elif score == 2:
            self.star_2_count = max(0, self.star_2_count - 1)
        elif score == 3:
            self.star_3_count = max(0, self.star_3_count - 1)
        elif score == 4:
            self.star_4_count = max(0, self.star_4_count - 1)
        elif score == 5:
            self.star_5_count = max(0, self.star_5_count - 1)

        self._recalculate_average()
        self.last_calculated_at = datetime.now(UTC)

    def calculate_bayesian_score(
        self,
        *,
        min_votes_threshold: int = 5,
        global_mean: Decimal = Decimal("3.50"),
    ) -> Decimal:
        """
        Обчислення зваженого Байєсівського рейтингу:
        WR = (v / (v + m)) * R + (m / (v + m)) * C
        де:
          v = total_reviews
          m = min_votes_threshold
          R = average_score
          C = global_mean
        """
        v = Decimal(self.total_reviews)
        m = Decimal(min_votes_threshold)
        r = self.average_score
        c = global_mean

        if v + m == 0:
            self.bayesian_score = Decimal("0.00")
            return self.bayesian_score

        score = ((v / (v + m)) * r) + ((m / (v + m)) * c)
        self.bayesian_score = score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return self.bayesian_score
