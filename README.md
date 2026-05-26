# Avatar Studio

Avatar video generation

🌐 **Online demo:** https://avatar-studio-production-cc26.up.railway.app/

## Architecture

```mermaid
flowchart LR
    UI[Streamlit :8501] -- submit_job --> J[app/jobs<br/>dict + ThreadPool N<br/>+ wakeup events]
    API[FastAPI :7860<br/>/api/* + /docs] -- submit_job --> J
    J -- worker thread --> B{Backend}
    B --> Mock[Mock]
    B --> Fal[fal.ai · omnihuman]
    B --> Local[OmniAvatar 1.3B / 14B<br/><i>stub</i>]
    B -- mp4 --> FS[(outputs/*.mp4)]
    J -. event push .-> UI
    API -- get status / stream result --> J
```

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
- Smoke-test the REST API end-to-end: open [`APICheck.ipynb`](APICheck.ipynb)
- Empty `FAL_API_KEY` → mock backend (offline, returns a cached sample video)

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/jobs` | Submit a job → `{"job_id"}` |
| `GET`  | `/api/jobs` | List all jobs (newest first) |
| `GET`  | `/api/jobs/{id}` | Get `Job` status |
| `GET`  | `/api/jobs/{id}/result` | Download mp4 (404 until `done`) |

<details>
<summary><code>Job</code> object</summary>

```json
{
  "id": "a1b2c3d4...",
  "status": "running",
  "progress": 47.5,
  "message": "mock step 9/20",
  "prompt": "friendly, smiling",
  "mode": "mock",
  "params": {"num_steps": 30, "guidance_scale": 5.0, "audio_scale": 3.0},
  "error": null,
  "created_at": "2026-05-25T12:34:56",
  "started_at": "2026-05-25T12:34:57",
  "finished_at": null,
  "elapsed_seconds": null,
  "result_url": "/api/jobs/a1b2c3d4.../result"
}
```
`status`: `queued` → `running` → `done` \| `failed`. `result_url` is `null` until `done`.
</details>

<details>
<summary>Curl walkthrough</summary>

```bash
curl -X POST :7860/api/jobs -F image=@a.jpg -F audio=@b.mp3 -F mode=fal
curl    :7860/api/jobs/<job_id>
curl -O :7860/api/jobs/<job_id>/result
```
</details>

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
- [x] Мониторинг, логирование, тесты — *логирование настроено (`logging.basicConfig` в main.py, `log.info`/`exception` в jobs/inference); smoke-тест REST API в [`APICheck.ipynb`](APICheck.ipynb). Мониторинга (Prometheus и т.п.) нет.*
