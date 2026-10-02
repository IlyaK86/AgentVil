#!/usr/bin/env python3
"""Simple RAG: keyword-based search over KB files."""
import os, re
from pathlib import Path

KB_DIR = Path('/opt/repetitor/kb')

# Common stopwords (Russian + general)
STOPWORDS = {
    'и', 'в', 'на', 'с', 'по', 'для', 'что', 'это', 'как', 'или', 'но',
    'а', 'же', 'ли', 'ни', 'бы', 'то', 'к', 'у', 'о', 'от', 'до', 'из',
    'за', 'мы', 'вы', 'он', 'она', 'они', 'я', 'ты', 'его', 'её', 'их',
    'этот', 'эта', 'эти', 'тот', 'та', 'те', 'мне', 'мной', 'нас', 'вас',
    'быть', 'есть', 'был', 'была', 'было', 'будут', 'может', 'можно',
    'не', 'да', 'нет', 'так', 'вот', 'уже', 'ещё', 'еще', 'когда', 'если',
    'чтобы', 'потому', 'очень', 'нужно', 'надо', 'просто', 'значит',
    'скажи', 'объясни', 'помоги', 'расскажи', 'теперь', 'потом', 'снова',
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'have',
    'has', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
    'можешь', 'могут', 'знает', 'знаю', 'знаешь', 'можно',
}

# Topic hints — расширяем запросы по темам
TOPIC_HINTS = {
    'дроб': ['математика 4 класс', 'ФГОС математика', 'дроби', 'доли'],
    'дроби': ['математика 4 класс', 'ФГОС математика', 'дроби', 'доли'],
    'дол': ['математика 4 класс', 'ФГОС математика', 'дроби', 'доли'],
    'умнож': ['математика 4 класс', 'ФГОС математика', 'умножение'],
    'дел': ['математика 4 класс', 'ФГОС математика', 'деление', 'деление в столбик'],
    'столбик': ['математика 4 класс', 'ФГОС математика', 'деление в столбик'],
    'площад': ['математика 4 класс', 'ФГОС математика', 'площадь'],
    'объём': ['математика 4 класс', 'ФГОС математика', 'объём'],
    'уравнен': ['математика 4 класс', 'ФГОС математика', 'уравнения'],
    'пример': ['математика 4 класс', 'ФГОС математика'],
    'задач': ['математика 4 класс', 'ФГОС математика', 'задачи', 'ошибки в задачах'],

    'морфем': ['морфемный разбор', 'разбор по составу', 'морфемы'],
    'разбор': ['морфемный разбор', 'разбор по составу', 'морфологический разбор'],
    'состав': ['морфемный разбор', 'разбор по составу'],
    'пристав': ['морфемный разбор', 'морфемы', 'приставка'],
    'суффикс': ['морфемный разбор', 'морфемы', 'суффикс'],
    'корен': ['морфемный разбор', 'морфемы', 'корень слова'],
    'окончан': ['морфемный разбор', 'морфемы', 'окончание'],
    'основ': ['морфемный разбор', 'морфемы', 'основа слова'],

    'причаст': ['ФГОС русский', 'причастие', 'причастный оборот'],
    'причастие': ['ФГОС русский', 'причастие', 'причастный оборот'],
    'деепричаст': ['ФГОС русский', 'деепричастие', 'деепричастный оборот'],
    'деепричастие': ['ФГОС русский', 'деепричастие', 'деепричастный оборот'],
    'существ': ['ФГОС русский', 'морфологический разбор', 'имя существительное'],
    'глагол': ['ФГОС русский', 'морфологический разбор', 'глагол'],
    'прилагательн': ['ФГОС русский', 'морфологический разбор', 'имя прилагательное'],
    'местоимен': ['ФГОС русский', 'морфологический разбор', 'местоимение'],
    'нареч': ['ФГОС русский', 'морфологический разбор', 'наречие'],
    'предлог': ['ФГОС русский', 'морфологический разбор', 'предлог'],
    'союз': ['ФГОС русский', 'союз'],
    'частиц': ['ФГОС русский', 'частица'],
    'падеж': ['ФГОС русский', 'морфологический разбор', 'падежи'],
    'склонен': ['ФГОС русский', 'морфологический разбор', 'склонение'],
    'спряжен': ['ФГОС русский', 'морфологический разбор', 'спряжение'],
    'орфограмм': ['ФГОС русский', 'орфограммы', 'правописание'],
    'правописан': ['ФГОС русский', 'орфограммы', 'правописание'],
    'словарн': ['ФГОС русский', 'словарные слова'],
    'ударен': ['ФГОС русский', 'ударение'],
    'безударн': ['ФГОС русский', 'безударная гласная'],
    'парн': ['ФГОС русский', 'парные согласные'],
    'непроизносим': ['ФГОС русский', 'непроизносимые согласные'],
    'удвоен': ['ФГОС русский', 'удвоенные согласные'],
    'мягк': ['ФГОС русский', 'мягкий знак'],
    'разделительн': ['ФГОС русский', 'разделительный мягкий знак'],

    'сингапур': ['Singapore Math', 'CPA', 'concrete pictorial abstract'],
    'cpa': ['Singapore Math', 'CPA'],
    'concrete': ['Singapore Math', 'CPA'],
    'pictorial': ['Singapore Math', 'CPA'],
    'abstract': ['Singapore Math', 'CPA'],
}

# Cache file contents
_CACHE = {}
def _load_all():
    if _CACHE:
        return _CACHE
    for f in KB_DIR.iterdir():
        if f.is_file() and f.suffix in ('.md', '.html', '.pdf', '.txt'):
            try:
                text = f.read_text(errors='ignore')[:200_000]  # 200K per file cap
                _CACHE[f.name] = text
            except Exception as e:
                _CACHE[f.name] = ''
    return _CACHE

def _score_file(text: str, query_terms: list[str], topic_hints: list[str]) -> int:
    """Return relevance score: term frequency in text + topic hits * 3."""
    text_lower = text.lower()
    score = 0
    for t in query_terms:
        # word boundary match for short terms
        pattern = re.escape(t.lower())
        score += len(re.findall(pattern, text_lower))
    for t in topic_hints:
        pattern = re.escape(t.lower())
        score += 3 * len(re.findall(pattern, text_lower))
    return score

def _extract_relevant_excerpt(text: str, terms: list[str], hints: list[str], max_chars: int = 4000) -> str:
    """Find windows in text with highest density of terms, return combined excerpt."""
    if not text or not (terms or hints):
        return ''
    text_lower = text.lower()
    # Find all match positions
    positions = []
    for t in terms + hints:
        tl = t.lower()
        i = 0
        while True:
            idx = text_lower.find(tl, i)
            if idx < 0:
                break
            positions.append(idx)
            i = idx + 1
            if len(positions) > 200:
                break
    if not positions:
        return ''
    positions.sort()

    # Sliding window of max_chars, score by density of matches
    window_size = 1200
    best_windows = []
    for start in range(0, len(text), 600):  # sliding step
        end = min(len(text), start + window_size)
        if end - start < 200:
            continue
        window_positions = [p for p in positions if start <= p < end]
        if window_positions:
            score = len(window_positions)
            best_windows.append((score, start, end))

    if not best_windows:
        # Fallback: first match
        pos = positions[0]
        return text[max(0, pos - 200):min(len(text), pos + max_chars - 200)]

    # Take top-3 windows, dedupe overlap, combine
    best_windows.sort(reverse=True)
    chosen = []
    for sc, s, e in best_windows:
        # Check overlap with already chosen
        overlaps = any(abs(s - cs) < window_size * 0.5 for cs, _, _ in chosen)
        if not overlaps:
            chosen.append((s, e, sc))
        if len(chosen) >= 3:
            break
    chosen.sort()

    parts = []
    total = 0
    for s, e, sc in chosen:
        excerpt = text[s:e].strip()
        if excerpt:
            parts.append(f'[{s}-{e}, score={sc}]\n{excerpt}')
            total += len(excerpt)
        if total >= max_chars:
            break
    return '\n...\n'.join(parts)


def search(query: str, top_k: int = 4, max_chars_per_file: int = 4500) -> str:
    """Search KB by query, return combined relevant excerpts from top scoring files."""
    cache = _load_all()
    if not cache:
        return ''

    # Tokenize query
    q_lower = query.lower()
    raw_terms = re.findall(r'[а-яёa-z]{3,}', q_lower)
    terms = [t for t in raw_terms if t not in STOPWORDS]

    # Add topic hints
    hints = []
    for trigger, expansions in TOPIC_HINTS.items():
        if trigger in q_lower:
            hints.extend(expansions)

    # Score each file (file-level ranking)
    scored = []
    for fname, text in cache.items():
        if not text:
            continue
        text_lower = text.lower()
        s = 0
        for t in terms:
            pattern = re.escape(t.lower())
            s += len(re.findall(pattern, text_lower))
        for t in hints:
            pattern = re.escape(t.lower())
            s += 3 * len(re.findall(pattern, text_lower))
        if s > 0:
            scored.append((s, fname, text))
    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return ''

    # For top-k files, extract relevant excerpts
    out_parts = []
    seen_chars = 0
    for s, fname, text in scored[:top_k]:
        excerpt = _extract_relevant_excerpt(text, terms, hints, max_chars=max_chars_per_file)
        if excerpt:
            out_parts.append(f'### Источник: {fname} (релевантность файла: {s})\n{excerpt}\n')
            seen_chars += len(excerpt)
        if seen_chars > 14_000:
            break

    if not out_parts:
        return ''

    return '\n---\n'.join(out_parts)


if __name__ == '__main__':
    # Quick test
    test_queries = [
        'Объясни дроби в 4 классе',
        'Как разобрать слово по составу?',
        'Что такое причастный оборот?',
        'Расскажи про Singapore Math CPA',
    ]
    for q in test_queries:
        print(f'\n=== {q} ===')
        result = search(q)
        print(result[:1500])
        print(f'  total chars: {len(result)}')