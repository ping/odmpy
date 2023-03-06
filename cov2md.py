import json
import os

#
# Simple script to convert coverage.json into markdown for display as GitHub Actions job summary
#


def _escape(txt: str) -> str:
    return txt.replace("_", r"\_")


def convert(cover_json_filepath, markdown_filepath):
    with open(cover_json_filepath, "r", encoding="utf-8") as f:
        results = json.load(f)

    job_summary = ""
    job_summary += f'\nTotal Coverage: __{results.get("totals", {}).get("percent_covered", 0):.1f}%__ \n\n'
    job_summary += """| Name | Stmts | Miss | Cover |
| :--- | ---: | ---: | ---: |
"""
    for k, v in results.get("files", {}).items():
        summary = v.get("summary", {})
        job_summary += f'| {_escape(k)} | {summary.get("num_statements", 0)} | {summary.get("missing_lines", 0)} | {summary.get("percent_covered", 0):.1f}% |\n'

    with open(markdown_filepath, "w", encoding="utf-8") as f:
        f.write(job_summary)
    try:
        os.remove(cover_json_filepath)
    except:  # noqa: E722, pylint: disable=bare-except
        pass


if __name__ == "__main__":
    convert("coverage.json", "coverage.md")
