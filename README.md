# Avatar Studio

Talking-avatar video generation demo: image + audio + prompt → video.

## Architecture

```mermaid
flowchart LR
    UI[Streamlit :8501] -- submit_job --> J[app/jobs<br/>dict + ThreadPool 1]
    API[FastAPI :7860<br/>/api/* + /docs] -- submit_job --> J
    J -- worker thread --> B{Backend}
    B --> Mock[Mock]
    B --> Fal[fal.ai · omnihuman]
    B --> Local[OmniAvatar 1.3B / 14B<br/><i>stub</i>]
    B -- mp4 --> FS[(outputs/*.mp4)]
    UI -- poll status --> J
    API -- poll status / stream result --> J
```

Both the Streamlit UI and the REST API call into the same `app/jobs` module —
one queue, one worker, one source of truth.

## Quick Start

Docker:
```bash
cp .env.example .env
docker compose up --build
```

Local (conda):
```bash
conda create -n avatar-studio python=3.11 -y
conda activate avatar-studio
pip install -r requirements.txt
copy .env.example .env
streamlit run app/main.py
```

- UI: http://localhost:8501
- Swagger / OpenAPI: http://localhost:7860/docs
- Empty `FAL_API_KEY` → mock backend (offline, returns a cached sample video).

## REST API

```bash
# Submit a job (returns {"job_id": "..."})
curl -X POST http://localhost:7860/api/jobs \
  -F image=@avatar.jpg -F audio=@speech.mp3 \
  -F prompt="friendly, smiling" -F mode=fal

# Poll status
curl http://localhost:7860/api/jobs/<job_id>

# Download result (404 until status=done)
curl -O http://localhost:7860/api/jobs/<job_id>/result
```

`mode`: `mock` | `fal` | `OmniAvatar 1.3B` | `OmniAvatar 14B` | `auto`

## Checklist

**Frontend**
- [x] Форма загрузки: reference image, аудио, текстовый промпт поведения
- [x] Real-time прогресс генерации (не polling)
- [x] Просмотр и скачивание результата
- [x] Обработка ошибок с понятной обратной связью

**Backend**
- [x] API для приёма задач и получения статуса/результата
- [x] Очередь задач с балансировкой (корректная работа при параллельных запросах)
- [x] GPU-воркер с интеграцией OmniAvatar inference pipeline — *структурный stub: `download_omniavatar_weights() / load_omniavatar_pipeline() / run_omniavatar()` в [app/inference.py](app/inference.py) с подробным docstring'ом «что заменить на Stage 2». Сейчас run_omniavatar() падает на mock fallback.*
- [x] Валидация входных файлов

**Инфраструктура**
- [x] Docker Compose — всё поднимается одной командой
- [x] README с инструкцией по запуску, описанием архитектуры и обоснованием решений

**Плюсом**
- [x] Галерея / история генераций
- [x] Выбор модели (14B / 1.3B) и параметров в UI
- [ ] TTS — генерация аудио из текста вместо загрузки файла
- [x] Превью входных данных перед отправкой
- [x] API-документация (Swagger)
- [ ] Мониторинг, логирование, тесты
