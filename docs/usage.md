# Usage

Start with the [quick start](../README.md#quick-start). Both commands accept a JSON object and print a receipt to standard output. Use one output directory per request and create its parent before invoking the CLI.

## Input formats

| Operation | Top-level fields | Example |
|---|---|---|
| `reconcile` | `ledger_entries`, `bank_lines` | [Reconciliation input](../examples/reconciliation.json) |
| `journal` | `accounts`, `journal_entries`, `journal_lines` | [Journal input](../examples/journal.json) |

| Reconciliation row | Required fields | Optional fields |
|---|---|---|
| Ledger entry | `id`, `book`, `entry_date`, `reference`, `counterparty`, `amount` | `currency`, `entered_by`, `entered_at` |
| Bank line | `id`, `account`, `posted_date`, `narrative`, `amount` | `currency` |

Use unique IDs per side, dates in `YYYY-MM-DD` format, and the same account identifier in `book` and `account` for comparable rows. Supply matching currency codes, or omit currency on both sides. Use decimal strings such as `"100.00"` for money. Floating-point values are rejected. For journals, use the example's field names and populate one positive side per line.

## Read the results

| Output field | Meaning |
|---|---|
| `workpaper.output.reconciliation.matches` | Proposed links with a decision reason and source digest |
| `workpaper.output.reconciliation.review_relationships` | Proposed review items, such as late postings and amount differences |
| `workpaper.output.reconciliation.deferred_ambiguous` | Candidate relationships held back because of duplicate or competing evidence |
| `workpaper.output.reconciliation.unmatched_bank_ids` and `unmatched_ledger_ids` | Records left unresolved after proposing matches |
| `workpaper.output.decisions` | Per-journal statuses, reasons, and exact cent differences when available |
| `workpaper.trace` | Task sequence with the tool name and result digest for each step |

In the reconciliation example, a positive `difference_cents` of 200 means ledger amount minus bank amount is 200 cents. In journal validation, `difference_cents` is debit minus credit. Balance is checked separately for every currency.

Successful CLI execution means a workpaper was produced or retrieved. Inspect the workpaper for unresolved relationships or journal decisions such as `UNBALANCED`.

## Local receipt files

| File | Contents |
|---|---|
| `receipts.sqlite` | The request binding and admission and completion events |
| `artifacts/<sha256>.json` | The workpaper addressed by its SHA-256 digest |

A repeat with the same operation, input, request ID, and output directory verifies and returns the completed receipt. Changed inputs, missing or incomplete receipts, and corrupted artifacts are rejected. Retain the directory for inspection after a failed request and use a new directory for a new request.

The CLI accepts JSON files up to 32 MiB. Reconciliation is bounded to 1,000 rows per side and a ledger-row × bank-row budget of 250,000. Journal validation accepts up to 1,000 entries, with a maximum of 128 lines per entry.

[Evaluation and release scope](evaluation.md)
