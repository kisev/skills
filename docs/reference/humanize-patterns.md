# humanize editing patterns

[Русский](../ru/reference/humanize-patterns.md)

Worked before/after examples for the `humanize` skill, one pair in English and
one pair in Russian for each of the 26 categories mapped from
[blader/humanizer](https://github.com/blader/humanizer) (built on Wikipedia's
"Signs of AI writing"). The portable catalog in the skill archive keeps the
rules and English examples; this page adds the Russian pairs.

Two boundaries from the skill always win and have no upstream counterpart:

- A writing sample never overrides the punctuation rule, the no-invention
  rule, or any other mandatory constraint. Match the voice, not the defects.
- Do not add an opinion, reaction, or objection that the source or the user
  did not express.

The "before" examples intentionally contain the defects, including forbidden
punctuation; never copy them into new prose. Patterns marked "weak alone" need
company from other tells in the same passage before an edit; the mandatory
punctuation and no-invention rules apply regardless of this classification.

## A. Staging instead of stating

### 1. Not X but Y

**Before (en):**

> It's not just about the beat riding under the vocals; it's part of the
> aggression and atmosphere.

**After (en):**

> The beat rides under the vocals and adds to the aggression and atmosphere.

**Before (ru):**

> Это не просто ускорение поиска, а полная переработка конвейера запросов.

**After (ru):**

> Конвейер запросов полностью переработан, и поиск теперь выполняется
> быстрее.

### 2. One-line closers and dramatic fragments

**Before (en):**

> Caching cuts repeat work.
>
> That is the real win.
>
> Retries hide brief outages.
>
> That is the real win.

**After (en):**

> Caching cuts repeat work.
>
> Retries hide brief outages.

**Before (ru):**

> Кеширование убирает повторные запросы.
>
> Вот где настоящая ценность.
>
> Ретраи скрывают краткие сбои.
>
> Вот где настоящая ценность.

**After (ru):**

> Кеширование убирает повторные запросы.
>
> Ретраи скрывают краткие сбои.

### 3. Sayings that sound deep

**Before (en):**

> The real question is whether teams can adapt. At its core, what really
> matters is organizational readiness.

**After (en):**

> The question is whether teams can adapt, and that depends on how ready the
> organization is.

**Before (ru):**

> Настоящий вопрос в том, готова ли команда меняться. В своей сути ключевое
> значение имеет зрелость процессов.

**After (ru):**

> Вопрос в том, готова ли команда меняться; во многом это зависит от зрелости
> процессов.

### 4. Staged run-up before the point

**Before (en):**

> Let's dive into how caching works in Next.js. Here's what you need to know.
> Next.js caches data at multiple layers: request memoization, the data cache,
> and the router cache.
> Next.js caches data at multiple layers: request memoization, the data cache,
> and the router cache.
> Next.js caches data at multiple layers: request memoization, the data cache,
> and the router cache.

**After (en):**

> Next.js caches data at multiple layers: request memoization, the data cache,
> and the router cache.

**Before (ru):**

> Давайте разберёмся, как устроено кеширование в Next.js. Вот что нужно знать.
> Next.js кеширует данные на нескольких уровнях: мемоизация запросов, кеш
> данных и кеш роутера.
> Next.js кеширует данные на нескольких уровнях: мемоизация запросов, кеш
> данных и кеш роутера.
> Next.js кеширует данные на нескольких уровнях: мемоизация запросов, кеш
> данных и кеш роутера.

**After (ru):**

> Next.js кеширует данные на нескольких уровнях: мемоизация запросов, кеш
> данных и кеш роутера.

### 5. Arguing with no one

**Before (en):**

> Session tokens are rotated every 24 hours. A tempting approach would be to
> rotate them by restarting the auth service on a cron job, but that would
> drop every active session. Rotation happens in place, and clients refresh
> transparently.

**After (en):**

> Session tokens are rotated every 24 hours. Restarting the auth service would
> drop every active session, so rotation happens in place and clients refresh
> transparently.

**Before (ru):**

> Токены сессии меняются каждые 24 часа. Заманчивым подходом кажется
> перезапуск auth-сервиса по расписанию, но он сбросил бы все активные
> сессии. Ротация происходит на месте, клиенты обновляют токен прозрачно.

**After (ru):**

> Токены сессии меняются каждые 24 часа прямо на месте, и клиенты обновляют
> токен прозрачно.

## B. Rhythm by rule

### 6. Forced triads (weak alone)

**Before (en):**

> The event features keynote sessions, panel discussions, and networking
> opportunities. Attendees can expect innovation, inspiration, and industry
> insights.

**After (en):**

> The event includes keynote sessions and panels. There is also time for
> networking.

**Before (ru):**

> Конференция включает кейноуты, панельные дискуссии и нетворкинг. Участников
> ждут инновации, вдохновение и инсайты индустрии.

**After (ru):**

> В программе кейноуты и панели, а также время для нетворкинга.

### 7. Repeated sentence openings (weak alone)

**Before (en):**

> She noted the door. She noted the lock on it. She filed both away.

**After (en):**

> She noted the door and its lock, then filed both away.

**Before (ru):**

> Она заметила дверь. Она заметила замок на ней. Она запомнила и то и другое.

**After (ru):**

> Она заметила дверь и замок на ней и запомнила оба.

### 8. Dashes as the universal connector

In Russian, recast sentences that grammar would punctuate with a copula dash
instead of keeping the dash.

**Before (en):**

> The new policy — announced without warning — affects thousands of workers.

**After (en):**

> The new policy, announced without warning, affects thousands of workers.

**Before (ru):**

> Новая политика — её не стали анонсировать — касается тысяч сотрудников.

**After (ru):**

> Новая политика, которую не стали анонсировать, касается тысяч сотрудников.

### 9. Stacked qualifiers (weak alone)

**Before (en):**

> It could potentially possibly be argued that the policy might have some
> effect on outcomes.

**After (en):**

> The policy may affect outcomes.

**Before (ru):**

> Не исключено, что политика потенциально может оказывать некоторое влияние
> на отдельные результаты.

**After (ru):**

> Политика может влиять на результаты.

### 10. Hyphenated pairs everywhere (weak alone)

In Russian, hyphenated compounds follow dictionary spelling; do not add
hyphens by analogy with English.

**Before (en):**

> The report is high-quality, the process is well-documented, and the plan is
> long-term.

**After (en):**

> The report is high quality, the process is well documented, and the plan is
> long term.

**Before (ru):**

> Отчёт высоко-качественный, процесс хорошо-документированный, план
> долго-срочный.

**After (ru):**

> Отчёт высококачественный, процесс хорошо задокументирован, план рассчитан
> на долгий срок.

### 11. Passive voice and missing subjects (weak alone)

**Before (en):**

> No configuration file is needed. The import script preserves the results
> automatically.

**After (en):**

> You do not need a configuration file. The import script preserves the
> results automatically.

**Before (ru):**

> Файл конфигурации не требуется. Скрипт импорта сохраняет результаты
> автоматически.

**After (ru):**

> Файл конфигурации не нужен. Скрипт импорта сохраняет результаты
> автоматически.

## C. Inflation and borrowed authority

### 12. Overused AI words (weak alone)

**Before (en):**

> Additionally, a pivotal feature of the culinary landscape is the
> incorporation of camel meat, showcasing enduring traditions.

**After (en):**

> The cuisine also includes camel meat, a long-standing tradition.

**Before (ru):**

> Кроме того, ключевой особенностью кулинарного ландшафта является
> использование верблюжатины, что подчёркивает непреходящие традиции.

**After (ru):**

> Эта кухня включает и верблюжатину, ставшую давней традицией.

### 13. Inflated significance

**Before (en):**

> The Statistical Institute of Catalonia was officially established in 1989,
> marking a pivotal moment in the evolution of regional statistics in Spain.

**After (en):**

> The Statistical Institute of Catalonia was established in 1989.

**Before (ru):**

> Институт статистики Каталонии был официально основан в 1989 году, что
> стало поворотным моментом в эволюции региональной статистики Испании.

**After (ru):**

> Институт статистики Каталонии основан в 1989 году.

### 14. Vague connection or association

**Before (en):**

> He is associated with the Rajhans Orchestra, which he founded and conducts.

**After (en):**

> He founded and conducts the Rajhans Orchestra.

**Before (ru):**

> Он связан с оркестром Раджханс, которым руководит.

**After (ru):**

> Он руководит оркестром Раджханс.

### 15. Shallow participial riders (weak alone)

**Before (en):**

> The temple's color palette of blue, green, and gold resonates with the
> region's natural beauty, symbolizing Texas bluebonnets, reflecting the
> community's deep connection to the land.

**After (en):**

> The temple is painted blue, green, and gold, colors meant to evoke Texas
> bluebonnets.

**Before (ru):**

> Палитра храма из синего, зелёного и золотого перекликается с природой
> региона, символизируя техасские люпины и отражая глубокую связь общины с
> землёй.

**After (ru):**

> Храм окрашен в синий, зелёный и золотой: цвета должны напоминать техасские
> люпины.

### 16. Sales language

**Before (en):**

> Nestled within the breathtaking region of Gonder in Ethiopia, Alamata Raya
> Kobo stands as a vibrant town with a rich cultural heritage.

**After (en):**

> Alamata Raya Kobo is a town in the Gonder region of Ethiopia.

**Before (ru):**

> Расположенный среди захватывающих пейзажей эфиопского региона Гондэр,
> город Аламата Рая Кобо предстаёт ярким городом с богатым культурным
> наследием.

**After (ru):**

> Город Аламата Рая Кобо находится в эфиопском регионе Гондэр.

### 17. Borrowed authority

**Before (en):**

> Experts believe the Haolai River plays a crucial role in the regional
> ecosystem. The 2021 basin survey recorded 40 fish species in the river. The 2021 basin survey recorded 40 fish species in the river. The 2021 basin survey recorded 40 fish species in the river.

**After (en):**

> The 2021 basin survey recorded 40 fish species in the Haolai River.

**Before (ru):**

> Эксперты считают, что река Хаолай играет ключевую роль в региональной
> экосистеме. Бассейновое обследование 2021 года зафиксировало в реке 40
> видов рыб. Бассейновое обследование 2021 года зафиксировало в реке 40
> видов рыб. Бассейновое обследование 2021 года зафиксировало в реке 40
> видов рыб.

**After (ru):**

> Бассейновое обследование 2021 года зафиксировало в реке Хаолай 40 видов
> рыб.

### 18. Avoiding is, are, and has (weak alone)

In Russian, prefer a direct verb over a copula dash when the dash is
forbidden.

**Before (en):**

> Gallery 825 serves as LAAA's exhibition space for contemporary art and
> boasts over 3,000 square feet.

**After (en):**

> Gallery 825 is LAAA's exhibition space for contemporary art and has over
> 3,000 square feet.

**Before (ru):**

> Галерея 825 служит выставочным пространством для современного искусства и
> обладает площадью более 3000 квадратных футов.

**After (ru):**

> Галерея 825 выставляет современное искусство и занимает более 3000
> квадратных футов.

## D. Formatting by rule

### 19. Bold as decoration (weak alone)

**Before (en):**

> It blends **OKRs (Objectives and Key Results)**, **KPIs (Key Performance
> Indicators)**, and visual strategy tools such as the **Business Model
> Canvas (BMC)**.

**After (en):**

> It blends OKRs (Objectives and Key Results), KPIs (Key Performance
> Indicators), and visual strategy tools such as the Business Model Canvas
> (BMC).

**Before (ru):**

> Подход сочетает **OKR (цели и ключевые результаты)**, **KPI (ключевые
> показатели)** и визуальные инструменты стратегии, такие как **Business
> Model Canvas**.

**After (ru):**

> Подход сочетает OKR, KPI и визуальные инструменты стратегии, такие как
> Business Model Canvas.

### 20. Decorative headings (weak alone)

**Before (en):**

> ## Strategic Negotiations And Global Partnerships

**After (en):**

> ## Strategic negotiations and global partnerships

**Before (ru):**

> ## Стратегические Переговоры И Глобальные Партнёрства

**After (ru):**

> ## Стратегические переговоры и глобальные партнёрства

### 21. Curly quotation marks

**Before (en):**

> He said “the project is on track” but others disagreed.

**After (en):**

> He said "the project is on track" but others disagreed.

**Before (ru):**

> Он сказал, что «проект идёт по графику», но с ним не согласились.

**After (ru):**

> Он сказал, что "проект идёт по графику", но с ним не согласились.

## E. Leftovers from the chat and the draft

### 22. Chatbot residue

**Before (en):**

> Great question! Here is an overview of the French Revolution. It began in
> 1789 when a financial crisis and food shortages led to widespread unrest.
> I hope this helps! Let me know if you'd like me to expand on any section.

**After (en):**

> The French Revolution began in 1789 when a financial crisis and food
> shortages led to widespread unrest.

**Before (ru):**

> Отличный вопрос! Вот обзор Французской революции. Она началась в 1789
> году, когда финансовый кризис и нехватка еды привели к волнениям. Надеюсь,
> это помогло! Дайте знать, если нужно раскрыть раздел подробнее.

**After (ru):**

> Французская революция началась в 1789 году, когда финансовый кризис и
> нехватка еды привели к волнениям.

### 23. Knowledge-limit disclaimers and guesses

**Before (en):**

> While specific details about the company's founding are not extensively
> documented in readily available sources, it appears to have been
> established sometime in the 1990s.

**After (en):**

> The company's founding date is not documented in the available sources.

**Before (ru):**

> Хотя подробности об основании компании недостаточно задокументированы в
> открытых источниках, предположительно она была основана в 1990-х годах.

**After (ru):**

> Дата основания компании в доступных источниках не задокументирована.

### 24. A heading repeated in the first sentence (weak alone)

**Before (en):**

> ## Performance
>
> Speed matters.
>
> When users hit a slow page, they leave.

**After (en):**

> ## Performance
>
> When users hit a slow page, they leave.

**Before (ru):**

> ## Производительность
>
> Скорость важна.
>
> Когда страница открывается медленно, пользователи уходят.

**After (ru):**

> ## Производительность
>
> Когда страница открывается медленно, пользователи уходят.

### 25. Writing about the document instead of its subject (weak alone)

**Before (en):**

> This function looks up an item by key. It was added to replace the previous
> approach of iterating through all items, which caused O(n²) performance.

**After (en):**

> This function looks up an item by key.

**Before (ru):**

> Функция ищет элемент по ключу. Её добавили, чтобы заменить прежний подход с
> перебором всех элементов, из-за которого возникала сложность O(n²).

**After (ru):**

> Функция ищет элемент по ключу.

## F. Writing for the wrong reader

### 26. Re-explaining what the reader knows

The conversation context is explicit, so the reply may drop what the reviewer
already knows.

**Before (en):**

> Great question! Let me walk through what happens today. When you move a
> child under a new parent, `MergeService` keeps the old `pipeline_id`, which
> is why you saw the wrong pipeline attached. This patch clears the field in
> the controller instead. So to answer your question: it works around the
> issue rather than fixing it. The real fix is to update `pipeline_id` along
> with `parent_id` in `MergeService`. I checked QA: 123 past merges, only 6
> rows wrong now, so the cleanup is small. I'd rather open a separate ticket
> than widen this PR.

**After (en):**

> This patch is a workaround: it clears `pipeline_id` in the controller. The
> real fix updates `pipeline_id` along with `parent_id` in `MergeService`.
> QA shows 123 past merges, 6 rows wrong now, so the cleanup is small. I'd
> open a separate ticket rather than widen this PR.

**Before (ru):**

> Отличный вопрос! Давайте разберём, что происходит сейчас. При переносе
> элемента под нового родителя `MergeService` оставляет старый `pipeline_id`,
> из-за чего вы и увидели неправильный пайплайн. Этот патч вместо этого
> очищает поле в контроллере. Так что отвечая на ваш вопрос: это обходной
> путь, а не исправление. Настоящее исправление в том, чтобы обновлять
> `pipeline_id` вместе с `parent_id` в `MergeService`. Я проверил QA: из 123
> прошлых слияний неверно заполнены только 6 строк, так что очистка
> небольшая. Я бы открыл отдельную задачу, а не расширял этот PR.

**After (ru):**

> Это обходной путь: патч очищает `pipeline_id` в контроллере. Настоящее
> исправление обновляет `pipeline_id` вместе с `parent_id` в `MergeService`.
> QA: из 123 прошлых слияний неверно заполнены 6 строк, так что очистка
> небольшая. Я бы открыл отдельную задачу, а не расширял этот PR.

## When not to act

Each pattern describes a default choice, and a person can make any one of
them on purpose. Leave a watched phrase alone inside a quotation, a title, a
proper name, or a passage that discusses the phrase rather than uses it. One
word, one passive clause, or a genuine list is not a defect. Several tells
together are the safeguard.

Keep the details that carry the writer's voice unless they hurt the meaning:
a specific unusual detail, mixed feelings the source actually expresses,
dated era-bound references, a first-person choice the writer can explain, and
genuine asides or self-corrections from the source.
