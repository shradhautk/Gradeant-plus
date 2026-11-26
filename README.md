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
├── run_instructions.md detailed run guide
├── README.md
└── requirements.txt
```

## Running GradeAnt+

```bash
pip install -r requirements.txt
cp .env.example .env        # then set GOOGLE_API_KEY (Gemini) in .env
cd src
python main.py --dry-run    # test run: no API calls
python main.py              # interactive tutoring session
```

**For full instructions, see [run_instructions.md](run_instructions.md):**
preparing and merging input files, choosing the session input, dry runs, live
sessions, outputs, tests and troubleshooting.

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

## Authors

Dr. Agarwal's Research Team
