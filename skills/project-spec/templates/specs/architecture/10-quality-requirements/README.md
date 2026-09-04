# 10. Обеспечение качества

## Назначение

Объясни, какие architecture decisions и mechanisms обеспечивают quality goals.

## Сюда относится

- ссылки на `REQ-Q-*`;
- architecture tactics и trade-offs;
- evidence paths для механизмов, связанных с качеством.

## Сюда не относится

- дублирование нормативных thresholds;
- общий список характеристик ISO/IEC 25010;
- неподтверждённые claims о качестве.

## Правила декомпозиции

Раздел остаётся одним `README.md`; нормативный источник истины находится в
`requirements/quality/README.md`.

## Ожидаемая структура

```text
10-quality-requirements/
└── README.md
```

## Шаблон содержания

Свяжи каждый critical `REQ-Q-*` с конкретным mechanism, decision и trade-off. Если
requirement ещё не обеспечен architecture, обозначь risk без выдуманного решения.
