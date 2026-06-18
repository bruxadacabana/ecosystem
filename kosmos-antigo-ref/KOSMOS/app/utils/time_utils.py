"""Utilitários de formatação de tempo relativo."""

from __future__ import annotations

from datetime import datetime, timezone


def time_ago(dt: datetime | None) -> str:
    """Retorna uma string de tempo relativo em português.

    Ex: "há 5 minutos", "há 2 horas", "há 3 dias", "há 1 semana".
    Retorna string vazia se dt for None.
    """
    if dt is None:
        return ""

    # Garantir que ambos os datetimes são tz-aware ou naive
    now = datetime.now(timezone.utc) if dt.tzinfo else datetime.utcnow()
    delta_sec = max(0, int((now - dt).total_seconds()))

    if delta_sec < 60:
        return "agora mesmo"
    if delta_sec < 3600:
        mins = delta_sec // 60
        return f"há {mins} minuto{'s' if mins != 1 else ''}"
    if delta_sec < 86400:
        hours = delta_sec // 3600
        return f"há {hours} hora{'s' if hours != 1 else ''}"
    if delta_sec < 604800:
        days = delta_sec // 86400
        return f"há {days} dia{'s' if days != 1 else ''}"
    if delta_sec < 2592000:
        weeks = delta_sec // 604800
        return f"há {weeks} semana{'s' if weeks != 1 else ''}"

    months = delta_sec // 2592000
    return f"há {months} {'mês' if months == 1 else 'meses'}"


def format_date(dt: datetime | None) -> str:
    """Data formatada no padrão brasileiro: '20 de março de 2026'."""
    if dt is None:
        return ""
    _MONTHS = (
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    )
    return f"{dt.day} de {_MONTHS[dt.month - 1]} de {dt.year}"
