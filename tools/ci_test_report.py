"""Bounded JUnit results in Actions summaries and visible annotations."""
from __future__ import annotations
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


def escape(value):
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def publish(path: Path):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if not cases:
        raise ValueError("JUnit report contains no executed test cases")
    failures = [(case, detail) for case in cases for detail in list(case)
                if detail.tag in ("failure", "error")]
    skipped = sum(case.find("skipped") is not None for case in cases)
    summary = ["## Source regression results", "",
               f"{len(cases)-len(failures)-skipped} passed, {len(failures)} failed/error, {skipped} skipped.", ""]
    print(f"::notice title=Source regression totals::{escape(summary[2])}")
    for case, detail in failures[:20]:
        identity = f"{case.get('classname', '')}::{case.get('name', '')}"
        message = (detail.get("message") or detail.text or "Failed")[:1500]
        print(f"::error title=Regression failure::{escape(identity + ': ' + message)}")
        summary.append(f"- `{identity.replace('`', '')}`: {message.replace('`', '')}")
    if target := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(target).open("a", encoding="utf-8") as output:
            output.write("\n".join(summary) + "\n")
    return len(failures)


if __name__ == "__main__":
    raise SystemExit(1 if publish(Path(sys.argv[1])) else 0)
