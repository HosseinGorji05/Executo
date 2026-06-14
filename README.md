⚡ Executo

> Natural language → tested Python, automatically.**
> Describe what you want. Executo writes the code, tests it in an isolated Docker sandbox, and fixes itself until the tests pass.

|
|
|

What it does

```
Your prompt  →  LLM writes code + tests  →  Docker sandbox runs tests
                                                    ↓
                                            Pass? → return code ✅
                                            Fail? → LLM reads error, fixes, retries 🔧
```

- **Self-correcting** — up to 4 attempts; the agent reads real unittest errors and rewrites
- **Sandboxed** — Docker with no network, capped CPU/RAM, read-only mounts
- **Benchmarked** — 90% pass rate on HumanEval (10-task sample)
- **Streaming UI** — watch generate → test → fix live in the browser

---

## Demo

```
$ python -m core.agent "Write a function is_prime(n) that returns True if n is prime."

🧠 Understanding your request…
✍️  Writing code and tests…
🧪  Attempt 1: tests ✅ passed

Overall: PASS after 1 attempt(s)
AI self-tests: PASS
```

---

## Quick start

### 1. Clone & set up
```bash
git clone https://github.com/HosseinGorji05/Executo.git
cd Executo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Add your API key
```bash
cp .env.example .env
# Edit .env and add your Groq key (free at console.groq.com/keys)
```

`.env`:
```
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

### 3. Start Docker Desktop
The sandbox requires Docker to be running.

### 4. Run
**Browser UI:**
```bash
python app.py
# Open http://127.0.0.1:7860
```

**CLI:**
```bash
python -m core.agent "Write a function that counts vowels in a string."
python -m core.agent --stream "Write a function is_leap_year(year)..."
```

**HumanEval benchmark:**
```bash
python eval_humaneval.py HumanEval/0
python eval_humaneval_batch.py --limit 10
```

---

## Project structure

```
Executo/
├── core/
│   ├── agent.py          # LangGraph loop: generate → execute → fix
│   ├── sandbox.py        # Docker runner (code + tests → pass/fail)
│   ├── prompts.py        # LLM system prompts
│   ├── humaneval.py      # HumanEval task loader + test wrapper
│   └── errors.py         # User-friendly error messages
├── app.py                # Gradio web UI
├── eval_humaneval.py     # Single HumanEval task eval
├── eval_humaneval_batch.py  # Batch benchmark (N tasks → pass rate)
├── run_isolated_unittest.py # Manual sandbox smoke test
├── download_coding_datasets.py
├── data/datasets/
│   ├── HumanEval.jsonl
│   └── mbpp.jsonl
├── .env.example
└── requirements.txt
```

---

## Benchmark

| Dataset     | Tasks | Pass rate |
|-------------|-------|-----------|
| HumanEval   | 10    | **90%**   |

Run your own:
```bash
python eval_humaneval_batch.py --limit 20
```

---

## Stack

| Layer         | Technology                        |
|---------------|-----------------------------------|
| Orchestration | LangGraph                         |
| LLM           | Groq (`llama-3.3-70b-versatile`)  |
| Sandbox       | Docker (isolated, no network)     |
| UI            | Gradio 6                          |
| Datasets      | HumanEval, MBPP                   |

---

## Rate limits

To protect against runaway usage, Executo enforces per-session limits via `core/rate_limit.py`:

- **10 runs per session** (configurable via `EXECUTO_MAX_RUNS_PER_SESSION`)
- **30-second cooldown** between runs (configurable via `EXECUTO_COOLDOWN_SECONDS`)

Set in `.env`:
```
EXECUTO_MAX_RUNS_PER_SESSION=10
EXECUTO_COOLDOWN_SECONDS=30
```

|
|
|

Environment variables

| Variable                       | Required | Default                      | Description                  |
|--------------------------------|----------|------------------------------|------------------------------|
| `GROQ_API_KEY`                 | ✅       | —                            | Groq API key                 |
| `GROQ_MODEL`                   | No       | `llama-3.3-70b-versatile`    | Groq model                   |
| `EXECUTO_MAX_RUNS_PER_SESSION` | No       | `10`                         | Max runs per browser session |
| `EXECUTO_COOLDOWN_SECONDS`     | No       | `30`                         | Cooldown between runs (sec)  |

|
|
|


## License

MIT
