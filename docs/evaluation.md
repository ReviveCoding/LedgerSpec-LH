# Evaluation and scope

The published reconciliation engine and journal validator are sourced from the offline R5 candidate. The table records prior measurements of that candidate, including its original batch wrapper. The portable wrapper in this repository is tested separately in CI with synthetic fixtures.

| Evaluation | Prior baseline | R5 candidate |
|---|---:|---:|
| Public bank-reconciliation fixture | 177/198, F1 94.40% | 177/198, F1 94.40% |
| RecBench USD payout-to-bank subset | 334/447, F1 85.53% | 415/447, F1 96.29% |
| Synthetic 1,000-row case | 0/454 correct links | 454/454 correct links |
| Synthetic 1,000-row workflow median | 14.559 s | 1.029 s |
| Public journal cent discrepancies | 240/240 exact | 240/240 exact |

Observed false automatic matches were zero in these samples. The candidate recovered 81 previously missed links on the same RecBench subset and left 32 conflicting links unresolved. This was a regression evaluation after examining the original errors. The timing comparison used five fresh processes per version on one Windows workstation.

The dataset inputs and answer keys are hosted separately by their publishers. This repository includes original synthetic examples for local tests.

- [Bank Feed and Ledger Reconciliation Practice Dataset](https://databasesample.com/datasets/bank-feed-and-ledger-reconciliation-practice-dataset)
- [RecBench](https://huggingface.co/datasets/end-close/recbench)

The workpapers are proposals for offline review. Deployment, production custody, three-way reconciliation, and financial posting are outside the release scope.
