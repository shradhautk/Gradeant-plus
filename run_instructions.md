# GradeAnt+ Run Instructions

Step-by-step instructions for setting up and running the GradeAnt+ tutoring
pipeline. For an overview of the project, see the [README](README.md).

**Contents**

1. [Prerequisites](#1-prerequisites)
2. [Setup](#2-setup)
3. [Prepare the input files](#3-prepare-the-input-files)
4. [Merge answers and question paper](#4-merge-answers-and-question-paper)
5. [Choose the session input](#5-choose-the-session-input)
6. [Dry run (no API calls)](#6-dry-run-no-api-calls)
7. [Run a tutoring session](#7-run-a-tutoring-session)
8. [Outputs](#8-outputs)
9. [Checks and tests](#9-checks-and-tests)
10. [Troubleshooting](#10-troubleshooting)

**Run scenarios at a glance** (commands run from `src/`)

| Scenario | Command | API key? | Section |
|---|---|---|---|
| Merge a student answer file with the question paper | `python utils.py --convert` | No | [4](#4-merge-answers-and-question-paper) |
| Use a hand-written input file (no converter) | edit `qa_file_path`, then run | – | [5](#5-choose-the-session-input) |
| Check the setup and input without calling the model | `python main.py --dry-run` | No | [6](#6-dry-run-no-api-calls) |
| Run a live tutoring session | `python main.py` | Yes | [7](#7-run-a-tutoring-session) |
| Run sessions for several students | repeat steps 4–7 per student | Yes | [7](#7-run-a-tutoring-session) |
| Validate the input file only | `python utils.py` | No | [9](#9-checks-and-tests) |
| Run the automated end-to-end tests | `python unit_test.py` | Yes | [9](#9-checks-and-tests) |
| Show command-line options | `python main.py --help` | No | [9](#9-checks-and-tests) |

---

## 1. Prerequisites

- Python 3 with `pip`
- A Google Gemini API key (for live sessions only; a dry run needs no key)
- Internet access (for live sessions only)

## 2. Setup

From the repository root:

```bash
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and set your Gemini key:

```
GOOGLE_API_KEY=your-gemini-api-key
```

`.env` is gitignored: never commit a real key. A `GOOGLE_API_KEY` already set
in your shell takes precedence over the one in `.env`.

**All commands below are run from the `src/` folder:**

```bash
cd src
```

They also work from the repository root with the `src/` prefix, e.g.
`python src/main.py --dry-run`. Input and output paths are the same either way.

## 3. Prepare the input files

Place two JSON files in `data/ga_format_input/`.

**Student answer file** (GradeAnt format): each question or subpart carries
the student's answer in `reply`.

```json
{
  "homework": "Homework 3",
  "questions": [
    {
      "question_number": 1,
      "subparts": [
        { "subpart": "a", "description": "Question 1a text", "reply": "Student answer to 1a" }
      ]
    },
    { "question_number": 2, "description": "Question 2 text", "reply": "Student answer to 2" }
  ]
}
```

**Question paper file**: the same structure, with `standard_answer`,
`max_marks` and `rubric` on each question or subpart.

```json
{
  "homework": "Homework 3",
  "questions": [
    {
      "question_number": 1,
      "subparts": [
        { "subpart": "a", "description": "Question 1a text", "max_marks": 5,
          "standard_answer": "Reference answer to 1a", "rubric": "How marks are awarded" }
      ]
    },
    { "question_number": 2, "description": "Question 2 text", "max_marks": 10,
      "standard_answer": "Reference answer to 2", "rubric": "How marks are awarded" }
  ]
}
```

Questions are matched by `question_number`, and subparts by `subpart` letter.
`data/ga_format_input/` contains complete sample files.

## 4. Merge answers and question paper

The converter turns the two files into one GradeAnt+ input file:

```bash
python utils.py --convert
```

1. Open **http://localhost:7860** in a browser.
2. Upload the **Homework** JSON and the **Question Paper** JSON.
3. Click **Merge Files** and check the merged JSON shown on the page.
4. Click **Save to Output Folder**.
5. Stop the converter with `Ctrl+C` in the terminal.

The merged file is saved as `data/input/<answer-file-name>_with_QP.json`.
Each question or subpart becomes one entry:

```json
{
  "question_id": "q1a",
  "question_text": "Question 1a text",
  "student_answer": "Student answer to 1a",
  "reference_answer": "Reference answer to 1a",
  "max_marks": 5,
  "rubric": "How marks are awarded"
}
```

> The converter listens on all network interfaces (`0.0.0.0`), so other
> machines on your network can reach port 7860 while it runs.

## 5. Choose the session input

The session input file and student ID are set in `src/main.py`, in the
function `main()`:

```python
qa_file_path = INPUT_FOLDER / "qa.json"      # change to your merged file
...
user_id = "..."                              # change to the student's ID
```

For example: `qa_file_path = INPUT_FOLDER / "<student>_HW3_with_QP.json"`.

Every question must have non-empty text values for `question_id`,
`question_text`, `student_answer` and `reference_answer`; questions missing
any of them are skipped with a warning.

### Writing an input file by hand (without the converter)

You can skip step 4 and write the input file yourself in `data/input/`. Two
layouts are accepted: a plain list of questions, or an object with a
`questions` list (the converter's layout). `max_marks` and `rubric` are
optional.

```json
[
  {
    "question_id": "q1",
    "question_text": "A car accelerates uniformly from rest to 20 m/s in 5 seconds. What is its acceleration?",
    "student_answer": "a = (v - u)/t = (20 - 0)/5 = 4 m/s^3",
    "reference_answer": "a = (v - u)/t = (20 - 0)/5 = 4 m/s^2"
  }
]
```

`data/input/qa.json` is a ready-made example of this layout.

## 6. Dry run (no API calls)

Check the setup and the input file before spending API credit:

```bash
python main.py --dry-run
```

A dry run loads and validates the input, routes every question (odd-numbered
questions as correct, even-numbered as needing feedback, so both paths are
used), and writes the session log and study guide. **No model is called**: all
analysis, dialogue and summary text is a canned placeholder. It needs no API
key, no internet, and does not use Google ADK or gTTS. No audio is produced.

Dry-run outputs are clearly marked:

- file names end in `_dryrun`
- the JSON log starts with a `dry_run_notice` and has `"dry_run": true`
- the study guide title starts with `[DRY RUN]`, followed by a warning banner
- log lines are tagged `[DRY RUN]`

A dry run checks input loading, routing and report generation. It does
**not** test the agents, prompts or the live ADK session; only a live run does.

## 7. Run a tutoring session

```bash
python main.py
```

For each question:

1. The answer is analysed against the reference answer (misconceptions,
   missing steps, key concepts).
2. **Correct answers** receive brief positive feedback and the session moves on.
3. **Answers that need work** start a Socratic dialogue in the terminal. The
   tutor asks a guiding question and you type the student's reply:
   - press **Enter** on an empty line to answer "I'm not sure"
   - type `exit`, `skip`, `quit`, `done`, `stop` or `end` to finish the dialogue
   - the dialogue ends automatically after **three turns**
   - `Ctrl+C` / `Ctrl+D` at the prompt also ends the dialogue

After the last question, GradeAnt+ writes the session summary, the study guide
and the audio summary.

**Other situations**

- **Several students:** the pipeline handles one student per session. Repeat
  steps 4–7 for each student's answer file. The session `<id>` combines the
  date, the time (to the minute) and the input file name, so different
  students' outputs never overwrite each other. Re-running the *same* file
  within the same minute would reuse the `<id>`.
- **No interactive terminal** (e.g. input piped in, or run as a background
  job): each dialogue ends immediately, as if the student typed `exit`.
  Analysis, feedback and reports are still produced.
- **Audio fails** (e.g. no internet for gTTS): the session log and study guide
  are still written, and the console reports
  `Audio summary could not be generated.`

## 8. Outputs

Each session writes to `data/output/` (`<id>` is the date, time and input name):

| File | Contents |
|---|---|
| `SummaryReport_Session<id>.md` | Study guide: session analytics, concepts and formulas, misconceptions addressed, personalised study roadmap, per-question analysis |
| `StructuredLog_Session<id>.json` | Full session record: metadata, summary, and every question's analysis and dialogue |
| `SummaryAudio_Session<id>.mp3` | Podcast-style audio summary (live sessions only) |

Run details are logged to `logs/gradeantplus.log`.

## 9. Checks and tests

| Command | What it does | Needs API key? |
|---|---|---|
| `python utils.py` | Validates `data/input/qa.json` and checks the session-analytics code | No |
| `python main.py --dry-run` | Full session flow with canned responses | No |
| `python unit_test.py` | End-to-end sessions with simulated student replies | **Yes** (calls Gemini) |
| `python main.py --help` | Lists the command-line options | No |

`unit_test.py` runs three groups of live sessions on built-in sample physics
questions (a full session, concept questions and calculation questions),
typing scripted student replies automatically. It writes real session logs,
study guides and audio files to `data/output/`, and ends with a pass/fail
summary.

## 10. Troubleshooting

| Message or symptom | Fix |
|---|---|
| `GOOGLE_API_KEY is not set` | Create `.env` from `.env.example` and add your key (section 2) |
| `ModuleNotFoundError` (e.g. `google.adk`, `gtts`, `gradio`) | Run `pip install -r requirements.txt` |
| `No valid questions found in ...` | Check the four required fields in the input file (section 5) |
| Converter: `Missing required fields ...` | Answer file needs `description` and `reply`; question paper needs `description`, `standard_answer`, `max_marks` and `rubric` (section 3) |
| Converter: `HW file missing 'reply' key` / `QP file missing 'standard_answer' key` | The files were uploaded in the wrong boxes, or are not in the expected format |
| Converter page does not open | Port 7860 is in use by another program; stop it and retry |
