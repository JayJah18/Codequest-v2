# prototype_llm_eval

Dissertation-ready evaluation prototype for LLM-based:
1. task generation,
2. marking,
3. feedback.

It stays modular and offline-friendly, and prioritizes reproducible artifacts over product features.

## Why Gemini 2.5 for dataset generation

Generation is fixed to Gemini by default (`gemini-2.5-flash`) because benchmark preparation needs fast, reliable structured outputs. This reduces dataset-build latency and stabilizes schema adherence for the fixed task bank.

Ollama models are still included as open-model baselines for comparative marking/feedback experiments.

## Why multiple models for marking and feedback

Marking and feedback are run across multiple providers (`gemini`, `llama`, `mistral`) to support comparative evaluation:
- proprietary cloud vs open/local models,
- agreement robustness against human ground truth,
- model-specific failure modes in grading/feedback behavior.

## Provider abstraction

`backend/llm_provider.py` defines:
- `LLMProvider.generate_text(prompt, system_prompt=None) -> str`
- `LLMProvider.generate_json(prompt, system_prompt=None) -> dict`

Providers:
- `GeminiProvider` (Google Generative AI, `GEMINI_API_KEY`)
- `OllamaProvider` (local HTTP API, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`)
- `MistralProvider` (Mistral API if `MISTRAL_API_KEY` exists, otherwise Ollama fallback model)

Factory:
- `get_provider(name)` with names: `gemini`, `llama`, `mistral`

## Strict task schema

Every task must follow:

```json
{
  "task_id": "q1",
  "concept": "variables",
  "difficulty": "beginner",
  "question_text": "string",
  "subtasks": [
    {"subtask_id": "s1", "label": "string"},
    {"subtask_id": "s2", "label": "string"},
    {"subtask_id": "s3", "label": "string"},
    {"subtask_id": "s4", "label": "string"},
    {"subtask_id": "s5", "label": "string"}
  ],
  "model_answer": "string"
}
```

Rules:
- exactly 20 tasks
- concept split: 5 variables / 5 conditionals / 5 loops / 5 functions
- exactly 5 subtasks per task
- total subtasks = 100
- unique `subtask_id` values per task

Subtasks are label-based and independently markable, enabling granular marking and disagreement analysis.

## Prompt contract consistency (fair comparison)

All marking models use the same `prompts/marking_prompt.txt` schema contract. Consistent prompt/output contracts are necessary so performance differences are due to model behavior, not formatting mismatches.

## Environment configuration

- `GEMINI_API_KEY` (required for Gemini provider)
- `GEMINI_MODEL` (default: `gemini-2.5-flash`)
- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `OLLAMA_MODEL` (default for `llama`: `llama3.1`)
- `MISTRAL_API_KEY` (optional; if missing, uses Ollama mistral fallback)
- `MISTRAL_MODEL` (default: `mistral-small-latest`)
- `MISTRAL_OLLAMA_MODEL` (default local fallback: `mistral`)
- `TASK_GENERATION_PROVIDER` (default: `gemini`)
- `ANSWER_VARIANT_PROVIDER` (default: `gemini`)
- `MARKING_MODELS` (default: `gemini`; example: `gemini,llama,mistral`)
- `FEEDBACK_MODELS` (default: `gemini`; example: `gemini,llama,mistral`)

## Workflow

1. Prepare fixed dataset + model answers (single provider, default Gemini):
   - `python -m prototype_llm_eval.backend.prepare_fixed_dataset`
2. Generate student answer variants:
   - `python -m prototype_llm_eval.backend.generate_answer_variants`
3. Run multi-model marking:
   - `python -m prototype_llm_eval.evaluation.run_sample_eval`
4. Run multi-model feedback eval (smaller subset):
   - `python -m prototype_llm_eval.evaluation.run_feedback_eval`
5. Fill human marks:
   - copy `evaluation/results/human_marks_template.csv` -> `evaluation/results/human_marks.csv`
   - fill `human_mark` per row (`correct/incorrect` or `1/0`)
6. Compare each marker model vs human:
   - `python -m prototype_llm_eval.evaluation.compare_results`

## API notes

### `POST /generate-task`
Input:
```json
{"concept":"loops","difficulty":"beginner"}
```
Output: strict task schema above.

### `POST /mark-answer`
Input:
```json
{"task_id":"...","student_answer":"..."}
```
Output:
```json
{
  "subtask_results": [
    {"subtask_id":"s1","correct":true,"reason":"..."}
  ],
  "overall_score": 4,
  "max_score": 5,
  "star_rating": 4,
  "reasoning": "..."
}
```

### `POST /generate-feedback`
Input:
```json
{"task_id":"...","student_answer":"...","marking_result":{}}
```
Output:
```json
{"feedback":"..."}
```

## Output artifacts

- `data/fixed_tasks_with_answers.json` (fixed benchmark tasks + model answers)
- `data/generated_answers.json` (3 answer variants per task)
- `evaluation/results/marking_results.csv` (includes `marker_model`)
- `evaluation/results/human_marks_template.csv` (ground-truth template)
- `evaluation/results/feedback_results.json` (feedback model comparison)
- `evaluation/results/comparison_summary.csv` (per-marker metric summary)

## Evaluation interpretation

- **Granular marking**: each subtask is judged separately.
- **Answer variants**: simulate realistic student levels (strong / partial / weak).
- **Human comparison**: human marks are the reference.
- **Metrics**:
  - accuracy, agreement rate
  - confusion matrix counts (TP, TN, FP, FN)
  - precision/recall/F1
  - optional per-concept accuracy
