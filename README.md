# ai-code-reviewer

CLI tool that uses Claude and GitHub Copilot to auto-generate code review comments and documentation for Python and TypeScript codebases.

I got tired of writing the same kinds of docstrings and review comments over and over, so I built this to handle the boring parts. It's not a replacement for real code review — more like a first pass that catches the obvious stuff (missing docstrings, type hints, error handling patterns, etc).

## What it does

- **`review`** — Analyzes a file or directory and generates review comments (style, bugs, missing error handling, etc.)
- **`document`** — Generates/updates docstrings and inline comments for functions that don't have them
- **`diff`** — Reviews only the changed lines in a git diff (useful in CI)

Works with Python and TypeScript files. Uses the Anthropic API (Claude) under the hood.

## Setup

```bash
git clone https://github.com/ag-siddharth/ai-code-reviewer.git
cd ai-code-reviewer
pip install -r requirements.txt
```

### API key

You'll need an Anthropic API key:

```bash
cp .env.example .env
# add your ANTHROPIC_API_KEY
```

### Install as CLI tool (optional)

```bash
pip install -e .
# now you can use `codereview` from anywhere
```

## Usage

### Review a file

```bash
python -m src.cli review path/to/file.py
# or if installed:
codereview review path/to/file.py
```

### Review a whole directory

```bash
codereview review src/ --ext py,ts
```

### Generate documentation

```bash
codereview document path/to/file.py
# writes updated file to path/to/file.documented.py
# use --inplace to modify the original
codereview document path/to/file.py --inplace
```

### Review a git diff (for CI)

```bash
codereview diff --base main
# reviews only changed files against main branch
```

### Output formats

```bash
codereview review src/ --format json     # machine readable
codereview review src/ --format markdown  # nice for PRs
codereview review src/ --format text      # default, terminal friendly
```

## GitHub Actions

There's a workflow in `.github/workflows/auto_review.yml` that runs on every PR. It posts review comments directly on the PR. To use it:

1. Add `ANTHROPIC_API_KEY` to your repo secrets
2. Copy the workflow file to your repo's `.github/workflows/`

The action only reviews changed files, so it won't burn through your API credits on every push.

## Config

Create a `config.yaml` in the project root (or pass `--config`):

```yaml
# what to focus on during reviews
review_focus:
  - missing_error_handling
  - type_hints
  - docstrings
  - security
  - naming

# max files to process in one run
max_files: 50

# model settings
model: claude-sonnet-4-6
max_tokens: 2000
```

## How it works

Not rocket science — it reads your code, builds a prompt with the relevant context (imports, function signatures, surrounding code), and asks Claude to review/document it. The tricky part was getting the prompts right so the output is actually useful and not generic "consider adding error handling" stuff.

For documentation, it parses the AST to find functions/classes without docstrings, generates them, and patches them back into the source. For TypeScript, it uses a regex-based parser since I didn't want to pull in a full TS compiler.

## Limitations

- TypeScript support is decent but not perfect (no JSX parsing yet)
- Large files (>500 lines) get chunked, which sometimes loses context
- It costs money — budget ~$0.01-0.03 per file reviewed
- Won't catch logic bugs or architectural issues, mostly style/documentation stuff

## TODO

- [ ] JSX/TSX support
- [ ] Config for custom review rules
- [ ] Cache results to avoid re-reviewing unchanged functions
- [ ] Support for more languages (Go, Java)
