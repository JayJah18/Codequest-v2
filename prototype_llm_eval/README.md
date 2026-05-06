# prototype_llm_eval

Dissertation-focused LLM evaluation prototype for:
1. fixed task generation benchmark preparation,
2. multi-model marking comparison,
3. smaller qualitative feedback comparison.

The design is intentionally file-based and reproducible, with human marks as ground truth.

## Two modes: why both exist

| Mode | Purpose | Where it shows up |
|------|---------|-------------------|
| **Dynamic (live) generation** | Prove **on-demand task JSON generation** works for demos and vivas (default provider `gemini`; override with **`QUESTION_GENERATION_PROVIDER`**). | `POST /api/demo/generate-live-task`, `POST /generate-task` when `USE_FIXED_DATASET=false`, `/demo-ui` (“Generate live task”). Output is **validated** (`backend/live_task_validation.py`) before marking; not written into the frozen benchmark file. |
| **Fixed benchmark** | **Controlled, reproducible** evaluation: same 20 tasks, same variants, same human marks CSVs. | `data/fixed_tasks_with_answers.json`, `run_sample_eval`, `compare_results`, `/eval-ui`, `/research-dashboard`. |

**Why both:** live generation demonstrates **capability**; the frozen set demonstrates **fair comparison** across models and over time. Question **appropriateness** for the *frozen* stems is judged by humans (`question_generation_review.csv`) against learner fit — **not** by matching text to another “gold” question file.

## Gemini API-key mode vs local Ollama (auth clarity)

This prototype’s **`gemini` provider** uses **API-key authentication only**: the `google.generativeai` Python SDK calls Google’s **Generative Language API** (`generativelanguage.googleapis.com`). It does **not** use Vertex AI, OAuth, or service-account JSON.

### A) Gemini API-key mode (default for question gen / marking / feedback when providers are `gemini`)

- Set **`GEMINI_API_KEY`** to a key from **[Google AI Studio](https://aistudio.google.com/apikey)** (or another key valid for the Generative Language API with this SDK).
- Optionally set **`GEMINI_MODEL`** (default `gemini-2.5-flash`).
- **Common confusion:** a Google Cloud Console API key with the wrong **API restrictions** (e.g. not including **Generative Language API**) often returns **`API_KEY_INVALID`** even when the key “looks” valid. That is a **restriction / key-type** issue, not a bug in this repo.
- **Test the same path as the app:** from repo root, run  
  `python prototype_llm_eval/scripts/test_gemini_key.py`  
  or `.\prototype_llm_eval\scripts\test_gemini_key.ps1`  
  The script prints whether the key is present, the model id, and whether a minimal Gemini call succeeds.

PowerShell examples (same shell as uvicorn, optional override):

```powershell
$env:GEMINI_API_KEY="your-key"
$env:GEMINI_MODEL="gemini-2.5-flash"
```

Prefer **`prototype_llm_eval/local.env`** (gitignored) plus `start_demo_server.ps1` / `load_local_env.ps1` so you do not paste keys into every terminal.

### B) Local fallback mode (live **question** generation without Gemini)

- Set **`QUESTION_GENERATION_PROVIDER=llama`** in `local.env` and run **[Ollama](https://ollama.com)** with **`OLLAMA_MODEL`** (and **`OLLAMA_BASE_URL`** if not default).
- **No silent fallback:** if `QUESTION_GENERATION_PROVIDER=gemini`, failures surface as **`503`** (missing key) or **`502`** (rejected key) with an explicit message — the app does not switch to Ollama unless you set the env var.
- **Marking / feedback** use **`MARKING_PROVIDER`** and **`FEEDBACK_PROVIDER`** separately. For a fully local demo, set those to **`llama`** as well; otherwise marking may still call Gemini and hit the same API-key errors.

```env
QUESTION_GENERATION_PROVIDER=llama
MARKING_PROVIDER=llama
FEEDBACK_PROVIDER=llama
```

### Active provider in the UI / API

- **`GET /api/demo/config`** returns **`question_generation_provider`**, **`question_generation_model`**, **`marking_provider`**, **`marking_model`**, **`feedback_provider`**, **`feedback_model`**, and **`gemini_api_key_configured`**.
- **`/demo-ui`** reads that endpoint and shows which providers are in use.

## Why Gemini is the default for generation and eval

**Question (task) authoring** defaults to the **`gemini`** provider (`gemini-2.5-flash` unless **`GEMINI_MODEL`** is set). You can switch live authoring to **`llama`** or **`mistral`** with **`QUESTION_GENERATION_PROVIDER`**. Offline benchmark preparation still typically uses Gemini for structured JSON reliability; the frozen file is human-reviewed.

Answer-variant generation still uses **`ANSWER_VARIANT_PROVIDER`** (default `gemini`). Marking and feedback remain multi-model via **`MARKING_PROVIDER`** / **`FEEDBACK_PROVIDER`** and batch env **`MARKING_MODELS`** / **`FEEDBACK_MODELS`**.

## Why multi-model marking/feedback is used

Marking and feedback are evaluated across `gemini`, `llama`, and `mistral` to compare:
- proprietary vs local/open models,
- robustness against human ground truth,
- model-specific behavior for grading and feedback quality.

## Provider abstraction

`backend/llm_provider.py` provides:
- `LLMProvider.generate_text(prompt, system_prompt=None) -> str`
- `LLMProvider.generate_json(prompt, system_prompt=None) -> dict`
- `get_provider(name)` for `gemini`, `llama`, `mistral`
- `get_configured_model_name(name)` for run metadata

Providers use:
- `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-2.5-flash`)
- `OLLAMA_BASE_URL`, `OLLAMA_MODEL`
- `MISTRAL_API_KEY`, `MISTRAL_MODEL`, `MISTRAL_OLLAMA_MODEL`

## Fixed benchmark constraints

- `data/fixed_tasks.json` / `data/fixed_tasks_with_answers.json` contain exactly 20 tasks.
- Concept split: 5 `variables`, 5 `conditionals`, 5 `loops`, 5 `functions`.
- Each task has exactly 5 unique labeled subtasks:
  - `{"subtask_id": "...", "label": "..."}`
- `model_answer` is required and non-empty in fixed-with-answers.

Validation is enforced by `backend/dataset_validation.py` and used before evaluation runs.

## Student answer variants

`backend/generate_answer_variants.py` creates exactly 3 answers per task:
- `fully_correct`
- `partly_correct` (target 2-3 subtasks correct)
- `fully_incorrect` (target 0-1 subtasks correct)

Output is `data/generated_answers.json` with `answer_id`, `variant_type`, `code`.

## Prompt versioning and fairness

Prompt files include explicit version headers:
- `prompts/task_generation_prompt.txt` (`PROMPT_VERSION:task_generation_v1`)
- `prompts/marking_prompt.txt` (`PROMPT_VERSION:marking_v1`)
- `prompts/feedback_prompt.txt` (`PROMPT_VERSION:feedback_v1`)

Keeping prompt contracts stable is critical for fair model comparison.

## Environment variables

- **`ADMIN_USERNAME`**, **`ADMIN_PASSWORD`**, **`SESSION_SECRET`** — prototype **web login** only (see *Web UI routes*). Not production security.
- `GEMINI_API_KEY`
- **Persisting secrets and model settings (Windows, recommended):** copy `prototype_llm_eval/local.env.example` to `prototype_llm_eval/local.env` and fill in any keys you use (`local.env` is **gitignored**). The example lists **Gemini**, **Mistral API**, and **Ollama** variables (`GEMINI_API_KEY`, `MISTRAL_API_KEY`, `OLLAMA_MODEL`, etc.).
  - **Web server:** `.\prototype_llm_eval\scripts\start_demo_server.ps1` — loads all `KEY=value` lines from `local.env`, then starts uvicorn (optional `.venv` activate).
  - **Batch eval in the same shell:** from repo root, dot-source once:  
    `. .\prototype_llm_eval\scripts\load_local_env.ps1`  
    then run e.g. `python -m prototype_llm_eval.evaluation.run_sample_eval`.  
  Shared loader: `prototype_llm_eval/scripts/Import-LocalEnv.ps1` (used by both scripts above).
- `GEMINI_MODEL` (default `gemini-2.5-flash`) — used for **every** call to the `gemini` provider (question generation, `prepare_fixed_dataset` model answers if you use that path, marking rows where the marker is `gemini`, feedback when `gemini` is in `FEEDBACK_MODELS`, and `/demo-ui` when `MARKING_PROVIDER` / `FEEDBACK_PROVIDER` are `gemini`).

### Trying another Gemini release (e.g. Gemini 3)

1. In [Google AI Studio](https://aistudio.google.com/) or the [Gemini API models doc](https://ai.google.dev/gemini-api/docs/models/gemini), copy the **exact model id** your key can use (preview names and availability change over time).
2. Point the prototype at it for one session, for example PowerShell:  
   `$env:GEMINI_MODEL="YOUR_MODEL_ID_HERE"`
3. **Question generation:** dynamic `/generate-task` or `task_bank` / bank rebuild paths call Gemini with that id. Fixed `fixed_tasks_with_answers.json` is not regenerated unless you run preparation scripts again.
4. **Marking:** `$env:MARKING_MODELS="gemini"` then `python -m prototype_llm_eval.evaluation.run_sample_eval` (use `TASK_LIMIT` or `TASK_IDS` for a cheap test). **`marking_results.csv` is overwritten** — copy it aside if you want to compare Gemini 2.5 vs Gemini 3 side by side.
5. **Feedback:** `$env:FEEDBACK_MODELS="gemini"` then `python -m prototype_llm_eval.evaluation.run_feedback_eval` — same idea; copy `feedback_results.json` / `.csv` if you need both versions.

If the API returns “model not found”, the id is wrong for your project or the model is not enabled for your key yet.

- `OLLAMA_BASE_URL` (default `http://localhost:11434`)
- `OLLAMA_MODEL` (default `llama3.1`)
- `MISTRAL_API_KEY`
- `MISTRAL_MODEL` (default `mistral-small-latest`)
- `MISTRAL_OLLAMA_MODEL` (default `mistral`)
- `ANSWER_VARIANT_PROVIDER` (default `gemini`)
- **`QUESTION_GENERATION_PROVIDER`** (`gemini` | `llama` | `mistral`, default `gemini`) — live/dynamic **question JSON** generation in `task_bank.py` (`POST /api/demo/generate-live-task`, dynamic `POST /generate-task`). Does **not** silently fall back to Ollama.
- `USE_FIXED_DATASET` (`true` / `false`) — when `true`, the server loads the frozen bank at startup and `POST /generate-task` **samples** it; **`POST /api/demo/generate-live-task`** still uses **`QUESTION_GENERATION_PROVIDER`** (independent of this flag).
- `MARKING_PROVIDER`, `FEEDBACK_PROVIDER` (defaults `gemini`) — used by `/mark-answer`, `/generate-feedback`, and `/demo-ui` marking/feedback.
- `MARKING_MODELS` (example `gemini,llama,mistral`)
- `FEEDBACK_MODELS` (example `gemini,llama,mistral`)

### Pilot subset filters

These are supported by marking/feedback scripts and validation helper:
- `TASK_LIMIT`
- `TASK_IDS` (comma-separated task IDs)
- `CONCEPT_FILTER` (comma-separated concepts)

## Web UI routes (public vs admin)

### Prototype login (not production security)

The server adds a **dissertation-only access layer**: env-configured **admin** credentials, **plaintext comparison**, and a **signed session cookie** (`SessionMiddleware`). There is **no** password hashing, user database, OAuth, or account recovery.

- **`ADMIN_USERNAME`** (default `admin`) and **`ADMIN_PASSWORD`** (if unset, insecure default `codequest-demo` — server prints a warning).
- **`SESSION_SECRET`** signs the cookie; set a long random string in `local.env` for demos (avoid the placeholder default if the machine is shared).
- **`POST /api/auth/login`** / **`POST /api/auth/logout`** / **`GET /api/auth/me`**.

Unauthenticated visitors hitting a protected page are **redirected to `/login?next=…`**. Protected **API** calls return **401 JSON**.

### Public routes (no login)

| Route | Purpose |
|-------|---------|
| **`/`** | Landing page — CodeQuest intro; CTAs to demo and login. |
| **`/login`** | Prototype sign-in for admin/research tools. |
| **`/demo-ui`** (+ static under `/demo-ui/static`) | Main **learner-facing** demo: tasks, answer box, marking, feedback. |
| **`/static/...`** | Shared theme/CSS for landing, login, admin hub. |
| **`/api/demo/...`** | Public demo API (generate task sample, mark, feedback). |
| **`/api/auth/...`** | Login/logout/me. |
| **`/docs`**, **`/openapi.json`**, **`/redoc`** | FastAPI docs (left public for local debugging). |

### Admin-only routes (session required)

| Route | Purpose |
|-------|---------|
| **`/admin`** | Control hub linking to eval, research, progression, demo, legacy console. |
| **`/eval-ui`** | Human marking interface → `human_marks.csv`. |
| **`/research-dashboard`** | Metrics + question appropriateness review. |
| **`/progress-ui`** | Progression scope / honesty page. |
| **`/legacy-console`** | Old three-step `/generate-task` · `/mark-answer` · `/generate-feedback` UI (preserved). |

Admin-only **API** prefixes: **`/api/eval/`**, **`/api/research-summary`**, **`/api/research/...`**, and legacy **`POST /generate-task`**, **`/mark-answer`**, **`/generate-feedback`**.

Static assets for gated UIs remain reachable without a session (e.g. **`/eval-ui/static/...`**) so pages load after login; the **HTML entry** and **data APIs** are protected.

**Progression (dissertation wording):** there is **no** learner unlock progression product. `/progress-ui` states that; `/eval-ui` “progress” is **human labelling** completeness only.

Supporting JSON (recap):

- `GET /api/research-summary` — dashboard aggregates (admin).
- `GET` / `POST /api/research/question-review` — question appropriateness CSV (admin).
- `GET` / `POST /api/research/feedback-review` — feedback quality scores CSV (admin; reads `feedback_results.json`).
- `GET /api/demo/config`, demo task/mark/feedback — **public**.
- `GET /api/eval/data`, `POST /api/eval/human-marks` — **admin**.

## Internal evaluation UI

After **`/login`**, open **`/admin`** or **`/eval-ui`**. `/eval-ui` is a small internal interface for human marking and inspection:
- browse task + answer variant,
- view student code and subtasks,
- view LLM marking by selected marker model,
- set human marks per subtask and notes,
- save directly to `evaluation/results/human_marks.csv`.

**Labeling workflow:** large Correct / Incorrect buttons per subtask, **Save & next** advances to the next answer attempt, shortcuts **Alt+N** / **Alt+P** (next/prev) and **Ctrl+Enter** (save; works while the notes field is focused).

The UI lists **all 20 tasks** by default (even if `TASK_IDS` / `TASK_LIMIT` are set for batch scripts). To restrict the UI to the same pilot subset as those env vars, set `EVAL_UI_PILOT_ONLY=true` before starting uvicorn.

No database is used.

## Primary metrics

`evaluation/compare_results.py` computes subtask-level metrics per marker model:
- accuracy
- agreement rate
- TP, TN, FP, FN
- precision
- recall
- F1
- per-concept accuracy
- per-variant-type accuracy

`evaluation/results/comparison_summary.csv` and `evaluation/results/confusion_matrix.csv` are also saved (set `SAVE_COMPARISON_SUMMARY` / `SAVE_CONFUSION_MATRIX` to `false` to skip).

### Why BLEU / ROUGE / METEOR are not the main metrics

Marking is evaluated as **subtask-level correctness** (human vs model on each binary subtask). BLEU-style n-gram overlap does not measure whether the model’s rubric judgement matches the human’s, so **accuracy, agreement, confusion counts, precision, recall, and F1** are the primary quantitative measures.

## 1. Benchmark task set

- Source: `data/fixed_tasks_with_answers.json` (20 tasks, 5 subtasks each, balanced concepts).
- Validation: `backend/dataset_validation.py` (`assert_valid_dataset`, etc.).

## 2. Answer variants

- Generator: `backend/generate_answer_variants.py`.
- Output: `data/generated_answers.json` (3 variants per task: `fully_correct`, `partly_correct`, `fully_incorrect`).

## 3. Marking evaluation

- Batch run: `evaluation/run_sample_eval.py` with `MARKING_MODELS` (e.g. `gemini,llama,mistral`).
- Output: `evaluation/results/marking_results.csv`.
- Human ground truth: `evaluation/results/human_marks.csv`.
- Metrics + confusion matrix: `python -m prototype_llm_eval.evaluation.compare_results` → `comparison_summary.csv`, `confusion_matrix.csv`, console tables.

## 4. Human marking UI

- Start server: `python -m uvicorn prototype_llm_eval.backend.main:app --reload` (from repo root).
- Set **`ADMIN_PASSWORD`** in `local.env`, then open `http://127.0.0.1:8000/login` and sign in, then **`/eval-ui`** (or **`/admin`**).
- Saves to `evaluation/results/human_marks.csv` via `POST /api/eval/human-marks`.
- Set `EVAL_UI_PILOT_ONLY=true` to mirror pilot `TASK_IDS` / `TASK_LIMIT` in the UI.

## 5. Question generation evaluation (human review sheet)

- **In-browser:** sign in at **`/login`**, open **`/research-dashboard`** → *Question appropriateness review* → pick each task, judge against the criteria panel, **Save review** (writes/updates the same CSV via `POST /api/research/question-review`).
- Generate Excel-friendly CSV (UTF-8 BOM):  
  `python -m prototype_llm_eval.evaluation.generate_question_review_sheet`  
  → `evaluation/results/question_generation_review.csv`
- Fill **`human_question_label`**: `appropriate` or `inappropriate`; **`notes`**; optional `level_fit`, `topic_fit`, `clarity`. (Columns are ordered for Excel: main labels appear after `subtasks_summary`.)
- Summarise:  
  `python -m prototype_llm_eval.evaluation.summarise_question_generation_review`

## 6. Feedback evaluation

- Env: `FEEDBACK_MODELS=gemini,llama,mistral` (comma-separated).
- **Default subset:** first **4** tasks after pilot filter (`FEEDBACK_EVAL_TASK_LIMIT`, default `4`). Set `FEEDBACK_EVAL_TASK_LIMIT=0` for no cap (all tasks after pilot filter), or `20` for full benchmark. If **`TASK_LIMIT`** is set, the default cap is **not** applied (pilot size already fixed).
- Run: `python -m prototype_llm_eval.evaluation.run_feedback_eval`  
  → `evaluation/results/feedback_results.json` and `feedback_results.csv` (columns include `task_id`, `concept`, `answer_id`, `variant_type`, `feedback_model`, `feedback_text`, `run_timestamp`, `actual_model_name`, `feedback_prompt_version`).
- **In-browser:** **`/research-dashboard`** → *Feedback quality review* (after `run_feedback_eval`). Saves via `POST /api/research/feedback-review` to `evaluation/results/feedback_review.csv`.
- Human review sheet (CLI):  
  `python -m prototype_llm_eval.evaluation.generate_feedback_review_sheet`  
  → `evaluation/results/feedback_review.csv` (fill scores 1–3 and `overall_feedback_label`: `poor` / `acceptable` / `good`).
- Summarise:  
  `python -m prototype_llm_eval.evaluation.summarise_feedback_review`

## 7. Validation report (methodology evidence)

- Run: `python -m prototype_llm_eval.evaluation.generate_validation_report`  
  → `evaluation/results/validation_report.json` and `validation_report.txt` (dataset validity, variant alignment, row counts, prompt versions, model names seen in marking CSV).

## 8. Student-facing demo page (supervisor / viva) — **live LLM task generation**

- Start server: `python -m uvicorn prototype_llm_eval.backend.main:app --reload`
- Open `http://127.0.0.1:8000/` (landing) or go directly to **`/demo-ui`** (public; no login).
- **Generate live task:** choose concept + difficulty → **Generate live task** → calls `POST /api/demo/generate-live-task` (fresh JSON from **`QUESTION_GENERATION_PROVIDER`**; **independent of `USE_FIXED_DATASET`**). Response includes `validation` (structural checks). Gemini auth errors return **`502`**/**`503`** with a clear `detail` string.
- **Optional contrast:** **Load frozen sample** → `GET /api/demo/task?task_id=q1` (read-only row from `fixed_tasks_with_answers.json`).
- **Marking / feedback:** `POST /api/demo/mark` and `POST /api/demo/feedback` resolve the task from **in-memory `task_store` first** (live task), else fall back to the frozen file by `task_id`.
- **Config hint:** `GET /api/demo/config` returns `USE_FIXED_DATASET`, **`question_generation_provider`**, **`marking_provider`**, **`feedback_provider`**, and related model names.

## 8b. Research dashboard (fixed-benchmark evidence)

- Sign in at **`/login`**, then open `http://127.0.0.1:8000/research-dashboard` (or use **`/admin`**). `GET /api/research-summary` includes `system_modes` (benchmark vs live demo, review CSV status).

## 9. Example cases for dissertation screenshots

- Run after marks / feedback / optional question review exist:  
  `python -m prototype_llm_eval.evaluation.export_example_cases`  
  → `evaluation/results/example_cases.json`

## Step-by-step workflow (full)

1. Prepare fixed dataset + model answers:  
   `python -m prototype_llm_eval.backend.prepare_fixed_dataset`
2. Generate answer variants:  
   `python -m prototype_llm_eval.backend.generate_answer_variants`
3. Pilot marking (optional): set `TASK_IDS`, `MARKING_MODELS`, then  
   `python -m prototype_llm_eval.evaluation.run_sample_eval`  
   `python -m prototype_llm_eval.evaluation.validate_pilot_outputs`
4. Human marking: uvicorn + **`/login`** + **`/eval-ui`** until `human_marks.csv` is complete.
5. Full marking (optional): clear pilot env vars,  
   `python -m prototype_llm_eval.evaluation.run_sample_eval`
6. Compare models vs human:  
   `python -m prototype_llm_eval.evaluation.compare_results`
7. Validation report:  
   `python -m prototype_llm_eval.evaluation.generate_validation_report`
8. Question review sheet + fill + summarise:  
   `python -m prototype_llm_eval.evaluation.generate_question_review_sheet`  
   (edit CSV)  
   `python -m prototype_llm_eval.evaluation.summarise_question_generation_review`
9. Feedback eval + review sheet + summarise:  
   `python -m prototype_llm_eval.evaluation.run_feedback_eval`  
   `python -m prototype_llm_eval.evaluation.generate_feedback_review_sheet`  
   (edit CSV)  
   `python -m prototype_llm_eval.evaluation.summarise_feedback_review`
10. Export examples:  
    `python -m prototype_llm_eval.evaluation.export_example_cases`
11. **Suggested supervisor flow:** uvicorn → **`/`** (landing story) → **`/demo-ui`** (public learner demo) → **`/login`** → **`/admin`** → **`/progress-ui`**, **`/eval-ui`**, **`/research-dashboard`** as needed.

## Key artifacts

| Artifact | Role |
|----------|------|
| `data/fixed_tasks_with_answers.json` | Fixed benchmark |
| `data/generated_answers.json` | Variant answers |
| `evaluation/results/marking_results.csv` | Multi-model automated marks |
| `evaluation/results/human_marks_template.csv` | Empty template |
| `evaluation/results/human_marks.csv` | Human ground truth |
| `evaluation/results/comparison_summary.csv` | Aggregated metrics |
| `evaluation/results/confusion_matrix.csv` | TP/TN/FP/FN counts |
| `evaluation/results/validation_report.json` / `.txt` | Pipeline checks |
| `evaluation/results/question_generation_review.csv` | Question appropriateness review |
| `evaluation/results/feedback_results.json` / `.csv` | Generated feedback runs |
| `evaluation/results/feedback_review.csv` | Human feedback quality review |
| `evaluation/results/example_cases.json` | Dissertation examples |
| `backend/live_task_validation.py` | Structural checks reported on live demo generation |
