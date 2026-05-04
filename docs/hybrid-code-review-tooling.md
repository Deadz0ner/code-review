# Code Review Tooling

## Why Three Tools?

We picked these three tools because they cover three fundamentally different types of code review problems:

| Tool | Review area | Question it answers |
| --- | --- | --- |
| `pylint` | Linting and correctness | Does the code follow rules, and is it correct syntactically? |
| `bandit` | Security | Is there anything dangerous or exploitable? |
| `radon` | Complexity | Is this code too complex to maintain? |

They are also among the most established and well-documented Python tools for each category.

That said, they are not the only possible choices:

| Category | Current choice | Alternatives |
| --- | --- | --- |
| Linting and bugs | `pylint` | `flake8`, `ruff`, `mypy` |
| Security | `bandit` | `semgrep`, `safety` |
| Complexity | `radon` | `wily`, `lizard` |
| Dead code | Nothing yet | `vulture` |
| Formatting | Nothing yet | `black`, `isort` |
| Test coverage | Nothing yet | `pytest-cov` |

`ruff` is especially worth knowing. It is replacing `pylint` and `flake8` for many teams because it is often 10-100x faster.

## Why Not Just Send Code to Claude?

Technically, Claude can read code and spot bugs, security issues, and complexity problems without any tools. For small files, it can do this well.

But static analysis tools still matter.

### Determinism

Tools like `pylint` and `bandit` will consistently catch issues such as unused imports or hardcoded passwords. Claude might miss them if the file is long, the context window is full, or the surrounding code distracts from the issue.

### Line-Level Precision

Static analysis tools return exact line numbers. Claude may describe an issue as being "around the auth function." In a 2,000-line file, that difference matters.

### Scale

If the tool scans a folder with 50 files, Claude cannot hold all of that code in context at once. Static analysis tools can scan everything first, then Claude only needs to review the findings. That gives the LLM a much smaller, more structured input.

### Credibility

"Bandit found a SQL injection vulnerability at line 47 with CWE-89" is verifiable. "Claude thinks there might be a security issue" is more speculative. For a code review tool that people need to trust, that distinction matters.

The intended architecture is:

> Static tools do the detection. Claude does the synthesis and explanation.

Neither approach is as strong alone as both are together.

## How Other Code Review Projects Work

Most code review projects fall into a few categories.

### Pure LLM Review

Tools like GitHub Copilot PR reviews, CodeRabbit, and Ellipsis use an LLM to read diffs and leave comments.

This approach is fast to build, but it can miss issues and hallucinate fixes.

### Pure Static Analysis

Tools like SonarQube, Snyk, and Checkmarx rely on deterministic analysis without an LLM.

This approach is scalable and verifiable, but the output can be raw, noisy, and harder for developers to act on. It often lacks clear explanation or practical fix suggestions.

### Hybrid Review

Hybrid tools use static analysis for detection and an LLM for synthesis, prioritization, and explanation.

This is the architecture we are building. Newer tools like Qodo, formerly CodiumAI, and Trunk.io are moving in this direction because it combines deterministic scanning with useful human-readable review output.

### CI/CD Integrated Review

Tools like Danger.js and Reviewdog run in a CI/CD pipeline, such as GitHub Actions, and post comments directly on pull requests.

In this model, analysis happens automatically on every push.

## Why This Prototype Is Honest

The prototype is genuinely hybrid. It is not just Claude with a "tools" label attached.

The static tools produce concrete findings. Claude then turns those findings into a review that is easier to understand, prioritize, and act on.
