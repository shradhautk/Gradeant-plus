# Gradeant-plus
Developing the prototype for the EDU-Core Proposal.
Extending GradeAnt for interactive feedback and NotebookLM Style summary

# GradeAnt+ Project Structure

gradeant-plus/
├── data/
│   ├── ga_format_input/
│   │   └── Narrie_HW3.json  (sample entry)
│   │   └── QP.json          (sample entry)
│   ├── input/
│   │   └── Narrie_HW3_with_QP.json   (sample entry)
│   └── output/
│       └── Narrie_HW3_summary.md     (sample entry)   
│
├── logs/
│   └── gradeantplus.log
│
├── src/
│   ├── agents.py     (agent definitions)
│   ├── main.py       (main entry point)
│   ├── prompts.py    (agent prompts/instructions)
│   └── utils.py      (helper functions)
│
├── README.md         (this file)
└── requirements.txt
