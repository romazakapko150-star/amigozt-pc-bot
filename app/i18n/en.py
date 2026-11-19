"""English locale."""

TEXTS: dict[str, str] = {
    # --- generic ---
    "start.title": "<b>AMIGOZT PC</b>",
    "start.tagline": (
        "Build a PC that fits your budget, your games and your work.\n"
        "I pick compatible parts and explain why they are the right choice."
    ),
    "menu.prompt": "Pick where we start:",
    "menu.build": "🖥 Build a PC",
    "menu.budget": "💰 PC by budget",
    "menu.games": "🎮 Gaming PC",
    "menu.presets": "⚡ Ready builds",
    "menu.compare": "🔄 Compare parts",
    "menu.mybuilds": "💾 My builds",
    "menu.about": "ℹ️ About",
    "menu.help": "❓ Help",
    "menu.language": "🌐 Language",
    "nav.back": "⬅️ Back",
    "nav.cancel": "❌ Cancel",
    "nav.restart": "🔄 Start over",
    "nav.menu": "🏠 Main menu",
    "nav.skip": "⏭ Skip",
    "nav.done": "✅ Done",
    "nav.yes": "Yes",
    "nav.no": "No",
    "nav.auto": "🤖 Choose for me",
    "nav.custom": "✏️ Custom value",
    "common.error": "Something went wrong. Please try again.",
    "common.rate_limited": "Too many requests. Give it a couple of seconds 🙂",
    "common.cancelled": "Configurator stopped. Back to the main menu.",
    "common.coming_soon": "This section is coming soon. For now try “🖥 Build a PC”.",
    "common.progress": "Step {current} of {total}",
    "common.unknown_action": "I did not recognise that action. Open the menu with /start.",
    "about.text": (
        "<b>AmigoZT PC</b> — an AI service for choosing PCs.\n\n"
        "You answer simple questions, and I:\n"
        "• pick parts for your budget and workload;\n"
        "• verify that every component is compatible;\n"
        "• optimise the build for price/performance;\n"
        "• calculate the total price in PLN and the estimated FPS.\n\n"
        "Market: Poland 🇵🇱 · Currency: PLN"
    ),
    "help.text": (
        "<b>Commands</b>\n"
        "/start — main menu\n"
        "/build — build a PC\n"
        "/budget — pick by budget\n"
        "/mybuilds — my builds\n"
        "/language — change language\n"
        "/help — this help\n\n"
        "“⬅️ Back” and “❌ Cancel” are available at every configurator step."
    ),
    "lang.prompt": "Choose the interface language:",
    "lang.changed": "Language switched to English 🇬🇧",
    # --- configurator ---
    "cfg.budget.q": "💰 What is your budget for the PC?",
    "cfg.budget.hint": (
        "This is the budget for the tower. Monitor and peripherals are counted separately."
    ),
    "cfg.budget.custom_prompt": (
        "Send your budget in PLN as a number.\nFor example: <code>5500</code>"
    ),
    "cfg.budget.invalid": (
        "I could not read that amount. Send a number in PLN between {min} and {max}.\n"
        "For example: <code>5500</code>"
    ),
    "cfg.purpose.q": "🎯 What do you need the PC for?",
    "purpose.gaming": "🎮 Gaming",
    "purpose.gaming_streaming": "🎥 Gaming + streaming",
    "purpose.work": "💻 Work",
    "purpose.design": "🎨 Design / video",
    "purpose.ai_ml": "🤖 AI / ML",
    "purpose.workstation": "💼 Workstation",
    "purpose.universal": "🔥 All-round",
    "cfg.games.q": "🎮 What do you play?",
    "cfg.games.hint": "You can pick several. Selected: <b>{count}</b>",
    "cfg.games.other": "✏️ Another game",
    "cfg.games.custom_prompt": "Send the game title in a single message.",
    "cfg.games.invalid": "The title is empty or too long. Please try again.",
    "cfg.games.limit": "You cannot select more than {max} games at once.",
    "cfg.resolution.q": "🖥 What resolution will you play or work at?",
    "resolution.1080p": "1080p (Full HD)",
    "resolution.1440p": "1440p (2K)",
    "resolution.4k": "4K (Ultra HD)",
    "cfg.fps.q": "⚡ What frame rate are you aiming for?",
    "cfg.priority.q": "🧭 What matters to you in this PC?",
    "cfg.priority.hint": (
        "Pick as many as you like - up to <b>{max}</b>. Selected: <b>{count}</b>. Then press Done."
    ),
    "cfg.priority.limit": "You cannot select more than {max} priorities at once.",
    "cfg.priority.pick_one": "Tick at least one priority.",
    "priority.max_fps": "⚡ Maximum FPS",
    "priority.price_performance": "💰 Price / performance",
    "priority.silence": "🤫 Quiet operation",
    "priority.cooling": "❄️ Cooling",
    "priority.looks": "🎨 Looks",
    "priority.versatility": "🧠 Versatility",
    "priority.efficiency": "🔌 Low power consumption",
    "priority.compact": "📦 Compact size",
    "priority.upgradeability": "🔧 Room to upgrade",
    "cfg.aesthetics.q": "🎨 How should the PC look?",
    "aesthetics.black": "⚫ Black",
    "aesthetics.white": "⚪ White",
    "aesthetics.black_rgb": "⚫ Black + RGB",
    "aesthetics.white_rgb": "⚪ White + RGB",
    "aesthetics.minimal": "◻️ Minimal",
    "aesthetics.gaming": "🔥 Gaming style",
    "cfg.connectivity.q": "📶 Do you need Wi-Fi and Bluetooth?",
    "connectivity.wifi_bt": "📶 Wi-Fi + Bluetooth",
    "connectivity.wifi": "📶 Wi-Fi only",
    "connectivity.bt": "🔵 Bluetooth only",
    "connectivity.none": "🔌 Not needed (cable)",
    "cfg.storage.q": "💾 How much storage do you need for games and files?",
    "cfg.ram.q": "🧠 How much RAM do you need?",
    "cfg.ram.hint": "Not sure? Let me decide.",
    "cfg.cpu.q": "🧩 Any CPU preference?",
    "cfg.gpu.q": "🖼 Any GPU preference?",
    "brand.any": "🤝 No preference",
    # --- summary ---
    "summary.title": "<b>Your requirements</b>",
    "summary.budget": "Budget",
    "summary.purpose": "Purpose",
    "summary.games": "Games",
    "summary.resolution": "Resolution",
    "summary.fps": "Target FPS",
    "summary.priority": "Priority",
    "summary.aesthetics": "Looks",
    "summary.connectivity": "Connectivity",
    "summary.storage": "Storage",
    "summary.ram": "Memory",
    "summary.cpu": "CPU",
    "summary.gpu": "GPU",
    "summary.auto": "my choice",
    "summary.none": "not set",
    "summary.next": (
        "Requirements saved ✅\n\n"
        "Next step — picking compatible components and calculating the price."
    ),
    "summary.btn_generate": "🚀 Generate the build",
    "summary.generate_pending": (
        "⚙️ Component selection is being prepared.\n\n"
        "The parts database and the compatibility engine are wired up in the next stage — "
        "your requirements are already saved and will be used automatically."
    ),
    # --- order ---
    "order.button": "🛒 I want to order",
    "order.created": (
        "Request <b>#{lead_id}</b> created ✅\n\n"
        "I passed it to the AmigoZT PC team — we will reach out on Telegram shortly."
    ),
    "order.exists": "Request <b>#{lead_id}</b> already exists. We are on it 👌",
    "order.expired": "These requirements are stale. Please configure again — it takes a minute.",
    "summary.ready": "✅ <b>Requirements ready</b>",
    "summary.hint_next": "All correct? Then send your request.",
    "order.confirm_q": "Send a request for this configuration?",
    "order.confirm_yes": "✅ Yes, send it",
    "order.edit": "✏️ Edit",
    "order.cancelled": "Request not sent.",
    "summary.btn_save": "💾 Save",
    # --- build card ---
    "build.ready": "🎉 <b>Your build is ready</b>",
    "build.tier.budget": "💰 BUDGET",
    "build.tier.optimal": "⚖️ OPTIMAL",
    "build.tier.performance": "🔥 PERFORMANCE",
    "build.total": "Total",
    "build.approx": "Price is approximate — we confirm it when you order.",
    "build.legacy_note": "⚠️ Platform with no CPU upgrade path left.",
    "build.fps_unavailable": "Not enough benchmark data for a reliable FPS estimate.",
    "build.warnings": "Worth knowing",
    "build.none": (
        "No compatible PC can be built for this budget.\n"
        "\n"
        "A configuration like this starts at about <b>{minimum}</b>."
    ),
    "build.none_generic": "Could not assemble a configuration. Try changing the parameters.",
    "build.btn_other": "🔄 Another option",
    "part.cpu": "🧠 CPU",
    "part.gpu": "🎮 GPU",
    "part.motherboard": "🧩 Motherboard",
    "part.ram": "🧠 Memory",
    "part.ssd": "💾 Storage",
    "part.psu": "🔌 Power supply",
    "part.case": "📦 Case",
    "part.cooler": "❄️ Cooling",
    # --- compatibility notes ---
    "compat.memory_speed": "Memory will run at the speed the platform supports.",
    "compat.psu_tight": "The power supply leaves little headroom for an upgrade.",
    "compat.ssd_pcie_generation": "The SSD will run at the motherboard bus speed.",
    "compat.bios_update": (
        "The motherboard may need a BIOS update for this CPU — we do it during assembly."
    ),
    "compat.gpu_power_adapter": (
        "The graphics card connects through the power adapter from its box."
    ),
    "compat.front_usb_c": (
        "The case's front USB-C will not connect to this board without an adapter."
    ),
    "compat.memory_four_modules": (
        "Four memory modules may run below the rated speed — two modules are more stable."
    ),
    "compat.memory_profile": "The memory profile (EXPO/XMP) may need manual settings.",
    "compat.monitor_output": (
        "Check the cable and port for the monitor's mode — not every output carries it."
    ),
    "order.blocked": "⚠️ <b>The build needs a small change</b>",
    "order.blocked_hint": (
        "The pre-order check found an incompatibility. Nothing was sent — let's pick again."
    ),
    "order.btn_regenerate": "🔄 Pick again",
    "compat.block.gpu_too_long": "The selected graphics card is too long for this case.",
    "compat.block.gpu_front_radiator": (
        "The graphics card and a front-mounted radiator do not fit together in this case."
    ),
    "compat.block.gpu_slots": "The graphics card is too thick for this case.",
    "compat.block.board_form_factor": "The motherboard format does not fit this case.",
    "compat.block.cooler_too_tall": "The CPU cooler is too tall for this case.",
    "compat.block.radiator_unsupported": (
        "This case has no mount for the selected liquid cooler's radiator."
    ),
    "compat.block.psu_too_long": "The power supply is too long for this case.",
    "compat.block.psu_form_factor": "The power supply format does not fit this case.",
    "compat.block.psu_underpowered": (
        "The power supply is not strong enough for this configuration."
    ),
    "compat.block.psu_gpu_minimum": (
        "The power supply is below the minimum the GPU vendor requires."
    ),
    "compat.block.gpu_power_connector": (
        "The power supply lacks the connectors this graphics card needs."
    ),
    "compat.block.socket_mismatch": "The CPU and the motherboard use different sockets.",
    "compat.block.memory_type_mismatch": "The memory type does not match the motherboard.",
    "compat.block.argb_header": "The lighting has no matching header on the motherboard.",
    "compat.block.missing_part": "A required component is missing from the build.",
    "compat.block.generic": "One combination of parts is not confirmed as compatible.",
    # --- ready builds ---
    "ready.title": "⚡ <b>Ready-made builds</b>",
    "ready.pick_filter": "Pick what to show:",
    "ready.all": "📋 All builds",
    "ready.by_budget": "💰 By budget",
    "ready.empty": "Nothing in this category yet.",
    "ready.count": "Found: <b>{count}</b>",
    "ready.page": "Page {page} of {total}",
    "ready.open_hint": "Open a build with a button below.",
    "ready.prev": "⬅️",
    "ready.next": "➡️",
    "ready.cat.budget": "💰 Budget",
    "ready.cat.gaming": "🎮 Gaming",
    "ready.cat.high_fps": "⚡ High FPS",
    "ready.cat.performance": "🔥 Performance",
    "ready.cat.high_end": "👑 High-End",
    "ready.cat.extreme": "💎 Extreme",
    "ready.cat.streaming": "🎥 Streaming",
    "ready.cat.design": "🎨 Design",
    "ready.cat.ai": "🤖 AI / ML",
    "ready.cat.workstation": "💼 Workstation",
    "ready.cat.white": "🤍 White",
    "ready.cat.rgb": "🌈 RGB",
    "ready.cat.quiet": "🤫 Quiet",
    "ready.budget.under": "under {value}",
    "ready.budget.over": "from {value}",
    "ready.stale": "That build is unavailable right now. Pick another one.",
    # --- compare ---
    "cmp.title": "🔄 <b>Compare parts</b>",
    "cmp.pick_category": "What are we comparing?",
    "cmp.pick_first": "Pick the first part:",
    "cmp.pick_second": "Now pick the second one:",
    "cmp.reset": "🔄 Compare others",
    "cmp.same": "That is the same part. Pick a different one.",
    "cmp.price_note": "Prices are approximate.",
    "cmp.spec.cores": "Cores",
    "cmp.spec.threads": "Threads",
    "cmp.spec.socket": "Socket",
    "cmp.spec.tdp": "Power draw",
    "cmp.spec.memory_support": "Memory",
    "cmp.spec.gaming_index": "Gaming index",
    "cmp.spec.perf_index": "Performance index",
    "cmp.spec.vram": "VRAM",
    "cmp.spec.length": "Length",
    "cmp.spec.psu_rec": "Recommended PSU",
    "cmp.spec.ray_tracing": "Ray tracing",
    "cmp.spec.upscaling": "Upscaling",
    "cmp.spec.memory_type": "Type",
    "cmp.spec.capacity": "Capacity",
    "cmp.spec.speed": "Speed",
    "cmp.spec.latency": "Latency",
    "cmp.spec.read": "Read",
    "cmp.spec.write": "Write",
    "cmp.spec.pcie": "PCIe",
    "cmp.spec.price": "Price",
    "cmp.index_note": "Indexes are AmigoZT's own rating, not a benchmark result.",
    # --- accessories ---
    "menu.accessories": "🖱 Accessories",
    "acc.title": "🖱 <b>Accessories</b>",
    "acc.pick_category": "What are we picking?",
    "acc.empty": "Nothing in this category yet.",
    "acc.from": "from {price}",
    "acc.count": "Found: <b>{count}</b>",
    "acc.open_hint": "Open a product with a button below.",
    "acc.price_note": "Price is approximate — confirmed when you order.",
    "part.monitor": "🖥 Monitor",
    "part.mouse": "🖱 Mouse",
    "part.keyboard": "⌨️ Keyboard",
    "part.headset": "🎧 Headset",
    "part.microphone": "🎙 Microphone",
    "part.webcam": "📷 Webcam",
    "part.speakers": "🔊 Speakers",
    "part.mousepad": "🟦 Mousepad",
    "part.chair": "🪑 Chair",
    "part.desk": "🗄 Desk",
    "acc.spec.size": "Size",
    "acc.spec.resolution": "Resolution",
    "acc.spec.refresh": "Refresh rate",
    "acc.spec.panel": "Panel",
    "acc.spec.response": "Response",
    "acc.spec.sync": "Adaptive Sync",
    "acc.spec.wireless": "Wireless",
    "acc.spec.colour": "Colour",
    "acc.yes": "yes",
    "acc.no": "no",
    # --- visualisation ---
    "visual.show": "🔥 Show my PC",
    "visual.look": "🖼️ See what it looks like",
    "visual.recolour": "🎨 Another colour",
    "visual.pick": "🎨 Pick the lighting colour and style:",
    "visual.style_gaming": "✨ Gaming",
    "visual.style_minimal": "◻️ Minimal",
    "visual.caption": (
        "AmigoZT PC visualisation — roughly how your build will look. Not a product photo."
    ),
    "visual.stale": "Build not found. Please configure it again.",
    "visual.product_caption": (
        "AI visualization of the product from catalogue data — not a photograph, details may "
        "differ."
    ),
    "visual.generating": "🎨 Creating your PC visualization… this usually takes up to a minute.",
    "visual.unavailable": (
        "Visualization is temporarily unavailable. The build, price and ordering work as usual."
    ),
    "visual.ai_title": "🖼️ AI visualization of your build",
    "visual.btn_change": "🔄 Change the build",
    "visual.btn_back": "⬅️ Back",
    "visual.caption_ai": (
        "AmigoZT PC AI visualisation from the chosen parts. "
        "A generated image, not a photo of the actual unit — details may differ."
    ),
    # --- pricing lines ---
    "build.components_line": "Components",
    "build.assembly_line": "Assembly & setup · {tier}",
    "build.assembly_hint": (
        "Assembly covers part selection and compatibility checks, the build, "
        "cable management, BIOS/EXPO, drivers and a stress test."
    ),
    "build.verified_note": "Component prices verified against Polish retailers.",
    # --- my builds ---
    "mybuilds.empty": "You have no saved builds yet. Start with “🖥 Build a PC”.",
    "mybuilds.title": "<b>My builds</b>",
    "mybuilds.item": "{index}. {purpose} · {budget} PLN · {date}",
    "accent.red": "Red",
    "accent.blue": "Blue",
    "accent.purple": "Purple",
    "accent.pink": "Pink",
    "accent.green": "Green",
    "accent.orange": "Orange",
    "accent.yellow": "Yellow",
    "accent.cyan": "Cyan",
    "accent.white": "White",
    "accent.silver": "Silver",
    "accent.gold": "Gold",
    "accent.rainbow": "Rainbow",
    "finish.black": "Black",
    "finish.white": "White",
    "visual.image_footer": "AmigoZT PC visualisation · not a product photo · indicative price",
    "shelf.desc.starter": "A quiet computer for study, work and undemanding games.",
    "shelf.desc.budget-gamer": "A first gaming PC: comfortable 1080p in popular titles.",
    "shelf.desc.1080p-king": "Confident 144 FPS at 1080p, with a couple of years to spare.",
    "shelf.desc.cs2-300": "Built for competitive CS2: the CPU and the frame rate come first.",
    "shelf.desc.cs2-500": "Maximum frames in esports titles at 1080p.",
    "shelf.desc.fps-beast": "For 360 Hz monitors and above: everything goes into frames.",
    "shelf.desc.1440p-sweet-spot": "The best price-to-frames ratio at 1440p.",
    "shelf.desc.1440p-high-fps": "240 Hz at 1440p, for those who have outgrown 144.",
    "shelf.desc.white-dream": "An all-white build: case, cooling and lighting in one style.",
    "shelf.desc.black-rgb": "A black case with lighting - the classic gaming desk.",
    "shelf.desc.silent-gaming": "A gaming PC you can barely hear: cooling with real headroom.",
    "shelf.desc.streamer": "Playing and streaming at once: many cores and plenty of memory.",
    "shelf.desc.creator": "Editing, graphics and rendering: memory, storage and VRAM.",
    "shelf.desc.4k-beast": "Comfortable 4K gaming at high settings.",
    "shelf.desc.4k-high": "High-refresh 4K, with no compromise on the graphics card.",
    "shelf.desc.workstation": "A workstation: cores, memory and fast storage.",
    "shelf.desc.ai-workstation": "For local models: VRAM and system memory come first.",
    "shelf.desc.ultimate": "As far as it makes sense to go: the top pairing, no compromises.",
    "shelf.desc.amd-only": "All AMD: Ryzen and Radeon in one machine.",
    "shelf.desc.intel-nvidia": "Intel Core and GeForce together, for games and work.",
    "cfg.monitor.q": "🖥 Do you want a monitor with this PC?",
    "cfg.monitor.hint": "Only screens that can show the resolution you picked are listed.",
    "cfg.monitor.skip": "➡️ No monitor",
    "cfg.monitor.continue": "✅ Continue with this monitor",
    "cfg.peripherals.q": "🖱 What should we add to the desk?",
    "cfg.peripherals.hint": (
        "Pick as many as you like. Selected: <b>{count}</b>. "
        "The model is matched to your build's style."
    ),
    "cfg.peripherals.none": "Nothing to offer in that category yet.",
    "setup.title": "Your desk",
    "setup.total": "Peripherals:",
    "setup.grand_total": "Complete setup:",
    "build.lighting.featured": "RGB lighting: {parts}",
    "build.lighting.available": "Lighting on board: {parts}",
    "build.lighting.addressable": "addressable ARGB",
    "build.lighting.unavailable": (
        "No lighting in this build: the chosen case, cooler and memory have none"
    ),
    "build.lighting.hint_swap": "Say the word and I will pick parts with RGB instead.",
    "acc.spec.lighting": "Lighting",
    "acc.spec.rgb": "RGB",
    "cfg.peripherals.clear": "❌ Remove from the build",
    "cfg.peripherals.back": "⬅️ Back to categories",
    "cfg.peripherals.pick": "Pick a number - the photo shows what you get and what it costs.",
    "summary.setup": "Your desk",
    "summary.variants": "Build options",
    "bot.description": (
        "AmigoZT PC — I build a computer around your budget, games and work. I check every part "
        "fits, quote an honest price and show you what the machine will look like. Four languages, "
        "an answer in a minute."
    ),
    "bot.short_description": (
        "PC builds for your budget: checked compatibility, honest pricing, a picture of the "
        "machine."
    ),
    "acc.kind.monitor": "Monitor",
    "acc.kind.mouse": "Mouse",
    "acc.kind.keyboard": "Keyboard",
    "acc.kind.headset": "Headset",
    "acc.kind.microphone": "Microphone",
    "acc.kind.webcam": "Webcam",
    "acc.kind.speakers": "Speakers",
    "acc.kind.mousepad": "Mouse pad",
    "acc.kind.chair": "Chair",
    "acc.kind.desk": "Desk",
    "acc.kind.lighting": "Lighting",
    "acc.trait.wired": "wired",
    "acc.trait.wireless": "wireless",
    "acc.trait.rgb": "with lighting",
}
