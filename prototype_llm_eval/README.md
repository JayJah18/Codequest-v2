# prototype_llm_eval

Focused research prototype for evaluating three LLM roles in a controlled workflow:
1. Task generation
2. Marking
3. Feedback generation

This is intentionally separate from the broader CodeQuest system and keeps architecture minimal for dissertation evaluation.

## Folder structure

- `backend/` - FastAPI app with 3 endpoints and in-memory task storage
- `frontend/` - plain HTML/CSS/JS UI
- `evaluation/` - helpers and scripts for marking experiments/comparison
- `data/` - fixed tasks dataset and generated student answers
- `prompts/` - editable prompt templates for each LLM role
- `README.md` - usage and architecture notes

## How to run

From the repo root:

1. Ensure dependencies are installed:
   - `pip install -r requirements.txt`
2. Ensure Ollama is running locally and a model is available (default: `llama3.2:3b`)
3. Start the prototype backend:
   - `uvicorn prototype_llm_eval.backend.main:app --reload`
4. Open:
   - `http://127.0.0.1:8000/`

Optional environment variables:
- `OLLAMA_URL` (default `http://localhost:11434/api/generate`)
- `OLLAMA_MODEL` (default `llama3.2:3b`)
- `USE_FIXED_DATASET` (default `true`)

## Fixed dataset mode

The prototype now supports a reproducible 20-question fixed dataset:

- `data/fixed_tasks.json` - 20 predefined tasks (5 each for variables, conditionals, loops, functions)
- `data/fixed_tasks_with_answers.json` - same tasks after model answers are generated
- `data/generated_answers.json` - answer variants per task (correct, partially_correct, incorrect)

When `USE_FIXED_DATASET=true`, `POST /generate-task` returns a matching task from `fixed_tasks_with_answers.json` and does not call the task generation LLM.
When `USE_FIXED_DATASET=false`, it uses the existing dynamic LLM generation flow.

## Generate model answers for fixed tasks

Before fixed-mode task serving, generate model answers once:

- `python -m prototype_llm_eval.backend.generate_model_answers`

This reads `fixed_tasks.json`, calls Ollama for each task, and writes `fixed_tasks_with_answers.json`.

## Evaluation pipeline

1. Generate model answers (if not already done):
   - `python -m prototype_llm_eval.backend.generate_model_answers`
2. Run sample marking evaluation:
   - `python -m prototype_llm_eval.evaluation.run_sample_eval`
3. Output produced:
   - `evaluation/results/marking_results.csv`
4. Fill human marks:
   - Copy `evaluation/results/human_marks_template.csv` to `evaluation/results/human_marks.csv`
   - Fill `human_mark` per subtask (`correct`/`incorrect` or `1`/`0`)
5. Compare LLM vs human marking:
   - `python -m prototype_llm_eval.evaluation.compare_results`

Comparison script prints:
- accuracy
- agreement rate
- confusion matrix counts (TP, TN, FP, FN)

## API routes

### `POST /generate-task`
Input:
```json
{
  "concept": "loops",
  "difficulty": "beginner"
}
```
Output includes:
- `task_id`
- `concept`
- `difficulty`
- `question_text`
- `subtasks` (4-5 items)
- `model_answer`

### `POST /mark-answer`
Input:
```json
{
  "task_id": "...",
  "student_answer": "..."
}
```
Output includes per-subtask marks, scores, star rating, and reasoning.

### `POST /generate-feedback`
Input:
```json
{
  "task_id": "...",
  "student_answer": "...",
  "marking_result": {}
}
```
Output:
```json
{
  "feedback": "..."
}
```

## LLM role design

- Task generation LLM:
  - Uses `prompts/task_generation_prompt.txt`
  - Returns structured task JSON in a beginner-friendly format
- Marking LLM:
  - Uses `prompts/marking_prompt.txt`
  - Marks each subtask as correct/incorrect and returns structured scoring
- Feedback LLM:
  - Uses `prompts/feedback_prompt.txt`
  - Produces learner-friendly feedback from task context + marking result

All three roles call Ollama with JSON-mode responses for easier downstream evaluation.
