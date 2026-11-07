"""Command-line interface for local accounting workpapers."""
import argparse
import json
import re
from pathlib import Path

from .core import ArtifactStore, Blocked, canonical, digest
from .journal import Journal
from .planning import validate_plan
from .public_batch import PublicBatchMCP, PublicBatchPlanner

KINDS = {"reconcile": "BANK_RECONCILIATION", "journal": "GENERAL_JOURNALS"}
MAX_INPUT_BYTES = 32 * 1024 * 1024


def load_input(path):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise Blocked("DUPLICATE_INPUT_KEY", key)
            obj[key] = value
        return obj

    with path.open("rb") as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise Blocked("INPUT_LIMIT")
    data = json.loads(raw, object_pairs_hook=unique)
    if type(data) is not dict:
        raise Blocked("INVALID_SCHEMA", "object expected")
    return data


def read_receipt(journal, store, binding):
    events = journal.read()
    if len(events) != 2 or events[1]["kind"] != "COMPLETED":
        raise Blocked("INCOMPLETE_RECEIPT")
    if any(event["cohort_key"] != digest(binding) or event["input_sha"] != binding["input_sha256"]
           for event in events):
        raise Blocked("RECEIPT_BINDING")
    artifact = events[1]["result_sha"]
    report = store.get(artifact)
    if report["input_sha256"] != binding["input_sha256"] or report["request_id"] != binding["request_id"]:
        raise Blocked("RECEIPT_BINDING")
    return {"artifact_sha256": artifact, "workpaper": report}


def run_batch(kind, data, directory, request_id):
    if not re.fullmatch("[A-Za-z0-9_-]{1,64}", request_id):
        raise Blocked("REQUEST_ID")
    gateway = PublicBatchMCP(kind, data)
    plan = PublicBatchPlanner().plan(gateway)
    order = validate_plan(plan, gateway.page_ids)
    input_hash = digest(gateway.data)
    binding = {"realm": "TEST_ONLY", "kind": kind, "request_id": request_id, "input_sha256": input_hash}
    try:
        directory.mkdir()
    except FileExistsError:
        journal = Journal(directory / "receipts.sqlite", binding)
        return read_receipt(journal, ArtifactStore(directory / "artifacts"), binding)

    journal = Journal(directory / "receipts.sqlite", binding, create=True)
    store = ArtifactStore(directory / "artifacts")
    key = digest(binding)
    journal.append("ADMITTED", 1, input_hash, key)
    tasks = {task.id: task for task in plan.tasks}
    trace = []
    for task_id in order:
        result = gateway.call(tasks[task_id].tool)
        trace.append({"task": task_id, "tool": tasks[task_id].tool.name, "result_sha256": digest(result)})
    report = {"schema": "LEDGERSPEC_OFFLINE_WORKPAPER_V1", "kind": kind, "request_id": request_id,
              "input_sha256": input_hash, "page_ids": gateway.page_ids, "trace": trace, "output": result}
    artifact = store.put(report)
    if canonical(store.get(artifact)) != canonical(report):
        raise Blocked("ARTIFACT_READBACK")
    journal.append("COMPLETED", 1, input_hash, key, artifact)
    return read_receipt(journal, store, binding)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=KINDS)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--request-id", required=True)
    args = parser.parse_args()
    try:
        receipt = run_batch(KINDS[args.operation], load_input(args.input), args.output, args.request_id)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"Rejected: {exc}\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
