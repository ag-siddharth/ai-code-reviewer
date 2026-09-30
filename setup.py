from setuptools import setup, find_packages

setup(
    name="ai-code-reviewer",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "anthropic>=0.39.0",
        "click>=8.1",
        "pyyaml>=6.0",
        "python-dotenv>=1.0",
        "rich>=13.0",
    ],
    entry_points={
        "console_scripts": [
            "codereview=src.cli:cli",
        ],
    },
    python_requires=">=3.9",
)
