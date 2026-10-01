"""Compact GitLab cards, independent of credentials and network access."""

from __future__ import annotations

import math
import re
import unicodedata
import urllib.parse
from typing import Any, NoReturn

LABELS = {
    "en": {
        "status": "Status",
        "author": "Author",
        "assignee": "Assignee",
        "milestone": "Milestone",
        "labels": "Labels",
        "pipeline": "Pipeline",
        "approvals": "Approvals",
        "unknown": "Unknown",
        "none": "None",
        "more": "{count} more",
    },
    "ru": {
        "status": "Статус",
        "author": "Автор",
        "assignee": "Исполнитель",
        "milestone": "Майлстоун",
        "labels": "Метки",
        "pipeline": "Пайплайн",
        "approvals": "Апрувы",
        "unknown": "Неизвестно",
        "none": "Нет",
        "more": "ещё {count}",
    },
}


class CardError(ValueError):
    """Invalid card; diagnostics use the requested card locale."""


def fail(locale: str, path: str, en: str, ru: str) -> NoReturn:
    raise CardError(f"{path}: {ru if locale == 'ru' else en}")


def text(value: object, locale: str, path: str, limit: int, lines: int = 1) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(locale, path, "expected non-empty text", "ожидается непустой текст")
    if any(unicodedata.category(c) in {"Cc", "Cf", "Cs", "Zl", "Zp"} and c != "\n" for c in value):
        fail(locale, path, "control characters are not allowed", "управляющие символы запрещены")
    if len(value) > limit or len(value.split("\n")) > lines:
        fail(
            locale,
            path,
            f"shorten to at most {limit} characters and {lines} line(s); got {len(value)} characters",
            f"сократите до {limit} символов и {lines} строк; получено {len(value)} символов",
        )
    return value


def escaped(value: str) -> str:
    # Card content is plain text: source Markdown must not add images, headings or pings.
    value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    value = re.sub(r"([\\`*_{}\[\]()#+.!|~\-])", r"\\\1", value)
    return value.replace("@", "&#64;")


def estimated_lines(value: str, width: int) -> int:
    return sum(
        max(
            1,
            math.ceil(
                sum(2 if unicodedata.east_asian_width(c) in {"W", "F"} else 1 for c in line) / width
            ),
        )
        for line in value.split("\n")
    )


def render(value: object) -> dict[str, Any]:
    """Validate a card and return one bounded legacy attachment without truncation."""
    locale = value.get("locale", "en") if isinstance(value, dict) else "en"
    if locale not in ("en", "ru"):
        fail("en", "card.locale", "expected en or ru", "")
    if not isinstance(value, dict):
        fail(locale, "card", "expected an object", "ожидается объект")
    base = {"kind", "template", "locale", "title", "url", "summary"}
    metadata = {"status", "author", "assignee", "milestone", "labels", "omitted_labels"}
    kind, template = value.get("kind"), value.get("template")
    if kind not in ("issue", "mr") or template not in ("standard", "custom"):
        fail(
            locale,
            "card",
            "expected kind issue/mr and template standard/custom",
            "ожидаются kind issue/mr и template standard/custom",
        )
    required = base | ({"fields"} if template == "custom" else metadata)
    if template == "standard" and kind == "mr":
        required |= {"pipeline", "approvals"}
    if set(value) != required:
        fail(
            locale,
            "card",
            f"expected exactly these keys: {', '.join(sorted(required))}",
            f"ожидаются только эти ключи: {', '.join(sorted(required))}",
        )
    title = text(value["title"], locale, "card.title", 100)
    summary = text(value["summary"], locale, "card.summary", 240, 3)
    if estimated_lines(summary, 40) > 8:
        fail(
            locale,
            "card.summary",
            "shorten to at most 8 estimated lines",
            "сократите до 8 расчётных строк",
        )
    url = text(value["url"], locale, "card.url", 2048)
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not any(c.isspace() for c in url)
            and "\\" not in url
        )
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        fail(
            locale,
            "card.url",
            "expected an absolute HTTPS URL without credentials",
            "ожидается абсолютный HTTPS URL без учётных данных",
        )
    labels = LABELS[locale]
    fields: list[dict[str, Any]] = []
    if template == "custom":
        supplied = value["fields"]
        if not isinstance(supplied, list) or len(supplied) > 8:
            fail(locale, "card.fields", "expected at most 8 fields", "допускается не более 8 полей")
        for index, field in enumerate(supplied):
            path = f"card.fields[{index}]"
            if (
                not isinstance(field, dict)
                or set(field) != {"title", "value", "short"}
                or not isinstance(field["short"], bool)
            ):
                fail(
                    locale,
                    path,
                    "expected title, value and boolean short",
                    "ожидаются title, value и логическое short",
                )
            fields.append(
                {
                    "title": text(field["title"], locale, path + ".title", 28),
                    "value": text(field["value"], locale, path + ".value", 100),
                    "short": field["short"],
                }
            )
    else:
        keys = ["status", "author", "assignee", "milestone"]
        if kind == "mr":
            keys += ["pipeline", "approvals"]
        for key in keys:
            raw = value[key]
            display = labels["unknown"] if raw is None else labels["none"] if raw == "" else raw
            fields.append(
                {
                    "title": labels[key],
                    "value": text(display, locale, "card." + key, 100),
                    "short": True,
                }
            )
        selected, omitted = value["labels"], value["omitted_labels"]
        if type(omitted) is not int or not 0 <= omitted <= 10000:
            fail(
                locale,
                "card.omitted_labels",
                "expected an integer from 0 to 10000",
                "ожидается целое число от 0 до 10000",
            )
        if selected is None:
            if omitted:
                fail(
                    locale,
                    "card.omitted_labels",
                    "unknown labels require zero omitted",
                    "для неизвестных меток требуется нулевое значение",
                )
            label_text = labels["unknown"]
        else:
            if not isinstance(selected, list) or len(selected) > 10:
                fail(
                    locale,
                    "card.labels",
                    "expected null or at most 10 labels",
                    "ожидается null или не более 10 меток",
                )
            names = [
                text(name, locale, f"card.labels[{i}]", 100) for i, name in enumerate(selected)
            ]
            if omitted:
                names.append(labels["more"].format(count=omitted))
            label_text = ", ".join(names) if names else labels["none"]
        fields.append(
            {
                "title": labels["labels"],
                "value": text(label_text, locale, "card.labels", 100),
                "short": False,
            }
        )
    total = len(title) + len(summary) + sum(len(f["title"]) + len(f["value"]) for f in fields)
    rows = estimated_lines(title, 40) + estimated_lines(summary, 40)
    pending = 0
    for field in fields:
        height = estimated_lines(field["title"], 20 if field["short"] else 40)
        height += estimated_lines(field["value"], 20 if field["short"] else 40) + 1
        if field["short"]:
            if pending:
                rows += max(pending, height)
                pending = 0
            else:
                pending = height
        else:
            rows += pending + height
            pending = 0
    rows += pending
    if total > 1000 or rows > 28:
        fail(
            locale,
            "card",
            f"compact budget exceeded ({total}/1000 characters, {rows}/28 estimated lines); shorten text or fields",
            f"превышен бюджет компактности ({total}/1000 символов, {rows}/28 расчётных строк); сократите текст или поля",
        )
    return {
        "fallback": title,
        "title": title,
        "title_link": url,
        "color": "#1f75cb" if kind == "issue" else "#7759c2",
        "text": escaped(summary),
        "fields": [{**field, "value": escaped(field["value"])} for field in fields],
    }
