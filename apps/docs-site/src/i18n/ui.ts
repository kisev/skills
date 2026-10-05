export type Locale = "en" | "ru";

export const locales: Locale[] = ["en", "ru"];

export const localeNames: Record<Locale, string> = {
  en: "English",
  ru: "Русский",
};

export const ui = {
  en: {
    site: {
      name: "Agent Skills",
      tagline: "Portable skills for Codex and OpenCode",
    },
    nav: {
      home: "Home",
      skills: "Skills",
      examples: "Examples",
      docs: "Documentation",
      github: "GitHub",
    },
    hero: {
      title: "Portable Agent Skills",
      lead: "Self-contained workflows for engineering, documentation, delivery, and team operations. Install them into any host that reads .agents/skills, or add @kisev/agentomatic for a first-class OpenCode integration.",
      browse: "Browse the catalog",
      examples: "See interaction examples",
    },
    install: {
      title: "Install",
      lead: "The installer opens a picker with every skill preselected; pass `--skill <name>` to stay selective. Rerun the same command to update.",
      latest: "Everything on latest",
      dev: "Everything on dev",
      verificationNote:
        "npm view previews a registry version; tags can move before installation. npx does not install a global CLI. skills@latest is the installer version, not the Pages release; skills list checks the skills actually installed.",
      ownershipNote:
        "After confirming the OpenCode setup, npm list checks agentomatic in its owning npm project, not npm's global CLI prefix. Restart OpenCode after installation or updates.",
    },
    components: {
      title: "Project components",
      lead: "The components are independent: use any of them on its own or combine them for the complete setup.",
      table: {
        component: "Component",
        provides: "What it provides",
        portable: "Portable Agent Skills",
        portableProvides:
          "Self-contained workflows installable with the skills CLI into ~/.agents/skills or .agents/skills",
        agentomatic: "@kisev/agentomatic",
        agentomaticProvides:
          "OpenCode slash-command adapters, fixed agents, capability routing, diagnostics, and optional plugin wrappers",
        memomatic: "@kisev/memomatic",
        memomaticProvides:
          "Personal learning memory for agents: a tiered Markdown corpus with a rebuildable search index, exposed to hosts through a local MCP server",
        reviewmatic: "reviewmatic (Python)",
        reviewmaticProvides:
          "Python runtime for the code-review skill: GitLab and local-WIP review workflows with private artifacts and copy-ready manual runbooks, launched from Git with uvx",
        taskmatic: "@kisev/taskmatic",
        taskmaticProvides:
          "Local-first task board for people and agents: SQLite cards with a Markdown mirror, agent claims with heartbeats, and a read-only web board",
      },
    },
    catalog: {
      title: "Skill catalog",
      lead: "Every skill is an independent archive with its own workflow; declared companions are install recommendations, not runtime dependencies.",
      search: "Search skills and examples",
    },
    skillPage: {
      installTitle: "Install this skill",
      relationsTitle: "Related skills",
      examplesTitle: "Interaction examples",
      noExamples:
        "No worked example yet. The example rollout continues across iterations; the catalog page always reflects current coverage.",
      backToCatalog: "All skills",
    },
    relations: {
      requires: "Requires",
      uses: "Uses",
      recommends: "Recommends",
    },
    example: {
      prompt: "Request",
      steps: "What the skill does",
      artifacts: "Generated artifact",
      limitations: "Limitations",
    },
    examplesIndex: {
      title: "Interaction examples",
      lead: "Worked scenarios per skill: the request, what the skill does, and the artifact it produces. The rollout starts with a pilot batch and grows by template.",
    },
    footer: {
      license: "MIT licensed",
      docs: "Full documentation",
      source: "Source",
    },
    notFound: {
      title: "Page not found",
      lead: "The page moved or never existed. The catalog is the safest starting point.",
      home: "To the home page",
    },
  },
  ru: {
    site: {
      name: "Agent Skills",
      tagline: "Портативные скиллы для Codex и OpenCode",
    },
    nav: {
      home: "Главная",
      skills: "Скиллы",
      examples: "Примеры",
      docs: "Документация",
      github: "GitHub",
    },
    hero: {
      title: "Портативные Agent Skills",
      lead: "Самодостаточные сценарии для инженерии, документации, поставки и работы с командой. Устанавливаются в любой хост, читающий .agents/skills, а @kisev/agentomatic добавляет полноценную интеграцию с OpenCode.",
      browse: "Открыть каталог",
      examples: "Посмотреть примеры",
    },
    install: {
      title: "Установка",
      lead: "Установщик открывает picker со всеми скиллами; флаг `--skill <name>` выбирает точечно. Повторный запуск обновляет установку.",
      latest: "Всё из канала latest",
      dev: "Всё из канала dev",
      verificationNote:
        "npm view показывает версию в реестре; теги могут сдвинуться до установки. npx не устанавливает CLI глобально. skills@latest - версия установщика, а не выпуска Pages; skills list проверяет реально установленные навыки.",
      ownershipNote:
        "После подтверждения настройки OpenCode команда npm list проверяет agentomatic во владеющем npm-проекте, а не среди глобальных CLI npm. Перезапустите OpenCode после установки или обновления.",
    },
    components: {
      title: "Компоненты проекта",
      lead: "Компоненты независимы: используйте любой отдельно или соедините их ради полного опыта.",
      table: {
        component: "Компонент",
        provides: "Что даёт",
        portable: "Portable Agent Skills",
        portableProvides:
          "Самодостаточные сценарии, устанавливаемые CLI skills в ~/.agents/skills или .agents/skills",
        agentomatic: "@kisev/agentomatic",
        agentomaticProvides:
          "Slash-command адаптеры OpenCode, фиксированные агенты, маршрутизация возможностей, диагностика и опциональные обёртки-плагины",
        memomatic: "@kisev/memomatic",
        memomaticProvides:
          "Личная обучающая память для агентов: многоуровневый Markdown-корпус с перестраиваемым поисковым индексом, доступная хостам через локальный MCP-сервер",
        reviewmatic: "reviewmatic (Python)",
        reviewmaticProvides:
          "Рантайм скилла code-review на Python: ревью GitLab и локального WIP с приватными артефактами и копируемыми ручными runbook, запуск из Git через uvx",
        taskmatic: "@kisev/taskmatic",
        taskmaticProvides:
          "Локальная доска задач для человека и агентов: карточки в SQLite с зеркалом в Markdown, захваты агентов с heartbeat и веб-доска только для чтения",
      },
    },
    catalog: {
      title: "Каталог скиллов",
      lead: "Каждый скилл — независимый архив со своим сценарием; объявленные спутники это рекомендации по установке, а не рантайм-зависимости.",
      search: "Поиск по скиллам и примерам",
    },
    skillPage: {
      installTitle: "Установка скилла",
      relationsTitle: "Связанные скиллы",
      examplesTitle: "Примеры взаимодействия",
      noExamples:
        "Разобранного примера пока нет. Примеры добавляются итерациями по общему шаблону; эта страница всегда показывает актуальное покрытие.",
      backToCatalog: "Все скиллы",
    },
    relations: {
      requires: "Требует",
      uses: "Использует",
      recommends: "Рекомендует",
    },
    example: {
      prompt: "Запрос",
      steps: "Что делает скилл",
      artifacts: "Сгенерированный артефакт",
      limitations: "Ограничения",
    },
    examplesIndex: {
      title: "Примеры взаимодействия",
      lead: "Разобранные сценарии по скиллам: запрос, действия скилла и полученный артефакт. Покрытие начинается с пилотной партии и растёт по шаблону.",
    },
    footer: {
      license: "Лицензия MIT",
      docs: "Полная документация",
      source: "Исходники",
    },
    notFound: {
      title: "Страница не найдена",
      lead: "Страница переехала или её никогда не было. Каталог — самый надёжный старт.",
      home: "На главную",
    },
  },
} as const;

export type Dictionary = (typeof ui)["en"];

export function useUi(locale: Locale): Dictionary {
  return ui[locale];
}
