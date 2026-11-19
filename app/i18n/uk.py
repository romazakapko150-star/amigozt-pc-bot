"""Ukrainian locale."""

TEXTS: dict[str, str] = {
    # --- generic ---
    "start.title": "<b>AMIGOZT PC</b>",
    "start.tagline": (
        "Збери комп'ютер під свій бюджет, ігри та задачі.\n"
        "Я підберу сумісні комплектуючі та поясню, чому саме їх варто обрати."
    ),
    "menu.prompt": "Обери, з чого почнемо:",
    "menu.build": "🖥 Зібрати ПК",
    "menu.budget": "💰 ПК за бюджетом",
    "menu.games": "🎮 ПК для ігор",
    "menu.presets": "⚡ Готові збірки",
    "menu.compare": "🔄 Порівняти деталі",
    "menu.mybuilds": "💾 Мої збірки",
    "menu.about": "ℹ️ Про проєкт",
    "menu.help": "❓ Допомога",
    "menu.language": "🌐 Мова",
    "nav.back": "⬅️ Назад",
    "nav.cancel": "❌ Скасувати",
    "nav.restart": "🔄 Почати спочатку",
    "nav.menu": "🏠 Головне меню",
    "nav.skip": "⏭ Пропустити",
    "nav.done": "✅ Готово",
    "nav.yes": "Так",
    "nav.no": "Ні",
    "nav.auto": "🤖 Підібрати автоматично",
    "nav.custom": "✏️ Свій варіант",
    "common.error": "Сталася помилка. Спробуй ще раз.",
    "common.rate_limited": "Забагато запитів. Зачекай пару секунд 🙂",
    "common.cancelled": "Конфігуратор зупинено. Повертаю до головного меню.",
    "common.coming_soon": "Цей розділ скоро з'явиться. Поки що спробуй «🖥 Зібрати ПК».",
    "common.progress": "Крок {current} з {total}",
    "common.unknown_action": "Не зрозумів дію. Відкрий меню командою /start.",
    "about.text": (
        "<b>AmigoZT PC</b> — AI-сервіс підбору комп'ютерів.\n\n"
        "Ти відповідаєш на прості запитання, а я:\n"
        "• підбираю комплектуючі під бюджет і задачі;\n"
        "• перевіряю сумісність усіх деталей;\n"
        "• оптимізую збірку за співвідношенням ціна/продуктивність;\n"
        "• рахую підсумкову ціну в PLN та орієнтовний FPS.\n\n"
        "Ринок: Польща 🇵🇱 · Валюта: PLN"
    ),
    "help.text": (
        "<b>Команди</b>\n"
        "/start — головне меню\n"
        "/build — зібрати ПК\n"
        "/budget — підбір за бюджетом\n"
        "/mybuilds — мої збірки\n"
        "/language — змінити мову\n"
        "/help — ця довідка\n\n"
        "У конфігураторі завжди доступні кнопки «⬅️ Назад» та «❌ Скасувати»."
    ),
    "lang.prompt": "Обери мову інтерфейсу:",
    "lang.changed": "Мову змінено на українську 🇺🇦",
    # --- configurator ---
    "cfg.budget.q": "💰 Який у тебе бюджет на комп'ютер?",
    "cfg.budget.hint": "Це бюджет на системний блок. Монітор і периферію рахуємо окремо.",
    "cfg.budget.custom_prompt": "Напиши свій бюджет у PLN числом.\nНаприклад: <code>5500</code>",
    "cfg.budget.invalid": (
        "Не вдалося розпізнати суму. Введи число в PLN від {min} до {max}.\n"
        "Наприклад: <code>5500</code>"
    ),
    "cfg.purpose.q": "🎯 Для чого потрібен комп'ютер?",
    "purpose.gaming": "🎮 Ігри",
    "purpose.gaming_streaming": "🎥 Ігри + стримінг",
    "purpose.work": "💻 Робота",
    "purpose.design": "🎨 Дизайн / відео",
    "purpose.ai_ml": "🤖 AI / ML",
    "purpose.workstation": "💼 Робоча станція",
    "purpose.universal": "🔥 Універсальний",
    "cfg.games.q": "🎮 У що граєш?",
    "cfg.games.hint": "Можна обрати декілька. Обрано: <b>{count}</b>",
    "cfg.games.other": "✏️ Інша гра",
    "cfg.games.custom_prompt": "Напиши назву гри одним повідомленням.",
    "cfg.games.invalid": "Назва порожня або задовга. Спробуй ще раз.",
    "cfg.games.limit": "Більше ніж {max} ігор за раз обрати не можна.",
    "cfg.resolution.q": "🖥 У якій роздільній здатності гратимеш або працюватимеш?",
    "resolution.1080p": "1080p (Full HD)",
    "resolution.1440p": "1440p (2K)",
    "resolution.4k": "4K (Ultra HD)",
    "cfg.fps.q": "⚡ Скільки FPS хочеш отримувати?",
    "cfg.priority.q": "🧭 Що для тебе важливо в цьому ПК?",
    "cfg.priority.hint": (
        "Можна обрати кілька — до <b>{max}</b>. Позначено: <b>{count}</b>. Потім натисни «Готово»."
    ),
    "cfg.priority.limit": "Більше ніж {max} пріоритетів за раз обрати не можна.",
    "cfg.priority.pick_one": "Познач хоча б один пріоритет.",
    "priority.max_fps": "⚡ Максимальний FPS",
    "priority.price_performance": "💰 Ціна / продуктивність",
    "priority.silence": "🤫 Тиша",
    "priority.cooling": "❄️ Охолодження",
    "priority.looks": "🎨 Зовнішній вигляд",
    "priority.versatility": "🧠 Універсальність",
    "priority.efficiency": "🔌 Низьке енергоспоживання",
    "priority.compact": "📦 Компактний розмір",
    "priority.upgradeability": "🔧 Запас на апгрейд",
    "cfg.aesthetics.q": "🎨 Як має виглядати комп'ютер?",
    "aesthetics.black": "⚫ Чорний",
    "aesthetics.white": "⚪ Білий",
    "aesthetics.black_rgb": "⚫ Чорний + RGB",
    "aesthetics.white_rgb": "⚪ Білий + RGB",
    "aesthetics.minimal": "◻️ Мінімалізм",
    "aesthetics.gaming": "🔥 Ігровий стиль",
    "cfg.connectivity.q": "📶 Чи потрібні Wi-Fi та Bluetooth?",
    "connectivity.wifi_bt": "📶 Wi-Fi + Bluetooth",
    "connectivity.wifi": "📶 Тільки Wi-Fi",
    "connectivity.bt": "🔵 Тільки Bluetooth",
    "connectivity.none": "🔌 Не потрібні (кабель)",
    "cfg.storage.q": "💾 Скільки місця потрібно для ігор і файлів?",
    "cfg.ram.q": "🧠 Скільки оперативної пам'яті потрібно?",
    "cfg.ram.hint": "Якщо не впевнений — довір вибір мені.",
    "cfg.cpu.q": "🧩 Є вподобання щодо процесора?",
    "cfg.gpu.q": "🖼 Є вподобання щодо відеокарти?",
    "brand.any": "🤝 Без різниці",
    # --- summary ---
    "summary.title": "<b>Твої вимоги</b>",
    "summary.budget": "Бюджет",
    "summary.purpose": "Призначення",
    "summary.games": "Ігри",
    "summary.resolution": "Роздільна здатність",
    "summary.fps": "Цільовий FPS",
    "summary.priority": "Пріоритет",
    "summary.aesthetics": "Зовнішній вигляд",
    "summary.connectivity": "Підключення",
    "summary.storage": "Накопичувач",
    "summary.ram": "Пам'ять",
    "summary.cpu": "Процесор",
    "summary.gpu": "Відеокарта",
    "summary.auto": "на мій розсуд",
    "summary.none": "не вказано",
    "summary.next": (
        "Вимоги збережено ✅\n\nНаступний крок — підбір сумісних комплектуючих і розрахунок ціни."
    ),
    "summary.btn_generate": "🚀 Підібрати збірку",
    "summary.generate_pending": (
        "⚙️ Підбір комплектуючих готується до запуску.\n\n"
        "База компонентів і рушій сумісності підключаються на наступному етапі — "
        "твої вимоги вже збережені й будуть використані автоматично."
    ),
    # --- order ---
    "order.button": "🛒 Хочу замовити",
    "order.created": (
        "Заявку <b>#{lead_id}</b> створено ✅\n\n"
        "Я передав її команді AmigoZT PC — зв'яжемося з тобою в Telegram найближчим часом."
    ),
    "order.exists": "Заявка <b>#{lead_id}</b> вже оформлена. Ми її опрацьовуємо 👌",
    "order.expired": "Вимоги застаріли. Збери конфігурацію заново — це займе хвилину.",
    "summary.ready": "✅ <b>Вимоги готові</b>",
    "summary.hint_next": "Усе вірно? Тоді подавай заявку.",
    "order.confirm_q": "Оформити заявку на цю конфігурацію?",
    "order.confirm_yes": "✅ Так, подати заявку",
    "order.edit": "✏️ Змінити",
    "order.cancelled": "Заявку не надіслано.",
    "summary.btn_save": "💾 Зберегти",
    # --- build card ---
    "build.ready": "🎉 <b>Твоя збірка готова</b>",
    "build.tier.budget": "💰 BUDGET",
    "build.tier.optimal": "⚖️ OPTIMAL",
    "build.tier.performance": "🔥 PERFORMANCE",
    "build.total": "Разом",
    "build.approx": "Ціна орієнтовна — уточнимо під час підтвердження замовлення.",
    "build.legacy_note": "⚠️ Платформа без запасу на апгрейд процесора.",
    "build.fps_unavailable": "Недостатньо benchmark-даних для надійної оцінки FPS.",
    "build.warnings": "На що звернути увагу",
    "build.none": (
        "Під цей бюджет зібрати сумісний ПК не вийде.\n"
        "\n"
        "Мінімум для такої конфігурації — приблизно <b>{minimum}</b>."
    ),
    "build.none_generic": "Не вдалося зібрати конфігурацію. Спробуй змінити параметри.",
    "build.btn_other": "🔄 Інший варіант",
    "part.cpu": "🧠 Процесор",
    "part.gpu": "🎮 Відеокарта",
    "part.motherboard": "🧩 Материнська плата",
    "part.ram": "🧠 Пам'ять",
    "part.ssd": "💾 Накопичувач",
    "part.psu": "🔌 Блок живлення",
    "part.case": "📦 Корпус",
    "part.cooler": "❄️ Охолодження",
    # --- compatibility notes ---
    "compat.memory_speed": "Памʼять працюватиме на частоті, яку підтримує платформа.",
    "compat.psu_tight": "Блок живлення без великого запасу під майбутній апгрейд.",
    "compat.ssd_pcie_generation": "SSD працюватиме на швидкості шини материнської плати.",
    "compat.bios_update": (
        "Материнській платі може знадобитися оновлення BIOS під цей процесор — зробимо це під "
        "час збирання."
    ),
    "compat.gpu_power_adapter": "Відеокарта підключається через перехідник живлення з комплекту.",
    "compat.front_usb_c": (
        "USB-C на передній панелі корпусу не підключиться до цієї плати без перехідника."
    ),
    "compat.memory_four_modules": (
        "Чотири модулі памʼяті можуть працювати нижче заявленої частоти — два модулі стабільніші."
    ),
    "compat.memory_profile": "Профіль памʼяті (EXPO/XMP) може потребувати ручного налаштування.",
    "compat.monitor_output": (
        "Для потрібного режиму монітора перевір кабель і розʼєм — не кожен порт його підтримує."
    ),
    "order.blocked": "⚠️ <b>Потрібно трохи змінити збірку</b>",
    "order.blocked_hint": (
        "Перевірка перед замовленням знайшла несумісність. Заявку не надіслано — підберімо заново."
    ),
    "order.btn_regenerate": "🔄 Підібрати заново",
    "compat.block.gpu_too_long": "Обрана відеокарта задовга для цього корпусу.",
    "compat.block.gpu_front_radiator": (
        "Відеокарта і радіатор СРО спереду не вміщуються разом у цей корпус."
    ),
    "compat.block.gpu_slots": "Відеокарта затовста для цього корпусу.",
    "compat.block.board_form_factor": (
        "Материнська плата не підходить за форматом до цього корпусу."
    ),
    "compat.block.cooler_too_tall": "Кулер процесора зависокий для цього корпусу.",
    "compat.block.radiator_unsupported": "У цьому корпусі немає місця під радіатор обраної СРО.",
    "compat.block.psu_too_long": "Блок живлення задовгий для цього корпусу.",
    "compat.block.psu_form_factor": "Блок живлення не підходить за форматом до цього корпусу.",
    "compat.block.psu_underpowered": "Потужності блока живлення не вистачає для цієї конфігурації.",
    "compat.block.psu_gpu_minimum": (
        "Блок живлення слабший за мінімум, який вимагає виробник відеокарти."
    ),
    "compat.block.gpu_power_connector": (
        "У блока живлення немає потрібних розʼємів для цієї відеокарти."
    ),
    "compat.block.socket_mismatch": "Процесор і материнська плата на різних сокетах.",
    "compat.block.memory_type_mismatch": "Тип памʼяті не підходить до материнської плати.",
    "compat.block.argb_header": "Підсвітці бракує розʼєму на материнській платі.",
    "compat.block.missing_part": "У збірці бракує обовʼязкового компонента.",
    "compat.block.generic": "Одна з комбінацій комплектуючих не підтверджена як сумісна.",
    # --- ready builds ---
    "ready.title": "⚡ <b>Готові збірки</b>",
    "ready.pick_filter": "Обери, що показати:",
    "ready.all": "📋 Усі збірки",
    "ready.by_budget": "💰 За бюджетом",
    "ready.empty": "У цій категорії поки порожньо.",
    "ready.count": "Знайдено: <b>{count}</b>",
    "ready.page": "Стор. {page} з {total}",
    "ready.open_hint": "Відкрий збірку кнопкою нижче.",
    "ready.prev": "⬅️",
    "ready.next": "➡️",
    "ready.cat.budget": "💰 Бюджетні",
    "ready.cat.gaming": "🎮 Ігрові",
    "ready.cat.high_fps": "⚡ High FPS",
    "ready.cat.performance": "🔥 Performance",
    "ready.cat.high_end": "👑 High-End",
    "ready.cat.extreme": "💎 Extreme",
    "ready.cat.streaming": "🎥 Стримінг",
    "ready.cat.design": "🎨 Дизайн",
    "ready.cat.ai": "🤖 AI / ML",
    "ready.cat.workstation": "💼 Workstation",
    "ready.cat.white": "🤍 Білі",
    "ready.cat.rgb": "🌈 RGB",
    "ready.cat.quiet": "🤫 Тихі",
    "ready.budget.under": "до {value}",
    "ready.budget.over": "від {value}",
    "ready.stale": "Збірка тимчасово недоступна. Обери іншу.",
    # --- compare ---
    "cmp.title": "🔄 <b>Порівняння комплектуючих</b>",
    "cmp.pick_category": "Що порівнюємо?",
    "cmp.pick_first": "Обери перший компонент:",
    "cmp.pick_second": "Тепер обери другий:",
    "cmp.reset": "🔄 Порівняти інші",
    "cmp.same": "Це той самий компонент. Обери інший.",
    "cmp.price_note": "Ціни орієнтовні.",
    "cmp.spec.cores": "Ядра",
    "cmp.spec.threads": "Потоки",
    "cmp.spec.socket": "Сокет",
    "cmp.spec.tdp": "Тепловиділення",
    "cmp.spec.memory_support": "Памʼять",
    "cmp.spec.gaming_index": "Індекс в іграх",
    "cmp.spec.perf_index": "Індекс продуктивності",
    "cmp.spec.vram": "Відеопамʼять",
    "cmp.spec.length": "Довжина",
    "cmp.spec.psu_rec": "Рекомендований БЖ",
    "cmp.spec.ray_tracing": "Трасування променів",
    "cmp.spec.upscaling": "Апскейлінг",
    "cmp.spec.memory_type": "Тип",
    "cmp.spec.capacity": "Обсяг",
    "cmp.spec.speed": "Частота",
    "cmp.spec.latency": "Затримка",
    "cmp.spec.read": "Читання",
    "cmp.spec.write": "Запис",
    "cmp.spec.pcie": "PCIe",
    "cmp.spec.price": "Ціна",
    "cmp.index_note": "Індекси — внутрішня оцінка AmigoZT, не результат бенчмарку.",
    # --- accessories ---
    "menu.accessories": "🖱 Аксесуари",
    "acc.title": "🖱 <b>Аксесуари</b>",
    "acc.pick_category": "Що підібрати?",
    "acc.empty": "У цій категорії поки порожньо.",
    "acc.from": "від {price}",
    "acc.count": "Знайдено: <b>{count}</b>",
    "acc.open_hint": "Відкрий товар кнопкою нижче.",
    "acc.price_note": "Ціна орієнтовна — уточнимо при замовленні.",
    "part.monitor": "🖥 Монітор",
    "part.mouse": "🖱 Миша",
    "part.keyboard": "⌨️ Клавіатура",
    "part.headset": "🎧 Навушники",
    "part.microphone": "🎙 Мікрофон",
    "part.webcam": "📷 Вебкамера",
    "part.speakers": "🔊 Колонки",
    "part.mousepad": "🟦 Килимок",
    "part.chair": "🪑 Крісло",
    "part.desk": "🗄 Стіл",
    "acc.spec.size": "Діагональ",
    "acc.spec.resolution": "Роздільна здатність",
    "acc.spec.refresh": "Частота",
    "acc.spec.panel": "Матриця",
    "acc.spec.response": "Відгук",
    "acc.spec.sync": "Adaptive Sync",
    "acc.spec.wireless": "Бездротовий",
    "acc.spec.colour": "Колір",
    "acc.yes": "так",
    "acc.no": "ні",
    # --- visualisation ---
    "visual.show": "🔥 Показати мій ПК",
    "visual.look": "🖼️ Подивитись, як виглядає",
    "visual.recolour": "🎨 Інший колір",
    "visual.pick": "🎨 Обери колір підсвітки та стиль:",
    "visual.style_gaming": "✨ Gaming",
    "visual.style_minimal": "◻️ Minimal",
    "visual.caption": (
        "Візуалізація AmigoZT PC — так приблизно виглядатиме твоя збірка. Це не фото товару."
    ),
    "visual.stale": "Збірку не знайдено. Збери конфігурацію заново.",
    "visual.product_caption": (
        "AI-візуалізація товару за даними каталогу — це не фотографія, деталі можуть відрізнятися."
    ),
    "visual.generating": "🎨 Створюємо візуалізацію твого ПК… зазвичай це займає до хвилини.",
    "visual.unavailable": (
        "Візуалізація тимчасово недоступна. Збірка, ціна та замовлення працюють як звичайно."
    ),
    "visual.ai_title": "🖼️ AI-візуалізація твоєї збірки",
    "visual.btn_change": "🔄 Змінити збірку",
    "visual.btn_back": "⬅️ Назад",
    "visual.caption_ai": (
        "AI-візуалізація AmigoZT PC за обраними комплектуючими. "
        "Це згенероване зображення, а не фото конкретного екземпляра — деталі можуть відрізнятися."
    ),
    # --- pricing lines ---
    "build.components_line": "Комплектуючі",
    "build.assembly_line": "Збирання та налаштування · {tier}",
    "build.assembly_hint": (
        "Збирання включає підбір і перевірку сумісності, монтаж, "
        "кабель-менеджмент, BIOS/EXPO, драйвери та стрес-тест."
    ),
    "build.verified_note": "Ціни комплектуючих перевірені в польських магазинах.",
    # --- my builds ---
    "mybuilds.empty": "У тебе поки немає збережених збірок. Почни з «🖥 Зібрати ПК».",
    "mybuilds.title": "<b>Мої збірки</b>",
    "mybuilds.item": "{index}. {purpose} · {budget} PLN · {date}",
    "accent.red": "Червоний",
    "accent.blue": "Синій",
    "accent.purple": "Фіолетовий",
    "accent.pink": "Рожевий",
    "accent.green": "Зелений",
    "accent.orange": "Помаранчевий",
    "accent.yellow": "Жовтий",
    "accent.cyan": "Бірюзовий",
    "accent.white": "Білий",
    "accent.silver": "Срібло",
    "accent.gold": "Золото",
    "accent.rainbow": "Райдуга",
    "finish.black": "Чорний",
    "finish.white": "Білий",
    "visual.image_footer": "Візуалізація AmigoZT PC · не фотографія товару · ціна орієнтовна",
    "shelf.desc.starter": "Тихий комп'ютер для навчання, роботи та невибагливих ігор.",
    "shelf.desc.budget-gamer": "Перший ігровий ПК: комфортний 1080p у популярних іграх.",
    "shelf.desc.1080p-king": "Впевнені 144 FPS у 1080p із запасом на кілька років.",
    "shelf.desc.cs2-300": "Збірка під змагальний CS2: пріоритет процесору та частоті кадрів.",
    "shelf.desc.cs2-500": "Максимум кадрів у кіберспортивних дисциплінах на 1080p.",
    "shelf.desc.fps-beast": "Для моніторів 360 Гц і вище: усе вкладено в кадри.",
    "shelf.desc.1440p-sweet-spot": "Найкраще співвідношення ціни та кадрів у 1440p.",
    "shelf.desc.1440p-high-fps": "240 Гц у 1440p: для тих, хто вже переріс 144.",
    "shelf.desc.white-dream": (
        "Повністю біла збірка: корпус, охолодження та підсвітка в одному стилі."
    ),
    "shelf.desc.black-rgb": "Чорний корпус із підсвіткою — класика ігрового столу.",
    "shelf.desc.silent-gaming": "Ігровий ПК, якого майже не чути: охолодження із запасом.",
    "shelf.desc.streamer": "Ігри та стрім одночасно: багатопотоковий процесор і багато пам'яті.",
    "shelf.desc.creator": "Монтаж, графіка та рендер: пам'ять, накопичувач і відеокарта з VRAM.",
    "shelf.desc.4k-beast": "Комфортна гра в 4K з високими налаштуваннями.",
    "shelf.desc.4k-high": "4K на високій частоті оновлення, без компромісів щодо відеокарти.",
    "shelf.desc.workstation": "Робоча станція: ядра, пам'ять і швидкий накопичувач.",
    "shelf.desc.ai-workstation": (
        "Для локальних моделей: пріоритет обсягу відеопам'яті та оперативної пам'яті."
    ),
    "shelf.desc.ultimate": "Максимум, який має сенс зібрати: топова зв'язка без компромісів.",
    "shelf.desc.amd-only": "Повністю AMD: Ryzen і Radeon в одній зв'язці.",
    "shelf.desc.intel-nvidia": "Зв'язка Intel Core і GeForce для ігор та роботи.",
    "cfg.monitor.q": "🖥 Потрібен монітор до цього ПК?",
    "cfg.monitor.hint": "Показую лише ті, що тягнуть обрану роздільну здатність.",
    "cfg.monitor.skip": "➡️ Без монітора",
    "cfg.monitor.continue": "✅ Продовжити з цим монітором",
    "cfg.peripherals.q": "🖱 Що додати до столу?",
    "cfg.peripherals.hint": (
        "Можна обрати кілька. Позначено: <b>{count}</b>. Модель підберу під стиль твоєї збірки."
    ),
    "cfg.peripherals.none": "У цій категорії поки що немає що запропонувати.",
    "setup.title": "Робоче місце",
    "setup.total": "Периферія:",
    "setup.grand_total": "Разом за комплект:",
    "build.lighting.featured": "Підсвітка RGB: {parts}",
    "build.lighting.available": "Підсвітка є: {parts}",
    "build.lighting.addressable": "адресна ARGB",
    "build.lighting.unavailable": (
        "Підсвітки в цій збірці немає: обрані корпус, кулер і пам'ять її не дають"
    ),
    "build.lighting.hint_swap": "Скажи, якщо потрібна підсвітка — підберу деталі з RGB.",
    "acc.spec.lighting": "Підсвітка",
    "acc.spec.rgb": "RGB",
    "cfg.peripherals.clear": "❌ Прибрати зі збірки",
    "cfg.peripherals.back": "⬅️ До категорій",
    "cfg.peripherals.pick": "Обери номер — на фото модель і ціна.",
    "summary.setup": "Робоче місце",
    "summary.variants": "Варіанти збірки",
    "bot.description": (
        "AmigoZT PC — збираю комп'ютер під твій бюджет, ігри та задачі. Перевіряю сумісність "
        "деталей, рахую чесну ціну і показую, як збірка виглядатиме. Чотири мови, відповідь за "
        "хвилину."
    ),
    "bot.short_description": (
        "Підбір ПК під бюджет: перевірена сумісність, чесна ціна, візуалізація збірки."
    ),
    "acc.kind.monitor": "Монітор",
    "acc.kind.mouse": "Миша",
    "acc.kind.keyboard": "Клавіатура",
    "acc.kind.headset": "Гарнітура",
    "acc.kind.microphone": "Мікрофон",
    "acc.kind.webcam": "Вебкамера",
    "acc.kind.speakers": "Колонки",
    "acc.kind.mousepad": "Килимок",
    "acc.kind.chair": "Крісло",
    "acc.kind.desk": "Стіл",
    "acc.kind.lighting": "Підсвітка",
    "acc.trait.wired": "дротова",
    "acc.trait.wireless": "бездротова",
    "acc.trait.rgb": "з підсвіткою",
}
