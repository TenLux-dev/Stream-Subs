# Stream Subs 🎙️

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)]()
[![CUDA](https://img.shields.io/badge/CUDA-Supported-green.svg)](https://developer.nvidia.com/cuda-zone)

**Локальные субтитры RU→EN для стримов на Whisper + CUDA**

[🇬🇧 English version](README.en.md)

**Stream Subs** — это локальное приложение для стримеров, которое в реальном времени переводит русскую речь в английские субтитры и выводит их поверх стрима в OBS или Streamlabs.

**Всё работает на вашем компьютере**, без облачных сервисов, ежемесячных платежей и лимитов.

Проект студии [TenLux](https://tenlux.tech).

---

## ✨ Возможности

- 🎤 **Речь с микрофона → английские субтитры** в реальном времени
- ⚡ **GPU-ускорение** через CUDA (задержка 0.3–0.7 секунды)
- 🎨 **Веб-интерфейс настроек** с поддержкой Google Fonts
- 🚫 **Фильтр галлюцинаций и запрещённых слов** (для безопасности эфира)
- 📝 **Логирование** всех распознаваний (для аудита)
- 🌍 **Двуязычный интерфейс** (RU + EN)
- 📦 **Установщик одним кликом** — не нужен Python у пользователя
- 💾 **Редактируемые списки** запрещённых слов и мемов

---

## 📊 Что внутри

```
Микрофон → VAD → Whisper (ru→en) → WebSocket → Браузер → OBS/Streamlabs
```

- **VAD** (Voice Activity Detection) — Silero VAD для нарезки фраз
- **Whisper** — модель `medium` через `faster-whisper` (CTranslate2 + CUDA)
- **Веб-сервер** — FastAPI + WebSocket для передачи субтитров
- **Внешний вид** — HTML + CSS + JS, поддерживает Google Fonts
- **Установщик** — Inno Setup с bootstrap-загрузкой зависимостей

---

## 📸 Скриншоты

| ![Установщик](assets/installer.png) | ![Bootstrap](assets/bootstrap.png) |
| :---: | :---: |
| Установщик Inno Setup | Загрузка компонентов (bootstrap) |

| ![Субтитры в игре](assets/subtitles.png) | ![Настройки](assets/settings.png) |
| :---: | :---: |
| Субтитры в OBS / Streamlabs | Веб-интерфейс настроек |

---

## 📥 Установка

### Готовый установщик (рекомендуется)

1. Скачайте **StreamSubsSetup.exe** со страницы [Releases](https://github.com/TenLux-dev/Stream-Subs/releases/latest).
2. Запустите установщик.
3. Следуйте инструкциям. Установка занимает 1–2 минуты.
4. **При первом запуске** программа скачает ~4 ГБ компонентов:
   - Python-пакеты (torch, faster-whisper, silero-vad) — ~2.5 ГБ
   - Модель Whisper `medium` — ~1.5 ГБ
   - Модель Silero VAD — ~2 МБ
5. Дождитесь сообщения **«ВСЁ ГОТОВО!»** — это займёт 10–30 минут.
6. Откройте `http://127.0.0.1:8000` в браузере или добавьте как **Browser Source** в OBS/Streamlabs.

### Требования

- Windows 10 / 11 (x64)
- NVIDIA GPU с поддержкой CUDA (рекомендуется GTX 1060+ / RTX 2060+)
- 6 ГБ свободного места на диске
- Интернет для первого запуска

### Сборка из исходников

Откройте терминал и выполните:

- `git clone https://github.com/TenLux-dev/Stream-Subs.git`
- `cd Stream-Subs`
- `py -3.11 -m venv .venv`
- `.venv\Scripts\activate`
- `pip install -r requirements.txt`
- `python main.py`

**Требования для сборки:** Python 3.11+, PyInstaller, Inno Setup 6.

---

## 🎮 CPU-версия

Если у вас **нет NVIDIA GPU**, приложение всё равно будет работать — Whisper автоматически переключится на CPU (`Whisper: cpu / int8`).

**Но:** на CPU модель `medium` обрабатывает фразу за **1–3 секунды** вместо 0.3–0.7, что для live-субтитров ощутимо. Плюс растёт задержка между фразами.

### Варианты для CPU

**1. Собрать оптимизированную CPU-сборку самому.**

В команде сборки `bootstrap.py` уберите флаги `--collect-all nvidia` и `--exclude-module nvidia`. Размер установщика упадёт с ~40 МБ до ~25 МБ, а итоговый размер на диске — с 4 ГБ до ~1.5 ГБ.

**2. Использовать меньшую модель.**

В `main.py` замените `MODEL = "medium"` на `MODEL = "small"` или `MODEL = "base"`. Скорость вырастет в 2–4 раза, качество перевода будет ниже.

**3. Попросить автора собрать CPU-версию.**

Если не хотите возиться со сборкой — создайте [Issue](https://github.com/TenLux-dev/Stream-Subs/issues) с заголовком **«Request: CPU build»**. Автор выложит готовый CPU-инсталлятор в Releases, если наберётся достаточное количество запросов.

---

## 🎬 Использование в OBS / Streamlabs

1. Запустите **Stream Subs** (ярлык на рабочем столе или `StreamSubs.exe`).
2. Дождитесь `✅ ВСЁ ГОТОВО!` и строки `Whisper: cuda / float16`.
3. В OBS / Streamlabs добавьте **Browser Source**:
   - **URL:** `http://127.0.0.1:8000`
   - **Width:** `1920`
   - **Height:** `1080`
4. Субтитры появятся поверх стрима с прозрачным фоном.

### Настройки внешнего вида

Откройте `http://127.0.0.1:8000/settings`:

- **Google Font** — название любого шрифта с fonts.google.com (например, `Inter`, `Tektur`, `Roboto`)
- **Размер** — от 16 до 120 px
- **Цвет** — любой hex-цвет
- **Отступ снизу** — где будут субтитры
- **Максимум символов в куске** — как резать длинные фразы
- **Время показа** — сколько держать субтитры на экране

### Редактирование списков слов

Все списки лежат в папке установки:

`C:\Users\<ваше_имя>\AppData\Local\Programs\StreamSubs\lists\`

- `banned_words.txt` — запрещённые слова
- `hallucinations.txt` — типичные галлюцинации Whisper
- `patterns.txt` — регулярные выражения
- `slang.txt` — замены мемов

Откройте любой файл в блокноте, добавьте или удалите строки, сохраните — изменения применятся **автоматически, без перезапуска программы**.

### Логирование

Каждое распознавание пишется в `whisper_log.txt` рядом с exe:

```
[2026-09-26 21:34:11] [OK] len=2.31s whisper=0.42s 'Today we will play a new game.'
[2026-09-26 21:34:18] [FILTERED] len=0.64s whisper=0.18s 'Fuck you'
[2026-09-26 21:34:22] [EMPTY] len=0.91s whisper=0.31s ''
```

Это защищает вас: если платформа спросит, почему в эфире было что-то неподобающее, вы покажете файл — вот что вернул Whisper, вот что фильтр отсёк.

---

## 🛠️ Требования

### Для пользователя

- Windows 10 / 11 (x64)
- NVIDIA GPU (рекомендуется), 6 ГБ свободного места
- Интернет для первого запуска

### Для разработчика

- Python 3.11+
- PyInstaller 6.x
- Inno Setup 6
- CUDA-совместимая видеокарта (для тестирования GPU)

---

## 🐛 Известные ограничения

- **Только русский → английский.** Модель `medium` обучена на общих данных; поддержка других языков требует модификации кода.
- **Мемы и сленг.** Whisper может переводить «я база» как `base 15`. Часть лечится через `slang.txt`, но не всё.
- **Галлюцинации на тишине.** Whisper иногда выдаёт `Thank you`, `Bye`, `Silence` на шум. Фильтр отсекает 99%, но идеала нет.
- **Задержка.** Минимум 0.5 секунды из-за ожидания тишины (VAD) + Whisper. Для настоящих «live» субтитров нужно потоковое распознавание, но это заметно ухудшает качество.

---

## 💖 Поддержать проект

Stream Subs — бесплатный проект с открытым исходным кодом, который делается в свободное время. Если он помогает вашим стримам — можно поддержать разработку:

- 💰 [**DonationAlerts**](https://www.donationalerts.com/r/cjdarklord) — разовый донат
- 🎁 [**ODA Digital**](https://cjdarklord.oda.digital/) — альтернативный вариант
- 💎 [**TON-кошелёк**](https://tonscan.org/address/UQC4_jNOa2xfv75n-95cluaN7P4HJ3Lk00b_p1xvn1tGDKYx) — открыть в tonscan и скопировать адрес
- ❤️ [**GitHub Sponsors**](https://github.com/sponsors/CJDARKLORD) — подписка через GitHub
- ⭐ [**Звезда на GitHub**](https://github.com/TenLux-dev/Stream-Subs) — тоже поддержка

Каждая копейка идёт на развитие проекта: новые функции, тестирование, поддержка пользователей.

---

## 📄 Лицензия

MIT License. См. файл [LICENSE](LICENSE).

Используйте свободно — в личных, коммерческих и любых других целях. Единственное требование — сохранить упоминание авторства.

---

## 🙏 Благодарности

- [OpenAI Whisper](https://github.com/openai/whisper) — модель распознавания речи
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — оптимизированная реализация на CTranslate2
- [Silero VAD](https://github.com/snakers4/silero-vad) — детекция голосовой активности
- [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) — веб-сервер
- [Inno Setup](https://jrsoftware.org/isinfo.php) — создание установщика

---

## 📬 Контакты

- **GitHub Issues:** [создать issue](https://github.com/TenLux-dev/Stream-Subs/issues)
- **Telegram:** [@tenlux_dev](https://t.me/tenlux_dev)
- **Сайт:** [tenlux.tech](https://tenlux.tech)
- **Автор:** CJDARKLORD / TenLux

Если проект помог — поставьте ⭐ звезду, это лучшая поддержка.
