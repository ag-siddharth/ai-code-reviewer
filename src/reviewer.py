"""
Code review logic. Sends code to Claude and parses structured feedback.
"""

import json
import logging
from pathlib import Path
from anthropic import Anthropic
from src.utils import get_client, chunk_file

logger = logging.getLogger(__name__)

REVIEW_SYSTEM_PROMPT = """You are a senior software engineer doing a code review. 
Analyze the code and return your review as a JSON array of comments.

Each comment should have:
- "line": approximate line number (integer)
- "severity": one of "error", "warning", "info"
- "category": one of "bug", "style", "security", "performance", "documentation", "error_handling", "naming"
- "message": clear, actionable feedback (1-2 sentences)

Also include a "summary" field with a 1-2 sentence overall assessment.

Return ONLY valid JSON in this format:
{
    "summary": "...",
    "comments": [{"line": 1, "severity": "warning", "category": "style", "message": "..."}]
}

Focus on:
- Missing error handling
- Type hint gaps
- Missing or incomplete docstrings  
- Security concerns (hardcoded secrets, SQL injection, etc)
- Naming issues
- Obvious bugs

Do NOT comment on:
- Personal style preferences (single vs double quotes, etc)
- Import ordering (leave that to linters)
- Things that are clearly intentional design choices"""


def review_file(file_path, config):
    """Review a single file and return structured comments."""
    file_path = Path(file_path)

    try:
        code = file_path.read_text()
    except Exception as e:
        return {"file": str(file_path), "comments": [], "summary": f"Could not read file: {e}"}

    if not code.strip():
        return {"file": str(file_path), "comments": [], "summary": "Empty file"}

    # chunk large files
    chunks = chunk_file(code, max_lines=500)
    all_comments = []
    summaries = []

    client = get_client()
    model = config.get("model", "claude-sonnet-4-6")
    max_tokens = config.get("max_tokens", 2000)

    for i, chunk in enumerate(chunks):
        offset = chunk["start_line"]
        chunk_code = chunk["code"]

        prompt = f"Review this {file_path.suffix.lstrip('.')} code"
        if len(chunks) > 1:
            prompt += f" (chunk {i+1}/{len(chunks)}, lines {chunk['start_line']}-{chunk['end_line']})"
        prompt += f":\n\n```\n{chunk_code}\n```"

        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=REVIEW_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text.strip()

            # sometimes the model wraps the json in backticks
            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[1]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]
                response_text = response_text.strip()

            result = json.loads(response_text)

            # adjust line numbers for the chunk offset
            for comment in result.get("comments", []):
                comment["line"] = comment.get("line", 0) + offset
                all_comments.append(comment)

            if result.get("summary"):
                summaries.append(result["summary"])

        except json.JSONDecodeError:
            logger.warning(f"Failed to parse review response for {file_path} chunk {i+1}")
            # still try to use the raw text
            all_comments.append({
                "line": 0,
                "severity": "info",
                "category": "documentation",
                "message": response_text[:200] if 'response_text' in dir() else "Parse error",
            })
        except Exception as e:
            logger.error(f"API error reviewing {file_path}: {e}")
            return {"file": str(file_path), "comments": [], "summary": f"Error: {e}"}

    summary = summaries[0] if summaries else "No issues found"

    return {
        "file": str(file_path),
        "comments": all_comments,
        "summary": summary,
    }


def review_files(file_paths, config):
    """Review multiple files. Returns list of results."""
    results = []
    for fp in file_paths:
        logger.info(f"Reviewing {fp}")
        result = review_file(fp, config)
        results.append(result)
    return results
