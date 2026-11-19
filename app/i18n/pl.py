"""Polish locale."""

TEXTS: dict[str, str] = {
    # --- generic ---
    "start.title": "<b>AMIGOZT PC</b>",
    "start.tagline": (
        "Złóż komputer pod swój budżet, gry i zadania.\n"
        "Dobiorę kompatybilne podzespoły i wyjaśnię, dlaczego warto wybrać właśnie te."
    ),
    "menu.prompt": "Wybierz, od czego zaczynamy:",
    "menu.build": "🖥 Złóż PC",
    "menu.budget": "💰 PC wg budżetu",
    "menu.games": "🎮 PC do gier",
    "menu.presets": "⚡ Gotowe zestawy",
    "menu.compare": "🔄 Porównaj części",
    "menu.mybuilds": "💾 Moje zestawy",
    "menu.about": "ℹ️ O projekcie",
    "menu.help": "❓ Pomoc",
    "menu.language": "🌐 Język",
    "nav.back": "⬅️ Wstecz",
    "nav.cancel": "❌ Anuluj",
    "nav.restart": "🔄 Zacznij od nowa",
    "nav.menu": "🏠 Menu główne",
    "nav.skip": "⏭ Pomiń",
    "nav.done": "✅ Gotowe",
    "nav.yes": "Tak",
    "nav.no": "Nie",
    "nav.auto": "🤖 Dobierz automatycznie",
    "nav.custom": "✏️ Własna opcja",
    "common.error": "Wystąpił błąd. Spróbuj jeszcze raz.",
    "common.rate_limited": "Za dużo zapytań. Poczekaj chwilę 🙂",
    "common.cancelled": "Konfigurator zatrzymany. Wracam do menu głównego.",
    "common.coming_soon": "Ta sekcja będzie dostępna wkrótce. Na razie wybierz „🖥 Złóż PC”.",
    "common.progress": "Krok {current} z {total}",
    "common.unknown_action": "Nie rozpoznaję tej akcji. Otwórz menu komendą /start.",
    "about.text": (
        "<b>AmigoZT PC</b> — serwis AI do doboru komputerów.\n\n"
        "Ty odpowiadasz na proste pytania, a ja:\n"
        "• dobieram podzespoły pod budżet i zadania;\n"
        "• sprawdzam kompatybilność wszystkich części;\n"
        "• optymalizuję zestaw pod stosunek ceny do wydajności;\n"
        "• liczę końcową cenę w PLN i szacowany FPS.\n\n"
        "Rynek: Polska 🇵🇱 · Waluta: PLN"
    ),
    "help.text": (
        "<b>Komendy</b>\n"
        "/start — menu główne\n"
        "/build — złóż PC\n"
        "/budget — dobór wg budżetu\n"
        "/mybuilds — moje zestawy\n"
        "/language — zmień język\n"
        "/help — ta pomoc\n\n"
        "W konfiguratorze zawsze dostępne są przyciski „⬅️ Wstecz” i „❌ Anuluj”."
    ),
    "lang.prompt": "Wybierz język interfejsu:",
    "lang.changed": "Język zmieniony na polski 🇵🇱",
    # --- configurator ---
    "cfg.budget.q": "💰 Jaki masz budżet na komputer?",
    "cfg.budget.hint": "To budżet na jednostkę centralną. Monitor i peryferia liczymy osobno.",
    "cfg.budget.custom_prompt": (
        "Napisz swój budżet w PLN liczbą.\nNa przykład: <code>5500</code>"
    ),
    "cfg.budget.invalid": (
        "Nie rozpoznałem kwoty. Podaj liczbę w PLN od {min} do {max}.\n"
        "Na przykład: <code>5500</code>"
    ),
    "cfg.purpose.q": "🎯 Do czego potrzebujesz komputera?",
    "purpose.gaming": "🎮 Gry",
    "purpose.gaming_streaming": "🎥 Gry + streaming",
    "purpose.work": "💻 Praca",
    "purpose.design": "🎨 Design / wideo",
    "purpose.ai_ml": "🤖 AI / ML",
    "purpose.workstation": "💼 Stacja robocza",
    "purpose.universal": "🔥 Uniwersalny",
    "cfg.games.q": "🎮 W co grasz?",
    "cfg.games.hint": "Możesz wybrać kilka. Wybrano: <b>{count}</b>",
    "cfg.games.other": "✏️ Inna gra",
    "cfg.games.custom_prompt": "Napisz nazwę gry w jednej wiadomości.",
    "cfg.games.invalid": "Nazwa jest pusta lub za długa. Spróbuj ponownie.",
    "cfg.games.limit": "Nie można wybrać więcej niż {max} gier naraz.",
    "cfg.resolution.q": "🖥 W jakiej rozdzielczości będziesz grać lub pracować?",
    "resolution.1080p": "1080p (Full HD)",
    "resolution.1440p": "1440p (2K)",
    "resolution.4k": "4K (Ultra HD)",
    "cfg.fps.q": "⚡ Ile FPS chcesz osiągać?",
    "cfg.priority.q": "🧭 Co jest dla Ciebie ważne w tym komputerze?",
    "cfg.priority.hint": (
        "Możesz wybrać kilka - maksymalnie <b>{max}</b>. Zaznaczono: <b>{count}</b>. "
        "Potem naciśnij „Gotowe”."
    ),
    "cfg.priority.limit": "Nie można wybrać więcej niż {max} priorytetów naraz.",
    "cfg.priority.pick_one": "Zaznacz przynajmniej jeden priorytet.",
    "priority.max_fps": "⚡ Maksymalny FPS",
    "priority.price_performance": "💰 Cena / wydajność",
    "priority.silence": "🤫 Cicha praca",
    "priority.cooling": "❄️ Chłodzenie",
    "priority.looks": "🎨 Wygląd",
    "priority.versatility": "🧠 Uniwersalność",
    "priority.efficiency": "🔌 Niskie zużycie energii",
    "priority.compact": "📦 Kompaktowy rozmiar",
    "priority.upgradeability": "🔧 Zapas na rozbudowę",
    "cfg.aesthetics.q": "🎨 Jak ma wyglądać komputer?",
    "aesthetics.black": "⚫ Czarny",
    "aesthetics.white": "⚪ Biały",
    "aesthetics.black_rgb": "⚫ Czarny + RGB",
    "aesthetics.white_rgb": "⚪ Biały + RGB",
    "aesthetics.minimal": "◻️ Minimalizm",
    "aesthetics.gaming": "🔥 Styl gamingowy",
    "cfg.connectivity.q": "📶 Potrzebujesz Wi-Fi i Bluetooth?",
    "connectivity.wifi_bt": "📶 Wi-Fi + Bluetooth",
    "connectivity.wifi": "📶 Tylko Wi-Fi",
    "connectivity.bt": "🔵 Tylko Bluetooth",
    "connectivity.none": "🔌 Niepotrzebne (kabel)",
    "cfg.storage.q": "💾 Ile miejsca potrzebujesz na gry i pliki?",
    "cfg.ram.q": "🧠 Ile pamięci RAM potrzebujesz?",
    "cfg.ram.hint": "Jeśli nie masz pewności — zostaw wybór mnie.",
    "cfg.cpu.q": "🧩 Masz preferencje co do procesora?",
    "cfg.gpu.q": "🖼 Masz preferencje co do karty graficznej?",
    "brand.any": "🤝 Bez znaczenia",
    # --- summary ---
    "summary.title": "<b>Twoje wymagania</b>",
    "summary.budget": "Budżet",
    "summary.purpose": "Przeznaczenie",
    "summary.games": "Gry",
    "summary.resolution": "Rozdzielczość",
    "summary.fps": "Docelowy FPS",
    "summary.priority": "Priorytet",
    "summary.aesthetics": "Wygląd",
    "summary.connectivity": "Łączność",
    "summary.storage": "Dysk",
    "summary.ram": "Pamięć",
    "summary.cpu": "Procesor",
    "summary.gpu": "Karta graficzna",
    "summary.auto": "według mojego uznania",
    "summary.none": "nie podano",
    "summary.next": (
        "Wymagania zapisane ✅\n\n"
        "Następny krok — dobór kompatybilnych podzespołów i wyliczenie ceny."
    ),
    "summary.btn_generate": "🚀 Dobierz zestaw",
    "summary.generate_pending": (
        "⚙️ Dobór podzespołów jest przygotowywany do uruchomienia.\n\n"
        "Baza komponentów i silnik kompatybilności podłączane są na kolejnym etapie — "
        "Twoje wymagania są już zapisane i zostaną użyte automatycznie."
    ),
    # --- order ---
    "order.button": "🛒 Chcę zamówić",
    "order.created": (
        "Zgłoszenie <b>#{lead_id}</b> utworzone ✅\n\n"
        "Przekazałem je zespołowi AmigoZT PC — odezwiemy się na Telegramie wkrótce."
    ),
    "order.exists": "Zgłoszenie <b>#{lead_id}</b> już istnieje. Zajmujemy się nim 👌",
    "order.expired": "Wymagania są nieaktualne. Skonfiguruj zestaw ponownie — zajmie to minutę.",
    "summary.ready": "✅ <b>Wymagania gotowe</b>",
    "summary.hint_next": "Wszystko się zgadza? Wyślij zgłoszenie.",
    "order.confirm_q": "Wysłać zgłoszenie na tę konfigurację?",
    "order.confirm_yes": "✅ Tak, wyślij",
    "order.edit": "✏️ Zmień",
    "order.cancelled": "Zgłoszenie nie zostało wysłane.",
    "summary.btn_save": "💾 Zapisz",
    # --- build card ---
    "build.ready": "🎉 <b>Twój zestaw jest gotowy</b>",
    "build.tier.budget": "💰 BUDGET",
    "build.tier.optimal": "⚖️ OPTIMAL",
    "build.tier.performance": "🔥 PERFORMANCE",
    "build.total": "Razem",
    "build.approx": "Cena orientacyjna — potwierdzimy ją przy zamówieniu.",
    "build.legacy_note": "⚠️ Platforma bez zapasu na wymianę procesora.",
    "build.fps_unavailable": "Za mało danych benchmarkowych, by rzetelnie oszacować FPS.",
    "build.warnings": "Na co zwrócić uwagę",
    "build.none": (
        "W tym budżecie nie da się złożyć kompatybilnego PC.\n"
        "\n"
        "Minimum dla takiej konfiguracji to około <b>{minimum}</b>."
    ),
    "build.none_generic": "Nie udało się złożyć konfiguracji. Spróbuj zmienić parametry.",
    "build.btn_other": "🔄 Inny wariant",
    "part.cpu": "🧠 Procesor",
    "part.gpu": "🎮 Karta graficzna",
    "part.motherboard": "🧩 Płyta główna",
    "part.ram": "🧠 Pamięć",
    "part.ssd": "💾 Dysk",
    "part.psu": "🔌 Zasilacz",
    "part.case": "📦 Obudowa",
    "part.cooler": "❄️ Chłodzenie",
    # --- compatibility notes ---
    "compat.memory_speed": "Pamięć będzie pracować z częstotliwością wspieraną przez platformę.",
    "compat.psu_tight": "Zasilacz bez dużego zapasu na przyszłą rozbudowę.",
    "compat.ssd_pcie_generation": "SSD będzie pracować z prędkością magistrali płyty głównej.",
    "compat.bios_update": (
        "Płyta główna może wymagać aktualizacji BIOS pod ten procesor — zrobimy to przy montażu."
    ),
    "compat.gpu_power_adapter": (
        "Karta graficzna podłącza się przez przejściówkę zasilania z zestawu."
    ),
    "compat.front_usb_c": (
        "USB-C na przednim panelu obudowy nie podłączy się do tej płyty bez przejściówki."
    ),
    "compat.memory_four_modules": (
        "Cztery moduły pamięci mogą pracować poniżej deklarowanej częstotliwości — dwa moduły "
        "są stabilniejsze."
    ),
    "compat.memory_profile": "Profil pamięci (EXPO/XMP) może wymagać ręcznych ustawień.",
    "compat.monitor_output": (
        "Sprawdź kabel i port dla trybu monitora — nie każde wyjście go obsłuży."
    ),
    "order.blocked": "⚠️ <b>Zestaw wymaga małej zmiany</b>",
    "order.blocked_hint": (
        "Kontrola przed zamówieniem wykryła niezgodność. Nic nie wysłano — dobierzmy ponownie."
    ),
    "order.btn_regenerate": "🔄 Dobierz ponownie",
    "compat.block.gpu_too_long": "Wybrana karta graficzna jest za długa do tej obudowy.",
    "compat.block.gpu_front_radiator": (
        "Karta graficzna i chłodnica z przodu nie mieszczą się razem w tej obudowie."
    ),
    "compat.block.gpu_slots": "Karta graficzna jest za gruba do tej obudowy.",
    "compat.block.board_form_factor": "Format płyty głównej nie pasuje do tej obudowy.",
    "compat.block.cooler_too_tall": "Chłodzenie procesora jest za wysokie do tej obudowy.",
    "compat.block.radiator_unsupported": (
        "W tej obudowie nie ma miejsca na chłodnicę wybranego AiO."
    ),
    "compat.block.psu_too_long": "Zasilacz jest za długi do tej obudowy.",
    "compat.block.psu_form_factor": "Format zasilacza nie pasuje do tej obudowy.",
    "compat.block.psu_underpowered": "Moc zasilacza nie wystarcza dla tej konfiguracji.",
    "compat.block.psu_gpu_minimum": (
        "Zasilacz jest słabszy niż minimum wymagane przez producenta karty."
    ),
    "compat.block.gpu_power_connector": "Zasilacz nie ma złączy potrzebnych tej karcie graficznej.",
    "compat.block.socket_mismatch": "Procesor i płyta główna mają różne gniazda.",
    "compat.block.memory_type_mismatch": "Typ pamięci nie pasuje do płyty głównej.",
    "compat.block.argb_header": "Podświetlenie nie ma odpowiedniego złącza na płycie głównej.",
    "compat.block.missing_part": "W zestawie brakuje wymaganego komponentu.",
    "compat.block.generic": "Jedna z kombinacji części nie została potwierdzona jako zgodna.",
    # --- ready builds ---
    "ready.title": "⚡ <b>Gotowe zestawy</b>",
    "ready.pick_filter": "Wybierz, co pokazać:",
    "ready.all": "📋 Wszystkie zestawy",
    "ready.by_budget": "💰 Wg budżetu",
    "ready.empty": "W tej kategorii jeszcze pusto.",
    "ready.count": "Znaleziono: <b>{count}</b>",
    "ready.page": "Str. {page} z {total}",
    "ready.open_hint": "Otwórz zestaw przyciskiem poniżej.",
    "ready.prev": "⬅️",
    "ready.next": "➡️",
    "ready.cat.budget": "💰 Budżetowe",
    "ready.cat.gaming": "🎮 Do gier",
    "ready.cat.high_fps": "⚡ High FPS",
    "ready.cat.performance": "🔥 Performance",
    "ready.cat.high_end": "👑 High-End",
    "ready.cat.extreme": "💎 Extreme",
    "ready.cat.streaming": "🎥 Streaming",
    "ready.cat.design": "🎨 Design",
    "ready.cat.ai": "🤖 AI / ML",
    "ready.cat.workstation": "💼 Workstation",
    "ready.cat.white": "🤍 Białe",
    "ready.cat.rgb": "🌈 RGB",
    "ready.cat.quiet": "🤫 Ciche",
    "ready.budget.under": "do {value}",
    "ready.budget.over": "od {value}",
    "ready.stale": "Zestaw chwilowo niedostępny. Wybierz inny.",
    # --- compare ---
    "cmp.title": "🔄 <b>Porównanie podzespołów</b>",
    "cmp.pick_category": "Co porównujemy?",
    "cmp.pick_first": "Wybierz pierwszy podzespół:",
    "cmp.pick_second": "Teraz wybierz drugi:",
    "cmp.reset": "🔄 Porównaj inne",
    "cmp.same": "To ten sam podzespół. Wybierz inny.",
    "cmp.price_note": "Ceny orientacyjne.",
    "cmp.spec.cores": "Rdzenie",
    "cmp.spec.threads": "Wątki",
    "cmp.spec.socket": "Socket",
    "cmp.spec.tdp": "Pobór mocy",
    "cmp.spec.memory_support": "Pamięć",
    "cmp.spec.gaming_index": "Indeks w grach",
    "cmp.spec.perf_index": "Indeks wydajności",
    "cmp.spec.vram": "Pamięć VRAM",
    "cmp.spec.length": "Długość",
    "cmp.spec.psu_rec": "Zalecany zasilacz",
    "cmp.spec.ray_tracing": "Ray tracing",
    "cmp.spec.upscaling": "Skalowanie",
    "cmp.spec.memory_type": "Typ",
    "cmp.spec.capacity": "Pojemność",
    "cmp.spec.speed": "Taktowanie",
    "cmp.spec.latency": "Opóźnienie",
    "cmp.spec.read": "Odczyt",
    "cmp.spec.write": "Zapis",
    "cmp.spec.pcie": "PCIe",
    "cmp.spec.price": "Cena",
    "cmp.index_note": "Indeksy to wewnętrzna ocena AmigoZT, nie wynik benchmarku.",
    # --- accessories ---
    "menu.accessories": "🖱 Akcesoria",
    "acc.title": "🖱 <b>Akcesoria</b>",
    "acc.pick_category": "Co dobieramy?",
    "acc.empty": "W tej kategorii jeszcze pusto.",
    "acc.from": "od {price}",
    "acc.count": "Znaleziono: <b>{count}</b>",
    "acc.open_hint": "Otwórz produkt przyciskiem poniżej.",
    "acc.price_note": "Cena orientacyjna — potwierdzimy przy zamówieniu.",
    "part.monitor": "🖥 Monitor",
    "part.mouse": "🖱 Mysz",
    "part.keyboard": "⌨️ Klawiatura",
    "part.headset": "🎧 Słuchawki",
    "part.microphone": "🎙 Mikrofon",
    "part.webcam": "📷 Kamerka",
    "part.speakers": "🔊 Głośniki",
    "part.mousepad": "🟦 Podkładka",
    "part.chair": "🪑 Fotel",
    "part.desk": "🗄 Biurko",
    "acc.spec.size": "Przekątna",
    "acc.spec.resolution": "Rozdzielczość",
    "acc.spec.refresh": "Odświeżanie",
    "acc.spec.panel": "Matryca",
    "acc.spec.response": "Czas reakcji",
    "acc.spec.sync": "Adaptive Sync",
    "acc.spec.wireless": "Bezprzewodowy",
    "acc.spec.colour": "Kolor",
    "acc.yes": "tak",
    "acc.no": "nie",
    # --- visualisation ---
    "visual.show": "🔥 Pokaż mój PC",
    "visual.look": "🖼️ Zobacz, jak wygląda",
    "visual.recolour": "🎨 Inny kolor",
    "visual.pick": "🎨 Wybierz kolor podświetlenia i styl:",
    "visual.style_gaming": "✨ Gaming",
    "visual.style_minimal": "◻️ Minimal",
    "visual.caption": (
        "Wizualizacja AmigoZT PC — tak mniej więcej będzie wyglądał Twój zestaw. "
        "To nie jest zdjęcie produktu."
    ),
    "visual.stale": "Nie znaleziono zestawu. Skonfiguruj go ponownie.",
    "visual.product_caption": (
        "Wizualizacja AI produktu na podstawie danych katalogu — to nie zdjęcie, szczegóły "
        "mogą się różnić."
    ),
    "visual.generating": "🎨 Tworzymy wizualizację Twojego PC… zwykle trwa to do minuty.",
    "visual.unavailable": (
        "Wizualizacja jest chwilowo niedostępna. Zestaw, cena i zamówienie działają normalnie."
    ),
    "visual.ai_title": "🖼️ Wizualizacja AI Twojego zestawu",
    "visual.btn_change": "🔄 Zmień zestaw",
    "visual.btn_back": "⬅️ Wstecz",
    "visual.caption_ai": (
        "Wizualizacja AI AmigoZT PC na podstawie wybranych podzespołów. "
        "To obraz wygenerowany, nie zdjęcie konkretnego egzemplarza — szczegóły mogą się różnić."
    ),
    # --- pricing lines ---
    "build.components_line": "Podzespoły",
    "build.assembly_line": "Montaż i konfiguracja · {tier}",
    "build.assembly_hint": (
        "Montaż obejmuje dobór i sprawdzenie kompatybilności, złożenie, "
        "ułożenie kabli, BIOS/EXPO, sterowniki i test obciążeniowy."
    ),
    "build.verified_note": "Ceny podzespołów zweryfikowane w polskich sklepach.",
    # --- my builds ---
    "mybuilds.empty": "Nie masz jeszcze zapisanych zestawów. Zacznij od „🖥 Złóż PC”.",
    "mybuilds.title": "<b>Moje zestawy</b>",
    "mybuilds.item": "{index}. {purpose} · {budget} PLN · {date}",
    "accent.red": "Czerwony",
    "accent.blue": "Niebieski",
    "accent.purple": "Fioletowy",
    "accent.pink": "Różowy",
    "accent.green": "Zielony",
    "accent.orange": "Pomarańczowy",
    "accent.yellow": "Żółty",
    "accent.cyan": "Turkusowy",
    "accent.white": "Biały",
    "accent.silver": "Srebrny",
    "accent.gold": "Złoty",
    "accent.rainbow": "Tęcza",
    "finish.black": "Czarny",
    "finish.white": "Biały",
    "visual.image_footer": "Wizualizacja AmigoZT PC · to nie zdjęcie produktu · cena orientacyjna",
    "shelf.desc.starter": "Cichy komputer do nauki, pracy i mniej wymagających gier.",
    "shelf.desc.budget-gamer": "Pierwszy komputer do gier: wygodne 1080p w popularnych tytułach.",
    "shelf.desc.1080p-king": "Pewne 144 FPS w 1080p, z zapasem na kilka lat.",
    "shelf.desc.cs2-300": (
        "Zestaw pod turniejowe CS2: procesor i liczba klatek na pierwszym miejscu."
    ),
    "shelf.desc.cs2-500": "Maksimum klatek w e-sporcie na 1080p.",
    "shelf.desc.fps-beast": "Do monitorów 360 Hz i wyżej: wszystko idzie w klatki.",
    "shelf.desc.1440p-sweet-spot": "Najlepszy stosunek ceny do klatek w 1440p.",
    "shelf.desc.1440p-high-fps": "240 Hz w 1440p dla tych, którym 144 już nie wystarcza.",
    "shelf.desc.white-dream": "Cała biała: obudowa, chłodzenie i podświetlenie w jednym stylu.",
    "shelf.desc.black-rgb": "Czarna obudowa z podświetleniem - klasyka biurka gracza.",
    "shelf.desc.silent-gaming": (
        "Komputer do gier, którego prawie nie słychać: chłodzenie z zapasem."
    ),
    "shelf.desc.streamer": "Granie i streaming naraz: wielowątkowy procesor i dużo pamięci.",
    "shelf.desc.creator": "Montaż, grafika i rendering: pamięć, dysk i karta z VRAM.",
    "shelf.desc.4k-beast": "Wygodne granie w 4K na wysokich ustawieniach.",
    "shelf.desc.4k-high": "4K przy wysokim odświeżaniu, bez kompromisów przy karcie graficznej.",
    "shelf.desc.workstation": "Stacja robocza: rdzenie, pamięć i szybki dysk.",
    "shelf.desc.ai-workstation": "Do modeli lokalnych: priorytet dla VRAM i pamięci operacyjnej.",
    "shelf.desc.ultimate": "Maksimum, które ma sens: topowy zestaw bez kompromisów.",
    "shelf.desc.amd-only": "W pełni AMD: Ryzen i Radeon w jednym zestawie.",
    "shelf.desc.intel-nvidia": "Intel Core i GeForce razem, do gier i do pracy.",
    "cfg.monitor.q": "🖥 Chcesz monitor do tego komputera?",
    "cfg.monitor.hint": "Pokazuję tylko te, które obsłużą wybraną rozdzielczość.",
    "cfg.monitor.skip": "➡️ Bez monitora",
    "cfg.monitor.continue": "✅ Kontynuuj z tym monitorem",
    "cfg.peripherals.q": "🖱 Co dołożyć na biurko?",
    "cfg.peripherals.hint": (
        "Możesz wybrać kilka. Zaznaczono: <b>{count}</b>. Model dobiorę do stylu Twojego zestawu."
    ),
    "cfg.peripherals.none": "W tej kategorii nie mam jeszcze nic do zaproponowania.",
    "setup.title": "Twoje stanowisko",
    "setup.total": "Peryferia:",
    "setup.grand_total": "Cały zestaw:",
    "build.lighting.featured": "Podświetlenie RGB: {parts}",
    "build.lighting.available": "Podświetlenie jest: {parts}",
    "build.lighting.addressable": "adresowalne ARGB",
    "build.lighting.unavailable": (
        "W tym zestawie nie ma podświetlenia: wybrana obudowa, chłodzenie i pamięć go nie mają"
    ),
    "build.lighting.hint_swap": "Napisz, a dobiorę podzespoły z RGB.",
    "acc.spec.lighting": "Podświetlenie",
    "acc.spec.rgb": "RGB",
    "cfg.peripherals.clear": "❌ Usuń z zestawu",
    "cfg.peripherals.back": "⬅️ Do kategorii",
    "cfg.peripherals.pick": "Wybierz numer - na zdjęciu widać model i cenę.",
    "summary.setup": "Twoje stanowisko",
    "summary.variants": "Warianty zestawu",
    "bot.description": (
        "AmigoZT PC — składam komputer pod Twój budżet, gry i pracę. Sprawdzam kompatybilność "
        "podzespołów, podaję uczciwą cenę i pokazuję, jak zestaw będzie wyglądał. Cztery języki, "
        "odpowiedź w minutę."
    ),
    "bot.short_description": (
        "Komputer pod Twój budżet: sprawdzona kompatybilność, uczciwa cena, wizualizacja zestawu."
    ),
    "acc.kind.monitor": "Monitor",
    "acc.kind.mouse": "Mysz",
    "acc.kind.keyboard": "Klawiatura",
    "acc.kind.headset": "Słuchawki",
    "acc.kind.microphone": "Mikrofon",
    "acc.kind.webcam": "Kamera",
    "acc.kind.speakers": "Głośniki",
    "acc.kind.mousepad": "Podkładka",
    "acc.kind.chair": "Fotel",
    "acc.kind.desk": "Biurko",
    "acc.kind.lighting": "Podświetlenie",
    "acc.trait.wired": "przewodowa",
    "acc.trait.wireless": "bezprzewodowa",
    "acc.trait.rgb": "z podświetleniem",
}
