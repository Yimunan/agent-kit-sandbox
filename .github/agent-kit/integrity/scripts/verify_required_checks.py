#!/usr/bin/env python3
"""Require a real, pinned success for every required check (P2.9).

Usage: verify_required_checks.py --ruleset FILE --sha SHA
           (--saved FILE | --repo OWNER/NAME [--wait SECONDS])
           [--exclude CONTEXT ...] [--output FILE]

GitHub's own required-check gate accepts skipped and neutral results. This
verifier does not: only status completed with conclusion success passes.

Rules (all block):
  CHK001  a required check ended, or is still, in anything but success
  CHK002  a required check has no run from its pinned app on this commit
  CHK003  another app reported under a required check's name
"""
import argparse
import re
import sys
import time

from common import GitHub, ToolError, emit, finding, load_json, load_required_checks, quote, run


def extract_runs(data):
    """Accept an API response, a bare list of runs, or a list of response pages."""
    if isinstance(data, dict):
        data = data.get("check_runs")
    if not isinstance(data, list):
        raise ToolError("expected a check_runs list")
    runs = []
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("check_runs"), list):
            runs.extend(item["check_runs"])
        elif isinstance(item, dict) and "name" in item:
            runs.append(item)
        else:
            raise ToolError("malformed check run entry: %r" % (item,))
    return runs


def fetch_runs(github, repo, sha):
    runs, page = [], 1
    while True:
        body = github.get_json(
            "/repos/%s/commits/%s/check-runs?filter=latest&per_page=100&page=%d" % (repo, quote(sha), page)
        )
        if not isinstance(body, dict) or not isinstance(body.get("check_runs"), list):
            raise ToolError("unexpected check-runs response")
        runs.extend(body["check_runs"])
        total = body.get("total_count")
        if not isinstance(total, int):
            raise ToolError("check-runs response has no total_count")
        if len(runs) >= total:
            return runs
        if not body["check_runs"]:
            raise ToolError("check-runs ended early: %d of %d" % (len(runs), total))
        page += 1


def app_id(check_run):
    app = check_run.get("app")
    return app.get("id") if isinstance(app, dict) else None


def passed(check_run):
    return check_run.get("status") == "completed" and check_run.get("conclusion") == "success"


def on_commit(runs, sha):
    return [r for r in runs if r.get("head_sha") == sha]


def evaluate(required, runs, sha, source):
    found = []
    runs = on_commit(runs, sha)
    for context, app in sorted(required.items()):
        named = [r for r in runs if r.get("name") == context]
        pinned = [r for r in named if app_id(r) == app]
        for run_ in named:
            if app_id(run_) != app:
                found.append(finding(
                    "CHK003", "block", source, 0,
                    "App %s reported '%s', which is pinned to app %d." % (app_id(run_), context, app),
                ))
        if not pinned:
            found.append(finding(
                "CHK002", "block", source, 0,
                "Required check '%s' has no run from app %d on %s." % (context, app, sha),
            ))
        for run_ in pinned:
            if not passed(run_):
                state = run_.get("conclusion") or run_.get("status") or "unknown"
                found.append(finding(
                    "CHK001", "block", source, 0,
                    "Required check '%s' is '%s'; only success passes." % (context, state),
                ))
    return found


def still_pending(required, runs, sha):
    runs = on_commit(runs, sha)
    for context, app in required.items():
        pinned = [r for r in runs if r.get("name") == context and app_id(r) == app]
        if not pinned or any(r.get("status") != "completed" for r in pinned):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ruleset", action="append", required=True)
    parser.add_argument("--sha", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--saved")
    source.add_argument("--repo")
    parser.add_argument("--wait", type=int, default=0, help="live only: seconds to wait for pending checks")
    parser.add_argument("--poll-interval", type=float, default=20)
    parser.add_argument("--exclude", action="append", default=[], help="skip this context, for the verifier's own job")
    parser.add_argument("--output")
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        raise ToolError("--sha must be a full commit SHA")
    required = load_required_checks(args.ruleset)
    required = {c: a for c, a in required.items() if c not in args.exclude}
    if not required:
        raise ToolError("no required checks left to verify")

    if args.saved:
        return emit(evaluate(required, extract_runs(load_json(args.saved)), args.sha, args.saved), args.output)

    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
        raise ToolError("--repo must be owner/name")
    github = GitHub()
    deadline = time.monotonic() + args.wait
    while True:
        runs = fetch_runs(github, args.repo, args.sha)
        if not still_pending(required, runs, args.sha) or time.monotonic() >= deadline:
            return emit(evaluate(required, runs, args.sha, "%s@%s" % (args.repo, args.sha)), args.output)
        print("waiting for required checks...", file=sys.stderr)
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    run(main)
