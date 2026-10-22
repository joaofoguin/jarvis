"""Estatísticas de uso de IA para o painel, lidas da tabela ai_usage."""

from datetime import date, timedelta

from db import get_connection


DAYS = 14

# Preços do deepseek-flash por milhão de tokens, em dólar, no horário de pico (o mais caro),
# conferidos em 22/10/2026 em https://api-docs.deepseek.com/quick_start/pricing.
PRICE_CACHE_HIT = 0.006
PRICE_INPUT = 0.3
PRICE_OUTPUT = 1.2


def rows(days=DAYS):
    """(quando, origem, entrada, entrada em cache, saída) de cada chamada dos últimos dias."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT created_at, source, prompt_tokens, cache_hit_tokens, completion_tokens
                FROM ai_usage
                WHERE created_at >= NOW() - %s * INTERVAL '1 day'
                """,
                (days,)
            )

            return cur.fetchall()


def summarize(data, today, days=DAYS):
    by_day = {today - timedelta(days=n): 0 for n in range(days - 1, -1, -1)}
    by_source = {}
    total = calls = 0
    cost = 0.0

    for created_at, source, prompt, cache_hit, completion in data:
        # O dia conta no fuso do notebook, não no do banco.
        day = created_at.astimezone().date()
        tokens = prompt + completion

        if day not in by_day:
            continue

        by_day[day] += tokens
        by_source[source] = by_source.get(source, 0) + tokens
        total += tokens
        calls += 1
        # O DeepSeek conta os tokens em cache dentro da entrada.
        cost += ((prompt - cache_hit) * PRICE_INPUT + cache_hit * PRICE_CACHE_HIT + completion * PRICE_OUTPUT) / 1_000_000

    return {
        "days": [{"day": day.isoformat(), "tokens": tokens} for day, tokens in by_day.items()],
        "by_source": by_source,
        "total": total,
        "calls": calls,
        "cost": round(cost, 4)
    }


def summary():
    return summarize(rows(), date.today())
