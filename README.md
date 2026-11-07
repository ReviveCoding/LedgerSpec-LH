# LedgerSpec-LH

Deterministic bank reconciliation and double-entry journal validation for local, offline accounting review.

LedgerSpec-LH validates transaction batches, proposes bank-to-ledger relationships, preserves ambiguous items for review, and generates content-addressed workpapers. All examples use synthetic data. The runtime has no bank or posting connection.

## Run locally

Requires Python 3.11 or newer.

    python -m pip install .
    ledgerspec reconcile examples/reconciliation.json --output example-run --request-id example
    ledgerspec journal examples/journal.json --output journal-run --request-id journal
    python -m unittest discover -s tests -v

Use a distinct output directory for each request. An exact repeat against a completed directory returns the verified receipt. A changed request or incomplete receipt fails closed. Reconciliation output contains proposed relationships and unresolved records.

## Architecture

| Stage | Implementation |
|---|---|
| Intake | Strict JSON decoding, duplicate-key rejection, row limits, and cent-level amounts |
| Execution | Typed tasks, validated dependency graph, and bounded 100-row pages |
| Reconciliation | Account and currency partitions, date-window search, reference evidence, and global ambiguity checks |
| Journal validation | Per-currency debit and credit checks with per-entry decisions |
| Evidence | SHA-256 workpapers, readback verification, and a local SQLite receipt journal |

[Evaluation and scope](docs/evaluation.md)
