# GradeAnt+

Developing the prototype for the EDU-Core Proposal.
Extending GradeAnt for interactive feedback and NotebookLM-style summary.

## Overview

GradeAnt grades students' homework automatically. GradeAnt+ goes a step further:
instead of stopping at a mark, it works through each answer with the student.

- It **analyses** every answer against a reference solution and identifies
  misconceptions, missing steps and the key concepts involved.
- When an answer needs work, it **tutors** the student with Socratic questions
  (up to three turns) instead of revealing the answer. Correct answers get
  specific positive reinforcement.
- At the end of a session it produces a **study guide** and a podcast-style
  **audio summary**, in the spirit of NotebookLM.

## Pipeline

```
GradeAnt output (student answers)  +  Question paper (reference answers, rubric)
                      │
                      ▼
          GA-format converter  (utils.py --convert)
                      │  data/input/<student>_with_QP.json
                      ▼
 ┌──────────────── for each question ────────────────┐
 │  KnowledgeAgent        analyse answer vs reference │
 │        │                                           │
 │  QuestionOrchestrator  route on needs_feedback     │
 │     ├── InteractiveTeachingAgent  Socratic dialogue│
 │     └── CorrectAnswerAgent        reinforcement    │
 └───────────────────────────────────────────────────┘
                      │
                      ▼
 SummarizationAgent → AudioScriptAgent → TtsAgent
                      │
                      ▼
 data/output/:  session log (JSON) · study guide (Markdown) · audio (MP3)
```

## Project Structure

```
gradeant-plus/
├── data/
│   ├── ga_format_input/
│   │   ├── <student>_HW3.json              (sample entry: GradeAnt output)
│   │   └── QP_Homework_3_rubric.json       (sample entry: question paper)
│   ├── input/
│   │   └── <student>_HW3_with_QP.json      (sample entry: merged input)
│   └── output/
│       ├── SummaryReport_Session<id>.md    (sample entry: study guide)
│       └── StructuredLog_Session<id>.json  (sample entry: full session log)
│
├── logs/
│   └── gradeantplus.log                    (created at run time)
│
├── src/
│   ├── agents.py       agent definitions and pipelines
│   ├── main.py         session runner (entry point)
│   ├── prompts.py      agent instructions
│   ├── utils.py        logging, validation, reports, GA-format converter
│   └── unit_test.py    end-to-end test with simulated student replies
│
├── .env.example        API key template
├── README.md
└── requirements.txt
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then set GOOGLE_API_KEY (Gemini) in .env
```

`.env` is gitignored; never commit a real key.

## Usage

Run all commands from `src/`:

```bash
cd src
python utils.py --convert   # web UI (port 7860): merge a GradeAnt answer file
                            # with the question paper into data/input/
python main.py              # run an interactive tutoring session
python unit_test.py         # end-to-end test (calls the Gemini API)
```

`main.py` reads `data/input/qa.json` by default; change `qa_file_path` in
`main()` to use another merged file.

## Sample Output

`data/output/` contains a sample three-question session (September 2025). The
study guide includes:

- session analytics: first-attempt success rate, feedback sessions, dialogue turns
- learning overview and the concepts and formulas covered
- misconceptions identified and how they were addressed
- a personalised study roadmap
- per-question analysis (status, key concepts, analysis confidence)

## Technology

Python · Google Agent Development Kit (ADK) · Gemini 2.0 Flash · gTTS · Gradio

## Status

Working prototype, developed September 2025.

## Next Steps

<!-- TO BE FILLED IN -->

## Authors

Dr. Agarwal's Research Team
