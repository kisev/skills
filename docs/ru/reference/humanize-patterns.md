# Приёмы редактирования humanize

[English](../../reference/humanize-patterns.md)

Разобранные примеры "до/после" для скилла `humanize`: по одной паре на
английском и на русском для каждой из 26 категорий, сопоставленных с
[blader/humanizer](https://github.com/blader/humanizer) (на основе
"Signs of AI writing" Википедии). Переносимый каталог в архиве скилла
содержит правила и примеры на английском; эта страница добавляет русские
пары.

Два ограничения скилла всегда сильнее образца и не имеют аналога в upstream:

- Образец письма никогда не отменяет правило пунктуации, запрет выдуманных
  фактов и другие обязательные ограничения. Подражайте голосу, а не дефектам.
- Не добавляйте мнение, реакцию или возражение, которых нет в источнике или
  в явной просьбе пользователя.

Примеры "до" намеренно содержат дефекты, включая запрещённую пунктуацию; не
переносите их в новый текст. Приёмы с пометкой "слабо в одиночку" оправдывают
правку только вместе с другими признаками в том же пассаже; обязательные
правила пунктуации и запрета выдуманных фактов действуют независимо от этой
классификации.

## A. Стахинг вместо утверждения

### 1. Не X, а Y

**До (en):**

> It's not just about the beat riding under the vocals; it's part of the
> aggression and atmosphere.

**После (en):**

> The beat rides under the vocals and adds to the aggression and atmosphere.

**До (ru):**

> Это не просто ускорение поиска, а полная переработка конвейера запросов.

**После (ru):**

> Конвейер запросов полностью переработан, и поиск теперь выполняется
> быстрее.

### 2. Однострочные выводы и драматические фрагменты

**До (en):**

> Caching cuts repeat work.
>
> That is the real win.
>
> Retries hide brief outages.
>
> That is the real win.

**После (en):**

> Caching cuts repeat work.
>
> Retries hide brief outages.

**До (ru):**

> Кеширование убирает повторные запросы.
>
> Вот где настоящая ценность.
>
> Ретраи скрывают краткие сбои.
>
> Вот где настоящая ценность.

**После (ru):**

> Кеширование убирает повторные запросы.
>
> Ретраи скрывают краткие сбои.

### 3. Псевдоглубокомысленные присказки

**До (en):**

> The real question is whether teams can adapt. At its core, what really
> matters is organizational readiness.

**После (en):**

> The question is whether teams can adapt, and that depends on how ready the
> organization is.

**До (ru):**

> Настоящий вопрос в том, готова ли команда меняться. В своей сути ключевое
> значение имеет зрелость процессов.

**После (ru):**

> Вопрос в том, готова ли команда меняться; во многом это зависит от зрелости
> процессов.

### 4. Разгон перед мыслью

**До (en):**

> Let's dive into how caching works in Next.js. Here's what you need to know.
> Next.js caches data at multiple layers: request memoization, the data cache,
> and the router cache.
> Next.js caches data at multiple layers: request memoization, the data cache,
> and the router cache.

**После (en):**

> Next.js caches data at multiple layers: request memoization, the data cache,
> and the router cache.

**До (ru):**

> Давайте разберёмся, как устроено кеширование в Next.js. Вот что нужно знать.
> Next.js кеширует данные на нескольких уровнях: мемоизация запросов, кеш
> данных и кеш роутера.
> Next.js кеширует данные на нескольких уровнях: мемоизация запросов, кеш
> данных и кеш роутера.

**После (ru):**

> Next.js кеширует данные на нескольких уровнях: мемоизация запросов, кеш
> данных и кеш роутера.

### 5. Спор с никем

**До (en):**

> Session tokens are rotated every 24 hours. A tempting approach would be to
> rotate them by restarting the auth service on a cron job, but that would
> drop every active session. Rotation happens in place, and clients refresh
> transparently.

**После (en):**

> Session tokens are rotated every 24 hours. Restarting the auth service would
> drop every active session, so rotation happens in place and clients refresh
> transparently.

**До (ru):**

> Токены сессии меняются каждые 24 часа. Заманчивым подходом кажется
> перезапуск auth-сервиса по расписанию, но он сбросил бы все активные
> сессии. Ротация происходит на месте, клиенты обновляют токен прозрачно.

**После (ru):**

> Токены сессии меняются каждые 24 часа. Перезапуск auth-сервиса сбросил бы
> все активные сессии, поэтому ротация происходит на месте, и клиенты
> обновляют токен прозрачно.

## B. Ритм по правилу

### 6. Вынужденные триады (слабо в одиночку)

**До (en):**

> The event features keynote sessions, panel discussions, and networking
> opportunities. Attendees can expect innovation, inspiration, and industry
> insights.

**После (en):**

> The event includes keynote sessions and panels. There is also time for
> networking.

**До (ru):**

> Конференция включает кейноуты, панельные дискуссии и нетворкинг. Участников
> ждут инновации, вдохновение и инсайты индустрии.

**После (ru):**

> В программе кейноуты и панели, а также время для нетворкинга.

### 7. Повторяющиеся начала предложений (слабо в одиночку)

**До (en):**

> She noted the door. She noted the lock on it. She filed both away.

**После (en):**

> She noted the door and its lock, then filed both away.

**До (ru):**

> Она заметила дверь. Она заметила замок на ней. Она запомнила и то и другое.

**После (ru):**

> Она заметила дверь и замок на ней и запомнила оба.

### 8. Тире вместо выбора связи

В русском тексте предложение с грамматическим тире между подлежащим и
сказуемым перестраивается, а не сохраняет тире.

**До (en):**

> The new policy — announced without warning — affects thousands of workers.

**После (en):**

> The new policy, announced without warning, affects thousands of workers.

**До (ru):**

> Новая политика — её не стали анонсировать — касается тысяч сотрудников.

**После (ru):**

> Новая политика, которую не стали анонсировать, касается тысяч сотрудников.

### 9. Нагромождение оговорок (слабо в одиночку)

**До (en):**

> It could potentially possibly be argued that the policy might have some
> effect on outcomes.

**После (en):**

> The policy may affect outcomes.

**До (ru):**

> Не исключено, что политика потенциально может оказывать некоторое влияние
> на отдельные результаты.

**После (ru):**

> Политика может влиять на результаты.

### 10. Дефисные пары везде (слабо в одиночку)

В русском языке дефисные написания следуют словарю; не добавляйте дефис по
аналогии с английским.

**До (en):**

> The report is high-quality, the process is well-documented, and the plan is
> long-term.

**После (en):**

> The report is high quality, the process is well documented, and the plan is
> long term.

**До (ru):**

> Отчёт высоко-качественный, процесс хорошо-документированный, план
> долго-срочный.

**После (ru):**

> Отчёт высококачественный, процесс хорошо задокументирован, план рассчитан
> на долгий срок.

### 11. Пассив и пропущенные субъекты (слабо в одиночку)

**До (en):**

> No configuration file is needed. The import script preserves the results
> automatically.

**После (en):**

> You do not need a configuration file. The import script preserves the
> results automatically.

**До (ru):**

> Файл конфигурации не требуется. Скрипт импорта сохраняет результаты
> автоматически.

**После (ru):**

> Файл конфигурации не нужен. Скрипт импорта сохраняет результаты
> автоматически.

## C. Раздувание и заимствованный авторитет

### 12. Заезженные слова ИИ (слабо в одиночку)

**До (en):**

> Additionally, a pivotal feature of the culinary landscape is the
> incorporation of camel meat, showcasing enduring traditions.

**После (en):**

> The cuisine also includes camel meat, a long-standing tradition.

**До (ru):**

> Кроме того, ключевой особенностью кулинарного ландшафта является
> использование верблюжатины, что подчёркивает непреходящие традиции.

**После (ru):**

> Эта кухня включает и верблюжатину, ставшую давней традицией.

### 13. Преувеличенная значимость

**До (en):**

> The Statistical Institute of Catalonia was officially established in 1989,
> marking a pivotal moment in the evolution of regional statistics in Spain.

**После (en):**

> The Statistical Institute of Catalonia was established in 1989.

**До (ru):**

> Институт статистики Каталонии был официально основан в 1989 году, что
> стало поворотным моментом в эволюции региональной статистики Испании.

**После (ru):**

> Институт статистики Каталонии основан в 1989 году.

### 14. Смутная связь

**До (en):**

> He is associated with the Rajhans Orchestra, which he founded and conducts.

**После (en):**

> He founded and conducts the Rajhans Orchestra.

**До (ru):**

> Он связан с оркестром Раджханс, которым руководит.

**После (ru):**

> Он руководит оркестром Раджханс.

### 15. Мелкие деепричастные украшения (слабо в одиночку)

**До (en):**

> The temple's color palette of blue, green, and gold resonates with the
> region's natural beauty, symbolizing Texas bluebonnets, reflecting the
> community's deep connection to the land.

**После (en):**

> The temple is painted blue, green, and gold, colors meant to evoke Texas
> bluebonnets.

**До (ru):**

> Палитра храма из синего, зелёного и золотого перекликается с природой
> региона, символизируя техасские люпины и отражая глубокую связь общины с
> землёй.

**После (ru):**

> Храм окрашен в синий, зелёный и золотой: цвета должны напоминать техасские
> люпины.

### 16. Рекламный язык

**До (en):**

> Nestled within the breathtaking region of Gonder in Ethiopia, Alamata Raya
> Kobo stands as a vibrant town with a rich cultural heritage.

**После (en):**

> Alamata Raya Kobo is a town in the Gonder region of Ethiopia.

**До (ru):**

> Расположенный среди захватывающих пейзажей эфиопского региона Гондэр,
> город Аламата Рая Кобо предстаёт ярким городом с богатым культурным
> наследием.

**После (ru):**

> Город Аламата Рая Кобо находится в эфиопском регионе Гондэр.

### 17. Заимствованный авторитет

**До (en):**

> Experts believe the Haolai River plays a crucial role in the regional
> ecosystem. The 2021 basin survey recorded 40 fish species in the river. The 2021 basin survey recorded 40 fish species in the river.

**После (en):**

> The 2021 basin survey recorded 40 fish species in the Haolai River.

**До (ru):**

> Эксперты считают, что река Хаолай играет ключевую роль в региональной
> экосистеме. Бассейновое обследование 2021 года зафиксировало в реке 40
> видов рыб. Бассейновое обследование 2021 года зафиксировало в реке 40
> видов рыб.

**После (ru):**

> Бассейновое обследование 2021 года зафиксировало в реке Хаолай 40 видов
> рыб.

### 18. Избегание "это", "есть" и "имеет" (слабо в одиночку)

В русском тексте при запрете тире предпочтительна прямая глагольная
конструкция вместо тире между подлежащим и сказуемым.

**До (en):**

> Gallery 825 serves as LAAA's exhibition space for contemporary art and
> boasts over 3,000 square feet.

**После (en):**

> Gallery 825 is LAAA's exhibition space for contemporary art and has over
> 3,000 square feet.

**До (ru):**

> Галерея 825 служит выставочным пространством для современного искусства и
> обладает площадью более 3000 квадратных футов.

**После (ru):**

> Галерея 825 выставляет современное искусство и занимает более 3000
> квадратных футов.

## D. Форматирование по правилу

### 19. Жирный как украшение (слабо в одиночку)

**До (en):**

> It blends **OKRs (Objectives and Key Results)**, **KPIs (Key Performance
> Indicators)**, and visual strategy tools such as the **Business Model
> Canvas (BMC)**.

**После (en):**

> It blends OKRs (Objectives and Key Results), KPIs (Key Performance
> Indicators), and visual strategy tools such as the Business Model Canvas
> (BMC).

**До (ru):**

> Подход сочетает **OKR (цели и ключевые результаты)**, **KPI (ключевые
> показатели)** и визуальные инструменты стратегии, такие как **Business
> Model Canvas**.

**После (ru):**

> Подход сочетает OKR (цели и ключевые результаты), KPI (ключевые показатели)
> и визуальные инструменты стратегии, такие как Business Model Canvas.

### 20. Декоративные заголовки (слабо в одиночку)

**До (en):**

> ## Strategic Negotiations And Global Partnerships

**После (en):**

> ## Strategic negotiations and global partnerships

**До (ru):**

> ## Стратегические Переговоры И Глобальные Партнёрства

**После (ru):**

> ## Стратегические переговоры и глобальные партнёрства

### 21. Типографские кавычки

**До (en):**

> He said “the project is on track” but others disagreed.

**После (en):**

> He said "the project is on track" but others disagreed.

**До (ru):**

> Он сказал, что «проект идёт по графику», но с ним не согласились.

**После (ru):**

> Он сказал, что "проект идёт по графику", но с ним не согласились.

## E. Остатки чата и черновика

### 22. Остатки чат-бота

**До (en):**

> Great question! Here is an overview of the French Revolution. It began in
> 1789 when a financial crisis and food shortages led to widespread unrest.
> I hope this helps! Let me know if you'd like me to expand on any section.

**После (en):**

> The French Revolution began in 1789 when a financial crisis and food
> shortages led to widespread unrest.

**До (ru):**

> Отличный вопрос! Вот обзор Французской революции. Она началась в 1789
> году, когда финансовый кризис и нехватка еды привели к волнениям. Надеюсь,
> это помогло! Дайте знать, если нужно раскрыть раздел подробнее.

**После (ru):**

> Французская революция началась в 1789 году, когда финансовый кризис и
> нехватка еды привели к волнениям.

### 23. Оговорки о границах знания и догадки

**До (en):**

> While specific details about the company's founding are not extensively
> documented in readily available sources, it appears to have been
> established sometime in the 1990s.

**После (en):**

> The company's founding date is not documented in the available sources.

**До (ru):**

> Хотя подробности об основании компании недостаточно задокументированы в
> открытых источниках, предположительно она была основана в 1990-х годах.

**После (ru):**

> Дата основания компании в доступных источниках не задокументирована.

### 24. Заголовок, повторённый первым предложением (слабо в одиночку)

**До (en):**

> ## Performance
>
> Speed matters.
>
> When users hit a slow page, they leave.

**После (en):**

> ## Performance
>
> When users hit a slow page, they leave.

**До (ru):**

> ## Производительность
>
> Скорость важна.
>
> Когда страница открывается медленно, пользователи уходят.

**После (ru):**

> ## Производительность
>
> Когда страница открывается медленно, пользователи уходят.

### 25. Текст о самом тексте вместо предмета (слабо в одиночку)

**До (en):**

> This function looks up an item by key. It was added to replace the previous
> approach of iterating through all items, which caused O(n²) performance.

**После (en):**

> This function looks up an item by key.

**До (ru):**

> Функция ищет элемент по ключу. Её добавили, чтобы заменить прежний подход с
> перебором всех элементов, из-за которого возникала сложность O(n²).

**После (ru):**

> Функция ищет элемент по ключу.

## F. Письмо не тому читателю

### 26. Повторное объяснение известного

Контекст беседы задан явно, поэтому ответ может опустить то, что ревьюер уже
знает.

**До (en):**

> Great question! Let me walk through what happens today. When you move a
> child under a new parent, `MergeService` keeps the old `pipeline_id`, which
> is why you saw the wrong pipeline attached. This patch clears the field in
> the controller instead. So to answer your question: it works around the
> issue rather than fixing it. The real fix is to update `pipeline_id` along
> with `parent_id` in `MergeService`. I checked QA: 123 past merges, only 6
> rows wrong now, so the cleanup is small. I'd rather open a separate ticket
> than widen this PR.

**После (en):**

> This patch is a workaround: it clears `pipeline_id` in the controller. The
> real fix updates `pipeline_id` along with `parent_id` in `MergeService`.
> QA shows 123 past merges, 6 rows wrong now, so the cleanup is small. I'd
> open a separate ticket rather than widen this PR.

**До (ru):**

> Отличный вопрос! Давайте разберём, что происходит сейчас. При переносе
> элемента под нового родителя `MergeService` оставляет старый `pipeline_id`,
> из-за чего вы и увидели неправильный пайплайн. Этот патч вместо этого
> очищает поле в контроллере. Так что отвечая на ваш вопрос: это обходной
> путь, а не исправление. Настоящее исправление в том, чтобы обновлять
> `pipeline_id` вместе с `parent_id` в `MergeService`. Я проверил QA: из 123
> прошлых слияний неверно заполнены только 6 строк, так что очистка
> небольшая. Я бы открыл отдельную задачу, а не расширял этот PR.

**После (ru):**

> Это обходной путь: патч очищает `pipeline_id` в контроллере. Настоящее
> исправление обновляет `pipeline_id` вместе с `parent_id` в `MergeService`.
> QA: из 123 прошлых слияний неверно заполнены 6 строк, так что очистка
> небольшая. Я бы открыл отдельную задачу, а не расширял этот PR.

## Когда не вмешиваться

Каждый приём описывает выбор по умолчанию, и человек может сделать его
намеренно. Не трогайте фразы внутри точной цитаты, названия, имени
собственного или пассажа, который обсуждает приём, а не использует его.
Отдельное слово, один пассивный оборот или настоящий список дефектом не
являются; дефект доказывают несколько приёмов вместе.

Сохраняйте детали, несущие голос автора, если они не вредят смыслу:
конкретную необычную деталь, смешанные чувства, реально выраженные в
источнике, приметы времени, выбор от первого лица и подлинные ремарки.
