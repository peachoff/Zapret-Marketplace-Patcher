<p align="center">
  <img src="src/zmp/icon.png" width="180" alt="ZMP icon"/>
</p>

<h1 align="center">ZMP — Zapret Modifications Patcher</h1>

<p align="center">
  Нативный десктопный клиент для установки модов из пользовательских репозиториев на <b>zapret-discord-youtube</b> и <b>zapret2</b>.
</p>

---

## Возможности

- **Каталог модов** — просмотр, поиск и установка модов из репозиториев github одним кликом.
- **Управление** — список установленных модов с информацией о версии, авторе и совместимости.
- **Автоподстановка папки** — путь к zapret сохраняется между сессиями.

## Установка

### Windows (portable)

Скачайте актуальный релиз из [Releases](https://github.com/peachoff/Zapret-Modifications-Patcher/releases) — файл `.exe` не требует установки.

### Linux (AppImage)

Скачайте `.AppImage` из [Releases](https://github.com/peachoff/Zapret-Modifications-Patcher/releases):

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

## Контакты

По проблемам и вопросам: **[@likeslp](https://t.me/likeslp)**

## Лицензия

MIT
