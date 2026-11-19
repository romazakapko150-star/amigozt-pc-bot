"""Russian locale."""

TEXTS: dict[str, str] = {
    # --- generic ---
    "start.title": "<b>AMIGOZT PC</b>",
    "start.tagline": (
        "Собери компьютер под свой бюджет, игры и задачи.\n"
        "Я подберу совместимые комплектующие и объясню, почему именно их стоит выбрать."
    ),
    "menu.prompt": "Выбери, с чего начнём:",
    "menu.build": "🖥 Собрать ПК",
    "menu.budget": "💰 ПК по бюджету",
    "menu.games": "🎮 ПК для игр",
    "menu.presets": "⚡ Готовые сборки",
    "menu.compare": "🔄 Сравнить детали",
    "menu.mybuilds": "💾 Мои сборки",
    "menu.about": "ℹ️ О проекте",
    "menu.help": "❓ Помощь",
    "menu.language": "🌐 Язык",
    "nav.back": "⬅️ Назад",
    "nav.cancel": "❌ Отмена",
    "nav.restart": "🔄 Начать заново",
    "nav.menu": "🏠 Главное меню",
    "nav.skip": "⏭ Пропустить",
    "nav.done": "✅ Готово",
    "nav.yes": "Да",
    "nav.no": "Нет",
    "nav.auto": "🤖 Подобрать автоматически",
    "nav.custom": "✏️ Свой вариант",
    "common.error": "Произошла ошибка. Попробуй ещё раз.",
    "common.rate_limited": "Слишком много запросов. Подожди пару секунд 🙂",
    "common.cancelled": "Конфигуратор остановлен. Возвращаю в главное меню.",
    "common.coming_soon": "Этот раздел скоро появится. Пока попробуй «🖥 Собрать ПК».",
    "common.progress": "Шаг {current} из {total}",
    "common.unknown_action": "Не понял действие. Открой меню командой /start.",
    "about.text": (
        "<b>AmigoZT PC</b> — AI-сервис подбора компьютеров.\n\n"
        "Ты отвечаешь на простые вопросы, а я:\n"
        "• подбираю комплектующие под бюджет и задачи;\n"
        "• проверяю совместимость всех деталей;\n"
        "• оптимизирую сборку по соотношению цена/производительность;\n"
        "• считаю итоговую цену в PLN и ориентировочный FPS.\n\n"
        "Рынок: Польша 🇵🇱 · Валюта: PLN"
    ),
    "help.text": (
        "<b>Команды</b>\n"
        "/start — главное меню\n"
        "/build — собрать ПК\n"
        "/budget — подбор по бюджету\n"
        "/mybuilds — мои сборки\n"
        "/language — сменить язык\n"
        "/help — эта справка\n\n"
        "В конфигураторе всегда доступны кнопки «⬅️ Назад» и «❌ Отмена»."
    ),
    "lang.prompt": "Выбери язык интерфейса:",
    "lang.changed": "Язык изменён на русский 🇷🇺",
    # --- configurator ---
    "cfg.budget.q": "💰 Какой у тебя бюджет на компьютер?",
    "cfg.budget.hint": "Это бюджет на системный блок. Монитор и периферию посчитаем отдельно.",
    "cfg.budget.custom_prompt": ("Напиши свой бюджет в PLN числом.\nНапример: <code>5500</code>"),
    "cfg.budget.invalid": (
        "Не смог распознать сумму. Введи число в PLN от {min} до {max}.\n"
        "Например: <code>5500</code>"
    ),
    "cfg.purpose.q": "🎯 Для чего нужен компьютер?",
    "purpose.gaming": "🎮 Игры",
    "purpose.gaming_streaming": "🎥 Игры + стриминг",
    "purpose.work": "💻 Работа",
    "purpose.design": "🎨 Дизайн / видео",
    "purpose.ai_ml": "🤖 AI / ML",
    "purpose.workstation": "💼 Рабочая станция",
    "purpose.universal": "🔥 Универсальный",
    "cfg.games.q": "🎮 Во что играешь?",
    "cfg.games.hint": "Можно выбрать несколько. Выбрано: <b>{count}</b>",
    "cfg.games.other": "✏️ Другая игра",
    "cfg.games.custom_prompt": "Напиши название игры одним сообщением.",
    "cfg.games.invalid": "Слишком длинное или пустое название. Попробуй ещё раз.",
    "cfg.games.limit": "Больше {max} игр за раз выбрать нельзя.",
    "cfg.resolution.q": "🖥 На каком разрешении будешь играть или работать?",
    "resolution.1080p": "1080p (Full HD)",
    "resolution.1440p": "1440p (2K)",
    "resolution.4k": "4K (Ultra HD)",
    "cfg.fps.q": "⚡ Сколько FPS хочешь получать?",
    "cfg.priority.q": "🧭 Что для тебя важно в этом ПК?",
    "cfg.priority.hint": (
        "Можно выбрать несколько — до <b>{max}</b>. Отмечено: <b>{count}</b>. Потом нажми «Готово»."
    ),
    "cfg.priority.limit": "Больше {max} приоритетов за раз выбрать нельзя.",
    "cfg.priority.pick_one": "Отметь хотя бы один приоритет.",
    "priority.max_fps": "⚡ Максимальный FPS",
    "priority.price_performance": "💰 Цена / производительность",
    "priority.silence": "🤫 Тишина",
    "priority.cooling": "❄️ Охлаждение",
    "priority.looks": "🎨 Внешний вид",
    "priority.versatility": "🧠 Универсальность",
    "priority.efficiency": "🔌 Низкое энергопотребление",
    "priority.compact": "📦 Компактный размер",
    "priority.upgradeability": "🔧 Запас на апгрейд",
    "cfg.aesthetics.q": "🎨 Как должен выглядеть компьютер?",
    "aesthetics.black": "⚫ Чёрный",
    "aesthetics.white": "⚪ Белый",
    "aesthetics.black_rgb": "⚫ Чёрный + RGB",
    "aesthetics.white_rgb": "⚪ Белый + RGB",
    "aesthetics.minimal": "◻️ Минимализм",
    "aesthetics.gaming": "🔥 Игровой стиль",
    "cfg.connectivity.q": "📶 Нужны ли Wi-Fi и Bluetooth?",
    "connectivity.wifi_bt": "📶 Wi-Fi + Bluetooth",
    "connectivity.wifi": "📶 Только Wi-Fi",
    "connectivity.bt": "🔵 Только Bluetooth",
    "connectivity.none": "🔌 Не нужны (кабель)",
    "cfg.storage.q": "💾 Сколько места нужно для игр и файлов?",
    "cfg.ram.q": "🧠 Сколько оперативной памяти нужно?",
    "cfg.ram.hint": "Если не уверен — доверь выбор мне.",
    "cfg.cpu.q": "🧩 Есть предпочтения по процессору?",
    "cfg.gpu.q": "🖼 Есть предпочтения по видеокарте?",
    "brand.any": "🤝 Без разницы",
    # --- summary ---
    "summary.title": "<b>Твои требования</b>",
    "summary.budget": "Бюджет",
    "summary.purpose": "Назначение",
    "summary.games": "Игры",
    "summary.resolution": "Разрешение",
    "summary.fps": "Целевой FPS",
    "summary.priority": "Приоритет",
    "summary.aesthetics": "Внешний вид",
    "summary.connectivity": "Подключение",
    "summary.storage": "Накопитель",
    "summary.ram": "Память",
    "summary.cpu": "Процессор",
    "summary.gpu": "Видеокарта",
    "summary.auto": "на моё усмотрение",
    "summary.none": "не указано",
    "summary.next": (
        "Требования сохранены ✅\n\nСледующий шаг — подбор совместимых комплектующих и расчёт цены."
    ),
    "summary.btn_generate": "🚀 Подобрать сборку",
    "summary.generate_pending": (
        "⚙️ Подбор комплектующих готовится к запуску.\n\n"
        "База компонентов и движок совместимости подключаются на следующем этапе — "
        "твои требования уже сохранены и будут использованы автоматически."
    ),
    # --- order ---
    "order.button": "🛒 Хочу заказать",
    "order.created": (
        "Заявка <b>#{lead_id}</b> создана ✅\n\n"
        "Я передал её команде AmigoZT PC — свяжемся с тобой в Telegram в ближайшее время."
    ),
    "order.exists": "Заявка <b>#{lead_id}</b> уже оформлена. Мы её обрабатываем 👌",
    "order.expired": "Требования устарели. Собери конфигурацию заново — это займёт минуту.",
    "summary.ready": "✅ <b>Требования готовы</b>",
    "summary.hint_next": "Всё верно? Тогда подавай заявку.",
    "order.confirm_q": "Оформить заявку на эту конфигурацию?",
    "order.confirm_yes": "✅ Да, подать заявку",
    "order.edit": "✏️ Изменить",
    "order.cancelled": "Заявка не отправлена.",
    "summary.btn_save": "💾 Сохранить",
    # --- build card ---
    "build.ready": "🎉 <b>Твоя сборка готова</b>",
    "build.tier.budget": "💰 BUDGET",
    "build.tier.optimal": "⚖️ OPTIMAL",
    "build.tier.performance": "🔥 PERFORMANCE",
    "build.total": "Итого",
    "build.approx": "Цена ориентировочная — уточним при подтверждении заказа.",
    "build.legacy_note": "⚠️ Платформа без запаса на апгрейд процессора.",
    "build.fps_unavailable": "Недостаточно benchmark-данных для надёжной оценки FPS.",
    "build.warnings": "На что обратить внимание",
    "build.none": (
        "Под этот бюджет собрать совместимый ПК не получится.\n"
        "\n"
        "Минимум для такой конфигурации — примерно <b>{minimum}</b>."
    ),
    "build.none_generic": "Не удалось собрать конфигурацию. Попробуй изменить параметры.",
    "build.btn_other": "🔄 Другой вариант",
    "part.cpu": "🧠 Процессор",
    "part.gpu": "🎮 Видеокарта",
    "part.motherboard": "🧩 Материнская плата",
    "part.ram": "🧠 Память",
    "part.ssd": "💾 Накопитель",
    "part.psu": "🔌 Блок питания",
    "part.case": "📦 Корпус",
    "part.cooler": "❄️ Охлаждение",
    # --- compatibility notes ---
    "compat.memory_speed": "Память будет работать на частоте, поддерживаемой платформой.",
    "compat.psu_tight": "Блок питания без большого запаса под будущий апгрейд.",
    "compat.ssd_pcie_generation": "SSD будет работать на скорости шины материнской платы.",
    "compat.bios_update": (
        "Материнской плате может понадобиться обновление BIOS под этот процессор — мы сделаем "
        "это при сборке."
    ),
    "compat.gpu_power_adapter": "Видеокарта подключается через переходник питания из комплекта.",
    "compat.front_usb_c": (
        "USB-C на передней панели корпуса не подключится к этой плате без переходника."
    ),
    "compat.memory_four_modules": (
        "Четыре модуля памяти могут работать ниже заявленной частоты — два модуля стабильнее."
    ),
    "compat.memory_profile": "Профиль памяти (EXPO/XMP) может потребовать ручной настройки.",
    "compat.monitor_output": (
        "Для нужного режима монитора проверь кабель и разъём — не все порты его тянут."
    ),
    "order.blocked": "⚠️ <b>Нужно немного изменить сборку</b>",
    "order.blocked_hint": (
        "Проверка перед заказом нашла несовместимость. Заявка не отправлена — давай подберём "
        "заново."
    ),
    "order.btn_regenerate": "🔄 Подобрать заново",
    "compat.block.gpu_too_long": "Выбранная видеокарта слишком длинная для этого корпуса.",
    "compat.block.gpu_front_radiator": (
        "Видеокарта и радиатор СЖО спереди не помещаются вместе в этот корпус."
    ),
    "compat.block.gpu_slots": "Видеокарта слишком толстая для этого корпуса.",
    "compat.block.board_form_factor": "Материнская плата не подходит по формату к этому корпусу.",
    "compat.block.cooler_too_tall": "Кулер процессора слишком высокий для этого корпуса.",
    "compat.block.radiator_unsupported": "В этом корпусе нет места под радиатор выбранной СЖО.",
    "compat.block.psu_too_long": "Блок питания слишком длинный для этого корпуса.",
    "compat.block.psu_form_factor": "Блок питания не подходит по формату к этому корпусу.",
    "compat.block.psu_underpowered": "Мощности блока питания не хватает для этой конфигурации.",
    "compat.block.psu_gpu_minimum": (
        "Блок питания слабее минимума, который требует производитель видеокарты."
    ),
    "compat.block.gpu_power_connector": "У блока питания нет нужных разъёмов для этой видеокарты.",
    "compat.block.socket_mismatch": "Процессор и материнская плата на разных сокетах.",
    "compat.block.memory_type_mismatch": "Тип памяти не подходит к материнской плате.",
    "compat.block.argb_header": "Подсветке не хватает разъёма на материнской плате.",
    "compat.block.missing_part": "В сборке не хватает обязательного компонента.",
    "compat.block.generic": "Одна из комбинаций комплектующих не подтверждена как совместимая.",
    # --- ready builds ---
    "ready.title": "⚡ <b>Готовые сборки</b>",
    "ready.pick_filter": "Выбери, что показать:",
    "ready.all": "📋 Все сборки",
    "ready.by_budget": "💰 По бюджету",
    "ready.empty": "В этой категории пока пусто.",
    "ready.count": "Найдено: <b>{count}</b>",
    "ready.page": "Стр. {page} из {total}",
    "ready.open_hint": "Открой сборку кнопкой ниже.",
    "ready.prev": "⬅️",
    "ready.next": "➡️",
    "ready.cat.budget": "💰 Бюджетные",
    "ready.cat.gaming": "🎮 Игровые",
    "ready.cat.high_fps": "⚡ High FPS",
    "ready.cat.performance": "🔥 Performance",
    "ready.cat.high_end": "👑 High-End",
    "ready.cat.extreme": "💎 Extreme",
    "ready.cat.streaming": "🎥 Стриминг",
    "ready.cat.design": "🎨 Дизайн",
    "ready.cat.ai": "🤖 AI / ML",
    "ready.cat.workstation": "💼 Workstation",
    "ready.cat.white": "🤍 Белые",
    "ready.cat.rgb": "🌈 RGB",
    "ready.cat.quiet": "🤫 Тихие",
    "ready.budget.under": "до {value}",
    "ready.budget.over": "от {value}",
    "ready.stale": "Сборка временно недоступна. Выбери другую.",
    # --- compare ---
    "cmp.title": "🔄 <b>Сравнение комплектующих</b>",
    "cmp.pick_category": "Что сравниваем?",
    "cmp.pick_first": "Выбери первый компонент:",
    "cmp.pick_second": "Теперь выбери второй:",
    "cmp.reset": "🔄 Сравнить другие",
    "cmp.same": "Это один и тот же компонент. Выбери другой.",
    "cmp.price_note": "Цены ориентировочные.",
    "cmp.spec.cores": "Ядра",
    "cmp.spec.threads": "Потоки",
    "cmp.spec.socket": "Сокет",
    "cmp.spec.tdp": "Тепловыделение",
    "cmp.spec.memory_support": "Память",
    "cmp.spec.gaming_index": "Индекс в играх",
    "cmp.spec.perf_index": "Индекс производительности",
    "cmp.spec.vram": "Видеопамять",
    "cmp.spec.length": "Длина",
    "cmp.spec.psu_rec": "Рекомендуемый БП",
    "cmp.spec.ray_tracing": "Трассировка лучей",
    "cmp.spec.upscaling": "Апскейлинг",
    "cmp.spec.memory_type": "Тип",
    "cmp.spec.capacity": "Объём",
    "cmp.spec.speed": "Частота",
    "cmp.spec.latency": "Задержка",
    "cmp.spec.read": "Чтение",
    "cmp.spec.write": "Запись",
    "cmp.spec.pcie": "PCIe",
    "cmp.spec.price": "Цена",
    "cmp.index_note": "Индексы — внутренняя оценка AmigoZT, не результат бенчмарка.",
    # --- accessories ---
    "menu.accessories": "🖱 Аксессуары",
    "acc.title": "🖱 <b>Аксессуары</b>",
    "acc.pick_category": "Что подобрать?",
    "acc.empty": "В этой категории пока пусто.",
    "acc.from": "от {price}",
    "acc.count": "Найдено: <b>{count}</b>",
    "acc.open_hint": "Открой товар кнопкой ниже.",
    "acc.price_note": "Цена ориентировочная — уточним при заказе.",
    "part.monitor": "🖥 Монитор",
    "part.mouse": "🖱 Мышь",
    "part.keyboard": "⌨️ Клавиатура",
    "part.headset": "🎧 Наушники",
    "part.microphone": "🎙 Микрофон",
    "part.webcam": "📷 Веб-камера",
    "part.speakers": "🔊 Колонки",
    "part.mousepad": "🟦 Коврик",
    "part.chair": "🪑 Кресло",
    "part.desk": "🗄 Стол",
    "acc.spec.size": "Диагональ",
    "acc.spec.resolution": "Разрешение",
    "acc.spec.refresh": "Частота",
    "acc.spec.panel": "Матрица",
    "acc.spec.response": "Отклик",
    "acc.spec.sync": "Adaptive Sync",
    "acc.spec.wireless": "Беспроводной",
    "acc.spec.colour": "Цвет",
    "acc.yes": "да",
    "acc.no": "нет",
    # --- visualisation ---
    "visual.show": "🔥 Показать мой ПК",
    "visual.look": "🖼️ Посмотреть, как выглядит",
    "visual.recolour": "🎨 Другой цвет",
    "visual.pick": "🎨 Выбери цвет подсветки и стиль:",
    "visual.style_gaming": "✨ Gaming",
    "visual.style_minimal": "◻️ Minimal",
    "visual.caption": (
        "Визуализация AmigoZT PC — так примерно будет выглядеть твоя сборка. Это не фото товара."
    ),
    "visual.stale": "Сборка не найдена. Собери конфигурацию заново.",
    "visual.product_caption": (
        "AI-визуализация товара по данным каталога — это не фотография, детали могут отличаться."
    ),
    "visual.generating": "🎨 Создаём визуализацию твоего ПК… обычно это занимает до минуты.",
    "visual.unavailable": (
        "Визуализация временно недоступна. Сборка, цена и заказ работают как обычно."
    ),
    "visual.ai_title": "🖼️ AI-визуализация твоей сборки",
    "visual.btn_change": "🔄 Изменить сборку",
    "visual.btn_back": "⬅️ Назад",
    "visual.caption_ai": (
        "AI-визуализация AmigoZT PC по выбранным комплектующим. "
        "Это сгенерированное изображение, а не фото конкретного экземпляра — "
        "детали могут отличаться."
    ),
    # --- pricing lines ---
    "build.components_line": "Комплектующие",
    "build.assembly_line": "Сборка и настройка · {tier}",
    "build.assembly_hint": (
        "В сборку входят подбор и проверка совместимости, сборка, "
        "кабель-менеджмент, BIOS/EXPO, драйверы и стресс-тест."
    ),
    "build.verified_note": "Цены комплектующих проверены по польским магазинам.",
    # --- my builds ---
    "mybuilds.empty": "У тебя пока нет сохранённых сборок. Начни с «🖥 Собрать ПК».",
    "mybuilds.title": "<b>Мои сборки</b>",
    "mybuilds.item": "{index}. {purpose} · {budget} PLN · {date}",
    "accent.red": "Красный",
    "accent.blue": "Синий",
    "accent.purple": "Фиолетовый",
    "accent.pink": "Розовый",
    "accent.green": "Зелёный",
    "accent.orange": "Оранжевый",
    "accent.yellow": "Жёлтый",
    "accent.cyan": "Бирюзовый",
    "accent.white": "Белый",
    "accent.silver": "Серебро",
    "accent.gold": "Золото",
    "accent.rainbow": "Радуга",
    "finish.black": "Чёрный",
    "finish.white": "Белый",
    "visual.image_footer": "Визуализация AmigoZT PC · не фотография товара · цена ориентировочная",
    "shelf.desc.starter": "Тихий компьютер для учёбы, работы и нетребовательных игр.",
    "shelf.desc.budget-gamer": "Первый игровой ПК: комфортный 1080p в популярных играх.",
    "shelf.desc.1080p-king": "Уверенные 144 FPS в 1080p с запасом на пару лет.",
    "shelf.desc.cs2-300": "Сборка под соревновательный CS2: приоритет процессору и частоте кадров.",
    "shelf.desc.cs2-500": "Максимум кадров в киберспортивных дисциплинах на 1080p.",
    "shelf.desc.fps-beast": "Для мониторов 360 Гц и выше: всё вложено в кадры.",
    "shelf.desc.1440p-sweet-spot": "Лучшее соотношение цены и кадров в 1440p.",
    "shelf.desc.1440p-high-fps": "240 Гц в 1440p: для тех, кто уже перерос 144.",
    "shelf.desc.white-dream": "Белая сборка целиком: корпус, охлаждение и подсветка в одном стиле.",
    "shelf.desc.black-rgb": "Чёрный корпус с подсветкой — классика игрового стола.",
    "shelf.desc.silent-gaming": (
        "Игровой ПК, которого почти не слышно: упор на охлаждение с запасом."
    ),
    "shelf.desc.streamer": "Игры и стрим одновременно: многопоточный процессор и много памяти.",
    "shelf.desc.creator": "Монтаж, графика и рендер: память, накопитель и видеокарта с VRAM.",
    "shelf.desc.4k-beast": "Комфортная игра в 4K с высокими настройками.",
    "shelf.desc.4k-high": "4K на высокой частоте обновления, без компромиссов по видеокарте.",
    "shelf.desc.workstation": "Рабочая станция: ядра, память и быстрый накопитель.",
    "shelf.desc.ai-workstation": (
        "Для локальных моделей: приоритет объёму видеопамяти и оперативной памяти."
    ),
    "shelf.desc.ultimate": (
        "Максимум, который имеет смысл собрать: топовая связка без компромиссов."
    ),
    "shelf.desc.amd-only": "Полностью AMD: Ryzen и Radeon в одной связке.",
    "shelf.desc.intel-nvidia": "Связка Intel Core и GeForce для игр и работы.",
    "cfg.monitor.q": "🖥 Нужен монитор к этому ПК?",
    "cfg.monitor.hint": "Показываю только те, что тянут выбранное разрешение.",
    "cfg.monitor.skip": "➡️ Без монитора",
    "cfg.monitor.continue": "✅ Продолжить с этим монитором",
    "cfg.peripherals.q": "🖱 Что добавить к столу?",
    "cfg.peripherals.hint": (
        "Можно выбрать несколько. Отмечено: <b>{count}</b>. Модель подберу под стиль твоей сборки."
    ),
    "cfg.peripherals.none": "В этой категории пока нечего предложить.",
    "setup.title": "Рабочее место",
    "setup.total": "Периферия:",
    "setup.grand_total": "Всего за комплект:",
    "build.lighting.featured": "Подсветка RGB: {parts}",
    "build.lighting.available": "Подсветка есть: {parts}",
    "build.lighting.addressable": "адресная ARGB",
    "build.lighting.unavailable": (
        "Подсветки в этой сборке нет: выбранные корпус, кулер и память её не дают"
    ),
    "build.lighting.hint_swap": "Скажи, если нужна подсветка — подберу детали с RGB.",
    "acc.spec.lighting": "Подсветка",
    "acc.spec.rgb": "RGB",
    "cfg.peripherals.clear": "❌ Убрать из сборки",
    "cfg.peripherals.back": "⬅️ К категориям",
    "cfg.peripherals.pick": "Выбери номер — подробности и цена на фото.",
    "summary.setup": "Рабочее место",
    "summary.variants": "Варианты сборки",
    "bot.description": (
        "AmigoZT PC — собираю компьютер под твой бюджет, игры и задачи. Проверяю совместимость "
        "деталей, считаю честную цену и показываю, как сборка будет выглядеть. 4 языка, ответ за "
        "минуту."
    ),
    "bot.short_description": (
        "Подбор ПК под бюджет и задачи: совместимость, честная цена, визуализация сборки."
    ),
    "acc.kind.monitor": "Монитор",
    "acc.kind.mouse": "Мышь",
    "acc.kind.keyboard": "Клавиатура",
    "acc.kind.headset": "Гарнитура",
    "acc.kind.microphone": "Микрофон",
    "acc.kind.webcam": "Веб-камера",
    "acc.kind.speakers": "Колонки",
    "acc.kind.mousepad": "Коврик",
    "acc.kind.chair": "Кресло",
    "acc.kind.desk": "Стол",
    "acc.kind.lighting": "Подсветка",
    "acc.trait.wired": "проводная",
    "acc.trait.wireless": "беспроводная",
    "acc.trait.rgb": "с подсветкой",
}
