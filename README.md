<p align="center">
  <img src="src/zmp/icon.png" width="180" alt="ZMP icon"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen" alt="license" />
</p>

# ZMP — Zapret Modifications Patcher

Нативный кроссплатформенный десктоп-клиент 🖥️ для удобной установки и управления модами для проектов вроде **[zapret-discord-youtube](https://github.com/flowseal/zapret-discord-youtube)** и **[zapret2](https://github.com/bol-van/zapret2)**. ✨

---

## Ключевые возможности

- 🗂️ Каталог модов из любого GitHub-репозитория: каждый релиз репозитория — это мод (как в [peachoff/Zapret-Mods](https://github.com/peachoff/Zapret-Mods))
- 💾 Сохранение нескольких репозиториев и быстрый переключатель между ними
- 🧩 Управление установленными модами: версия, автор, совместимость
- 📦 Установка модов напрямую из локального ZIP-архива
- 💾 Сохранение пути к папке zapret между сессиями
- 🛠️ Простая сборка и портирование под Windows и Linux

## Использование

1. Запустите ZMP и укажите папку с zapret.
2. Перейдите в **Каталог**, вставьте ссылку на GitHub-репозиторий с модами (например `https://github.com/peachoff/Zapret-Mods`) и нажмите **Загрузить** — моды появятся списком.
3. Нажмите **Установить** у нужного мода — его `.zip` из релиза будет скачан и установлен.
4. Мод из локального файла можно установить на вкладке **Из ZIP**.

## Быстрый старт

1. Перейдите в Releases и скачайте нужный артефакт: https://github.com/peachoff/Zapret-Modifications-Patcher/releases

### Windows (portable)

Запустите скачанный `.exe` — установка не требуется.

### Linux (AppImage)

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

Требуется Python 3.10+ и Poetry.

## Сборка

### Windows (.exe)

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

## Контакты

По вопросам и багрепортам: **[@likeslp](https://t.me/likeslp)**

## Вклад

Пул-реквесты и issue приветствуются. Для локальной разработки используйте виртуальное окружение и Poetry.

## Лицензия

Этот проект распространяется под лицензией [MIT](https://github.com/peachoff/Zapret-Modifications-Patcher/blob/main/LICENSE) — ссылка на файл лицензии в репозитории.

