"""Public Actions observations preserve native step and annotation evidence."""
import json

import pytest

from tools.observe_actions import ActionsPage, _run_link, details_from_page, observe_run, runs_from_page


RUN = "https://github.com/example/studio/actions/runs/42"
MATRIX = "/example/studio/actions/runs/42/graph/matrix/encoded=?attempt=1&expanded=true"
JOB = "/example/studio/actions/runs/42/job/73"


def test_existing_workflow_list_contract_is_preserved():
    source = '<script type="application/json">' + json.dumps({"payload": {"allWorkflowRunsRoute": {
        "workflowRuns": [{"id": 42, "runUrl": RUN, "title": "Native build", "branch": {"name": "development"},
                          "state": "failure", "description": {"linkUrl": "commit"},
                          "workflowFilePath": ".github/workflows/native.yml", "timing": {"duration": 10}}]
    }}}) + '</script>'
    assert runs_from_page(source) == [{"id": 42, "url": RUN, "title": "Native build", "branch": "development",
                                       "state": "failure", "commit_url": "commit",
                                       "workflow": ".github/workflows/native.yml", "timing": {"duration": 10}}]
    with pytest.raises(ValueError, match="did not expose"):
        runs_from_page("<html>Sign in</html>")


def test_steps_and_errors_do_not_turn_continue_on_error_into_test_success():
    source = '''<check-steps data-job-status="completed">
      <check-step data-number="7" data-name="Source tests" data-conclusion="success"></check-step>
      <check-step data-number="11" data-name="Build Windows archive" data-conclusion="skipped"></check-step>
    </check-steps><annotation-message><svg class="color-fg-danger"></svg>
      <a><strong>Publish source test details</strong></a>
      <div data-target="annotation-message.annotationContainer"><div>test_worker: failed &lt; completed
        <a href="https://example.invalid">details</a></div></div>
      <button>Show more</button><button>Show less</button></annotation-message>
    <a>Sign in to view logs</a>'''
    result = details_from_page(source)
    assert result["job_status"] == "completed"
    assert result["log_access"] == "sign-in-required"
    assert result["steps"][0]["conclusion"] == "success"
    assert result["steps"][1]["conclusion"] == "skipped"
    assert result["annotations"] == [{"severity": "error", "step": "Publish source test details",
                                      "message": "test_worker: failed < completed\n        details"}]


def test_observe_run_expands_normal_public_matrix_then_reads_public_job_page():
    main = '<button data-update-url="' + MATRIX.replace('&', '&amp;') + '"></button>'
    matrix = '<streaming-graph-job data-concluded="true"><a href="' + JOB + '">'
    matrix += '<svg aria-label="failed: "></svg><span data-target="streaming-graph-job.name">Windows x64</span>'
    matrix += '</a></streaming-graph-job>'
    job = '<check-steps data-job-status="completed"><check-step data-name="Package and smoke" data-conclusion="success"/></check-steps>'
    calls = []

    def fetch(url, **kwargs):
        calls.append((url, kwargs))
        return {RUN: main, "https://github.com" + MATRIX: matrix, "https://github.com" + JOB: job}[url]

    result = observe_run("example/studio", 42, fetch=fetch)
    assert calls == [(RUN, {}), ("https://github.com" + MATRIX, {"referer": RUN}), ("https://github.com" + JOB, {})]
    assert result["observation_errors"] == []
    observed = result["jobs"][0]
    assert observed["url"] == "https://github.com" + JOB
    assert observed["id"] == 73 and observed["name"] == "Windows x64"
    assert observed["status_label"] == "failed" and observed["concluded"] is True
    assert observed["steps"][0]["conclusion"] == "success"  # Overall gate failure must not erase native build success.


@pytest.mark.parametrize("href", [
    "https://api.github.com/example/studio/actions/runs/42/job/73",
    "https://other.invalid/example/studio/actions/runs/42/job/73",
    "/example/other/actions/runs/42/job/73", "/example/studio/actions/runs/43/job/73",
    "/example/studio/actions/runs/42/job/73/../../secrets", "//github.com@other.invalid/job/73",
])
def test_public_links_cannot_change_host_repository_or_run(href):
    with pytest.raises(ValueError, match="Unexpected"):
        _run_link(href, RUN, "job")


def test_unavailable_job_is_recorded_as_observation_error_without_fake_results():
    source = '<streaming-graph-job data-concluded="false"><a href="' + JOB + '">'
    source += '<svg aria-label="currently running: "></svg></a></streaming-graph-job>'

    def fetch(url, **kwargs):
        if url == RUN:
            return source
        raise OSError("Public job page unavailable")

    result = observe_run("example/studio", 42, fetch=fetch)
    assert result["jobs"][0]["status_label"] == "currently running"
    assert "steps" not in result["jobs"][0]
    assert result["observation_errors"] == [{"url": "https://github.com" + JOB,
                                             "error": "Public job page unavailable"}]


def test_public_artifact_metadata_is_preserved_without_claiming_download_verification():
    source = '''<table><tr data-artifact-id="123"><td><span>validation-Windows</span></td>
      <td>34.4 KB</td><td><code id="artifact-123-hash">sha256:abc</code></td></tr></table>'''
    result = observe_run("example/studio", 42, fetch=lambda url: source)
    assert result["artifacts"] == [{"id": 123, "name": "validation-Windows", "size": "34.4 KB",
                                    "digest": "sha256:abc", "url": RUN + "/artifacts/123",
                                    "download_verified": False}]
    assert not result["jobs"]
