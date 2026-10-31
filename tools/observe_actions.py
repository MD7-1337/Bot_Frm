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


class ActionsPage(HTMLParser):
    """Read public matrix, step attributes and annotations, without log requests."""

    def __init__(self):
        super().__init__()
        self.matrix_links = []
        self.jobs = []
        self.steps = []
        self.annotations = []
        self.artifacts = []
        self.job_status = None
        self.log_access = "not-assessed"
        self._job = None
        self._annotation = None
        self._artifact = None
        self._artifact_column = 0
        self._captures = []

    def _capture(self, field, tag, destination):
        self._captures.append({"field": field, "tag": tag, "depth": 1,
                               "parts": [], "destination": destination})

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for capture in self._captures:
            if capture["tag"] == tag:
                capture["depth"] += 1
        matrix_link = attrs.get("data-update-url", "")
        if "/graph/matrix/" in matrix_link:
            self.matrix_links.append(matrix_link)
        if tag == "tr" and attrs.get("data-artifact-id", "").isdigit():
            self._artifact = {"id": int(attrs["data-artifact-id"])}
            self._artifact_column = 0
        elif self._artifact is not None:
            if tag == "td":
                self._artifact_column += 1
                if self._artifact_column <= 2:
                    self._capture("name" if self._artifact_column == 1 else "size", tag, self._artifact)
            elif tag == "code" and attrs.get("id", "").endswith("-hash"):
                self._capture("digest", tag, self._artifact)
        if tag == "streaming-graph-job":
            self._job = {"concluded": attrs.get("data-concluded") == "true"}
        elif self._job is not None:
            if tag == "a" and re.search(r"/actions/runs/\d+/job/\d+(?:\?|$)", attrs.get("href", "")):
                self._job["url"] = attrs["href"]
            elif tag == "svg" and attrs.get("aria-label"):
                self._job["status_label"] = attrs["aria-label"].strip().rstrip(":")
            if attrs.get("data-target") == "streaming-graph-job.name":
                self._capture("name", tag, self._job)
        if tag == "check-steps":
            self.job_status = attrs.get("data-job-status")
        elif tag == "check-step":
            self.steps.append({key.replace("-", "_"): attrs.get("data-" + key)
                               for key in ("number", "name", "conclusion", "started-at", "completed-at")})
        elif tag == "annotation-message":
            self._annotation = {"severity": "unknown", "step": "", "message": ""}
        elif self._annotation is not None:
            if tag == "svg":
                classes = attrs.get("class", "").split()
                if "color-fg-danger" in classes:
                    self._annotation["severity"] = "error"
                elif "color-fg-attention" in classes:
                    self._annotation["severity"] = "warning"
            if tag == "strong":
                self._capture("step", tag, self._annotation)
            elif attrs.get("data-target") == "annotation-message.annotationContainer":
                self._capture("message", tag, self._annotation)

    def handle_endtag(self, tag):
        for capture in self._captures[:]:
            if capture["tag"] == tag:
                capture["depth"] -= 1
                if capture["depth"] == 0:
                    capture["destination"][capture["field"]] = "".join(capture["parts"]).strip()
                    self._captures.remove(capture)
        if tag == "streaming-graph-job" and self._job is not None:
            if self._job.get("url"):
                self.jobs.append(self._job)
            self._job = None
        elif tag == "annotation-message" and self._annotation is not None:
            self.annotations.append(self._annotation)
            self._annotation = None
        elif tag == "tr" and self._artifact is not None:
            self.artifacts.append(self._artifact)
            self._artifact = None

    def handle_data(self, value):
        for capture in self._captures:
            capture["parts"].append(value)
        if "Sign in to view logs" in value:
            self.log_access = "sign-in-required"


def details_from_page(source: str):
    page = ActionsPage()
    page.feed(source)
    return {"job_status": page.job_status, "steps": page.steps,
            "annotations": page.annotations, "log_access": page.log_access}


def _run_link(href: str, run_url: str, kind: str):
    """Only follow expected public links belonging to this repository and run."""
    url = urllib.parse.urljoin(run_url, href)
    parsed = urllib.parse.urlsplit(url)
    prefix = urllib.parse.urlsplit(run_url).path
    suffix = r"/job/\d+" if kind == "job" else r"/graph/matrix/[A-Za-z0-9_=+-]+"
    if (parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.fragment
            or not re.fullmatch(re.escape(prefix) + suffix, parsed.path)):
        raise ValueError("Unexpected public Actions " + kind + " link")
    return url


def fetch_public_page(url: str, *, referer: str | None = None):
    headers = {"Cache-Control": "no-cache"}
    if referer:
        # These are the same HTML fragments requested by the normal public UI.
        headers.update({"X-Requested-With": "XMLHttpRequest", "Accept": "text/html", "Referer": referer})
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        if urllib.parse.urlsplit(response.url).netloc != "github.com":
            raise ValueError("Public Actions page redirected outside github.com")
        return response.read(3_000_000).decode("utf-8")


def observe_run(repository: str, run_id: int, *, fetch=fetch_public_page):
    run_url = f"https://github.com/{repository}/actions/runs/{run_id}"
    page = ActionsPage()
    page.feed(fetch(run_url))
    jobs = list(page.jobs)
    artifacts = [{**artifact, "url": f"{run_url}/artifacts/{artifact['id']}", "download_verified": False}
                 for artifact in page.artifacts]
    report = {"url": run_url, "id": run_id, "matrix_sources": [], "jobs": [],
              "artifacts": artifacts, "observation_errors": []}
    for href in dict.fromkeys(page.matrix_links):
        url = _run_link(href, run_url, "matrix")
        report["matrix_sources"].append(url)
        try:
            matrix = ActionsPage()
            matrix.feed(fetch(url, referer=run_url))
            jobs.extend(matrix.jobs)
        except (OSError, ValueError) as error:
            report["observation_errors"].append({"url": url, "error": str(error)})
    seen = set()
    for job in jobs:
        url = _run_link(job["url"], run_url, "job")
        if url in seen:
            continue
        seen.add(url)
        job["url"] = url
        job["id"] = int(urllib.parse.urlsplit(url).path.rsplit("/", 1)[1])
        try:
            job.update(details_from_page(fetch(url)))
        except (OSError, ValueError) as error:
            report["observation_errors"].append({"url": url, "error": str(error)})
        report["jobs"].append(job)
    if not jobs:
        report["observation_errors"].append({"url": run_url, "error": "Public page did not expose matrix jobs"})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="MD7-1337/Bot_Frm")
    parser.add_argument("--branch", default="feat/cross-platform-alpha-release")
    parser.add_argument("--run-id", type=int, help="Inspect this run's public matrix, step results and annotations")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("Repository must be owner/name")
    if args.run_id is not None and args.run_id <= 0:
        parser.error("Run ID must be positive")
    report = {"observed_utc": datetime.now(timezone.utc).isoformat(),
              "method": "public GitHub webpage; no authenticated log/artifact access"}
    if args.run_id:
        report["run"] = observe_run(args.repository, args.run_id)
        report["source"] = report["run"]["url"]
    else:
        url = "https://github.com/" + args.repository + "/actions?" + urllib.parse.urlencode({"query": "branch:" + args.branch})
        report.update({"source": url, "runs": runs_from_page(fetch_public_page(url))})
    data = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data + "\n", encoding="utf-8")
    print(data)


if __name__ == "__main__":
    main()
