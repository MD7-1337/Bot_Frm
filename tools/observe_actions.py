"""Observe public GitHub Actions pages without requiring API credentials.

Reads the normal github.com webpage only. Private logs/artifacts still require
the user's GitHub login. This does not replace an authenticated API client.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.current = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type") == "application/json":
            self.capture, self.current = True, []

    def handle_endtag(self, tag):
        if tag == "script" and self.capture:
            self.capture = False
            try:
                self.documents.append(json.loads("".join(self.current)))
            except json.JSONDecodeError:
                pass

    def handle_data(self, value):
        if self.capture:
            self.current.append(value)


def runs_from_page(source: str):
    page = Page()
    page.feed(source)
    for document in page.documents:
        route = document.get("payload", {}).get("allWorkflowRunsRoute") if isinstance(document, dict) else None
        if route is not None:
            return [{"id": run["id"], "url": run["runUrl"], "title": run.get("title"),
                     "branch": run.get("branch", {}).get("name"), "state": run.get("state"),
                     "commit_url": run.get("description", {}).get("linkUrl"),
                     "workflow": run.get("workflowFilePath"), "timing": run.get("timing")}
                    for run in route["workflowRuns"]]
    raise ValueError("Public Actions page did not expose workflow results; sign in or inspect the page manually")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="MD7-1337/Bot_Frm")
    parser.add_argument("--branch", default="feat/cross-platform-alpha-release")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("Repository must be owner/name")
    url = "https://github.com/" + args.repository + "/actions?" + urllib.parse.urlencode({"query": "branch:" + args.branch})
    with urllib.request.urlopen(url, timeout=30) as response:
        source = response.read(3_000_000).decode("utf-8")
    report = {"observed_utc": datetime.now(timezone.utc).isoformat(), "source": url,
              "method": "public GitHub webpage; no authenticated log/artifact access",
              "runs": runs_from_page(source)}
    data = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data + "\n", encoding="utf-8")
    print(data)


if __name__ == "__main__":
    main()
