<p align="center">
  <img src="src/zmp/icon.png" width="180" alt="ZMP icon"/>
</p>

<h1 align="center">ZMP — Zapret Marketplace Patcher</h1>

<p align="center">
  Нативный десктопный клиент для установки модов из <a href="https://goshkow.com/marketplace">Zapret Marketplace</a> в <b>zapret-discord-youtube</b> / <b>zapret2</b>.
</p>

---

## Возможности

- **Каталог модов** — просмотр, поиск и установка модов из Marketplace одним кликом
- **Управление** — список установленных модов с информацией о версии, авторе и совместимости
- **Установка по slug** — ручная установка мода по короткому имени
- **Безопасное удаление** — чистое удаление модов (файлы, bat-скрипты, списки)
- **Автоподстановка папки** — путь к zapret сохраняется между сессиями
- **Анимации** — плавные переходы, fade-in, toast-уведомления
- **Тёмная тема** — Fluent Design стилистика с JetBrains Mono шрифтом

## Установка

### Windows (portable)

Скачайте актуальный релиз из [Releases](https://github.com/peachoff/Zapret-Marketplace-Patcher/releases) — файл `.exe` не требует установки.

### Linux (AppImage)

Скачайте `.AppImage` из [Releases](https://github.com/peachoff/Zapret-Marketplace-Patcher/releases):

```bash
chmod +x ZMP-*.AppImage
./ZMP-*.AppImage
```

### Из исходников

```bash
git clone https://github.com/peachoff/Zapret-Marketplace-Patcher.git
cd Zapret-Marketplace-Patcher
poetry install
poetry run python main.py
```

Требуется **Python 3.10+** и **Poetry**.

## Сборка

### Windows (portable .exe)

```bash
poetry install
poetry run pyinstaller build/win.spec --noconfirm
```

Результат: `dist/ZMP.exe`

### Linux (AppImage)

```bash
poetry install
poetry run pyinstaller build/linux.spec --noconfirm
cd build && ./build_appimage.sh
```

Результат: `dist/ZMP-*.AppImage`

## Структура проекта

```
src/zmp/
├── app.py            # CustomTkinter GUI
├── api_client.py     # Клиент Zapret Marketplace API
├── installer.py      # Установка / удаление модов
├── icon.ico          # Иконка приложения (Windows)
├── icon.png          # Иконка приложения
└── fonts/            # Используемые шрифты
```

## Контакты

По проблемам и вопросам: **[@likeslp](https://t.me/likeslp)**

## Лицензия

MIT
