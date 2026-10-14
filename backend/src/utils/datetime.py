from datetime import UTC, datetime


def ensure_utc_datetime(dt: datetime) -> datetime:
    """
    Гарантує, що об'єкт datetime є timezone-aware та наведений до часового поясу UTC.

    Примітка: для naive datetime об'єктів (де tzinfo is None) функція припускає, що мітка
    вже представляє UTC-час, і призначає часовий пояс UTC без зсуву годин.
    Для timezone-aware об'єктів виконується коректна конвертація до UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
