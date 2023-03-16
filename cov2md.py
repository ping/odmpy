import json
from pathlib import Path

#
# Simple script to convert coverage.json into markdown for display as GitHub Actions job summary
#


def _escape(txt: str) -> str:
    return txt.replace("_", r"\_")


def convert(cover_json_filepath, markdown_filepath):
    cover_json_path = Path(cover_json_filepath)
    markdown_path = Path(markdown_filepath)
    with cover_json_path.open("r", encoding="utf-8") as f:
        results = json.load(f)

    job_summary = ""
    job_summary += f'\nTotal Coverage: __{results.get("totals", {}).get("percent_covered", 0):.1f}%__ \n\n'
    job_summary += """| Name | Stmts | Miss | Cover |
| :--- | ---: | ---: | ---: |
"""
    for k, v in results.get("files", {}).items():
        summary = v.get("summary", {})
        job_summary += f'| {_escape(k)} | {summary.get("num_statements", 0)} | {summary.get("missing_lines", 0)} | {summary.get("percent_covered", 0):.1f}% |\n'

    with markdown_path.open("w", encoding="utf-8") as f:
        f.write(job_summary)
    try:
        cover_json_path.unlink()
    except:  # noqa: E722, pylint: disable=bare-except
        pass


if __name__ == "__main__":
    convert("coverage.json", "coverage.md")
