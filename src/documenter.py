"""
Documentation generator. Finds undocumented functions/classes and generates
docstrings using Claude.

For Python: uses AST to find functions missing docstrings.
For TypeScript: uses regex matching (good enough for most cases).
"""

import ast
import re
import json
import logging
from pathlib import Path
from src.utils import get_client

logger = logging.getLogger(__name__)

DOCGEN_SYSTEM_PROMPT = """You are a documentation writer. Given a function or class definition, 
generate a clear, concise docstring in the appropriate style.

For Python: use Google-style docstrings.
For TypeScript: use JSDoc format.

Return ONLY a JSON object:
{
    "docstring": "the docstring text (properly formatted with newlines)",
    "params": [{"name": "x", "type": "int", "description": "..."}]  
}

Keep it brief — 1-2 sentences for the description, plus param/return docs.
Don't state the obvious ("This function does X" when the function is called do_x)."""


def document_file(file_path, config):
    """
    Generate docstrings for undocumented functions in a file.
    Returns the updated file content, or None if nothing to document.
    """
    file_path = Path(file_path)
    code = file_path.read_text()

    if file_path.suffix == ".py":
        return _document_python(code, config)
    elif file_path.suffix in (".ts", ".js"):
        return _document_typescript(code, config)
    else:
        logger.warning(f"Unsupported file type: {file_path.suffix}")
        return None


def _document_python(code, config):
    """Find Python functions without docstrings and generate them."""

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        logger.error(f"Syntax error in file: {e}")
        return None

    lines = code.split("\n")
    functions_to_doc = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # check if it already has a docstring
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, (ast.Str, ast.Constant))):
                continue  # already documented

            # skip private helpers (single underscore is fine, dunder is fine)
            if node.name.startswith("_") and not node.name.startswith("__"):
                continue

            # get the source for this function
            start = node.lineno - 1
            end = node.end_lineno if hasattr(node, "end_lineno") else start + 20
            func_source = "\n".join(lines[start:end])

            functions_to_doc.append({
                "name": node.name,
                "line": node.lineno,
                "source": func_source,
                "type": "class" if isinstance(node, ast.ClassDef) else "function",
            })

    if not functions_to_doc:
        return None

    logger.info(f"Found {len(functions_to_doc)} undocumented functions/classes")

    client = get_client()
    model = config.get("model", "claude-sonnet-4-6")

    # generate docstrings
    insertions = []  # (line_number, docstring_text)

    for func in functions_to_doc:
        prompt = f"Generate a docstring for this Python {func['type']}:\n\n```python\n{func['source']}\n```"

        try:
            response = client.messages.create(
                model=model,
                max_tokens=500,
                system=DOCGEN_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            resp_text = response.content[0].text.strip()
            if resp_text.startswith("```"):
                resp_text = resp_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(resp_text)
            docstring = result.get("docstring", "")

            if docstring:
                insertions.append((func["line"], docstring))
                logger.info(f"  Generated docstring for {func['name']}")

        except Exception as e:
            logger.warning(f"  Failed to generate docstring for {func['name']}: {e}")

    if not insertions:
        return None

    # apply insertions (bottom-up so line numbers don't shift)
    insertions.sort(key=lambda x: x[0], reverse=True)

    for line_num, docstring in insertions:
        # figure out indentation
        func_line = lines[line_num - 1]
        indent = len(func_line) - len(func_line.lstrip())
        body_indent = " " * (indent + 4)

        # format the docstring
        doc_lines = docstring.split("\n")
        if len(doc_lines) == 1:
            formatted = f'{body_indent}"""{docstring}"""'
        else:
            formatted = f'{body_indent}"""\n'
            for dl in doc_lines:
                formatted += f"{body_indent}{dl}\n"
            formatted += f'{body_indent}"""'

        # insert after the def line (and any decorators)
        insert_at = line_num  # lines list is 0-indexed, line_num is 1-indexed
        lines.insert(insert_at, formatted)

    return "\n".join(lines)


def _document_typescript(code, config):
    """
    Find TypeScript functions without JSDoc and generate comments.
    Uses regex since we don't have a TS parser available.
    """

    # match function/method declarations that don't have a JSDoc comment above them
    # this is imperfect but works for most cases
    func_pattern = re.compile(
        r"^(\s*)((?:export\s+)?(?:async\s+)?function\s+\w+|"
        r"(?:export\s+)?(?:const|let)\s+\w+\s*=\s*(?:async\s+)?\(|"
        r"\w+\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{)",
        re.MULTILINE
    )

    lines = code.split("\n")
    functions_to_doc = []

    for match in func_pattern.finditer(code):
        line_num = code[:match.start()].count("\n")

        # check if previous non-empty line is a JSDoc closing
        prev_line = ""
        for i in range(line_num - 1, max(line_num - 5, -1), -1):
            if i >= 0 and lines[i].strip():
                prev_line = lines[i].strip()
                break

        if prev_line.endswith("*/"):
            continue  # already has JSDoc

        # grab a few lines for context
        end = min(line_num + 15, len(lines))
        func_source = "\n".join(lines[line_num:end])

        functions_to_doc.append({
            "line": line_num,
            "source": func_source,
            "indent": match.group(1),
        })

    if not functions_to_doc:
        return None

    logger.info(f"Found {len(functions_to_doc)} undocumented TypeScript functions")

    client = get_client()
    model = config.get("model", "claude-sonnet-4-6")

    insertions = []

    for func in functions_to_doc:
        prompt = f"Generate a JSDoc comment for this TypeScript function:\n\n```typescript\n{func['source']}\n```"

        try:
            response = client.messages.create(
                model=model,
                max_tokens=400,
                system=DOCGEN_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            resp_text = response.content[0].text.strip()
            if resp_text.startswith("```"):
                resp_text = resp_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(resp_text)
            docstring = result.get("docstring", "")

            if docstring:
                indent = func["indent"]
                jsdoc = f"{indent}/**\n"
                for line in docstring.split("\n"):
                    jsdoc += f"{indent} * {line}\n"
                jsdoc += f"{indent} */"
                insertions.append((func["line"], jsdoc))

        except Exception as e:
            logger.warning(f"Failed to generate JSDoc: {e}")

    if not insertions:
        return None

    # insert bottom-up
    insertions.sort(key=lambda x: x[0], reverse=True)
    for line_num, jsdoc in insertions:
        lines.insert(line_num, jsdoc)

    return "\n".join(lines)
