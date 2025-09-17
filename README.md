# Gradeant-plus
Developing the prototype for the EDU-Core Proposal.
Extending GradeAnt for interactive feedback and NotebookLM Style summary

# GradeAnt+ Project Structure
You are absolutely right. This is a very common and frustrating formatting issue.

The reason it "does not maintain shape" is because of **monospace vs. proportional fonts**.

*   **Monospace Font:** Every character takes up the exact same width (like in a code editor). The tree structure you created relies on this to make the vertical lines `│` align perfectly.
*   **Proportional Font:** Characters have different widths (`i` is narrower than `W`). Most websites, including GitHub, render plain text in a proportional font, which breaks the alignment.

### The Solution: Use a Markdown Code Block

To fix this, you must wrap the entire structure in a Markdown **code block**. This tells the renderer (like GitHub) to use a monospace font and preserve all your spacing and special characters exactly as you wrote them.

Here is how you should format it in your `README.md` file. Just copy and paste this entire block.

### Project Structure

```
gradeant-plus/
├── data/
│   ├── ga_format_input/
│   │   ├── Narrie_HW3.json
│   │   └── QP.json
│   ├── input/
│   │   └── Narrie_HW3_with_QP.json
│   └── output/
│       └── Narrie_HW3_summary.md
│
├── logs/
│   └── gradeantplus.log
│
├── src/
│   ├── agents.py
│   ├── main.py
│   ├── prompts.py
│   └── utils.py
│
├── README.md
└── requirements.txt
```

By enclosing your tree in the triple backticks (```), you guarantee that when you commit the file and view it on GitHub, GitLab, or any modern Markdown viewer, it will render perfectly and maintain its shape.
