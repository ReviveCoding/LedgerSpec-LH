# Evaluation and scope

The published engine and journal validator come from the offline R5 candidate. These measurements used that candidate's original batch wrapper. The portable CLI in this repository has a separate [CI test matrix](https://github.com/ReviveCoding/LedgerSpec-LH/actions/workflows/ci.yml) with synthetic inputs.

| Evaluation | R3 baseline | R5 candidate |
|---|---:|---:|
| Bank Feed and Ledger Reconciliation Practice Dataset | 177/198 correct links, F1 94.40% | 177/198 correct links, F1 94.40% |
| RecBench USD payout-to-bank subset | 334/447 correct links, F1 85.53% | 415/447 correct links, F1 96.29% |
| Synthetic 1,000-row case | 0/454 correct links | 454/454 correct links |
| Synthetic 1,000-row workflow median | 14.559 s | 1.029 s |
| Public journal cent discrepancies | 240/240 exact | 240/240 exact |

The correct-link ratios use labeled links as their denominator. F1 scores are computed on pairs. Observed false automatic matches were zero in the evaluated samples.

R5 recovered 81 previously missed links on the same RecBench subset and left 32 conflicting links unresolved. The subset covered USD payouts and bank rows. This was a regression evaluation following analysis of the original errors. The timing comparison used five fresh processes per version on one Windows workstation.

## Data and scope

The public datasets are available from their publishers. The repository includes synthetic examples for local testing.

- [Bank Feed and Ledger Reconciliation Practice Dataset](https://databasesample.com/datasets/bank-feed-and-ledger-reconciliation-practice-dataset)
- [RecBench](https://huggingface.co/datasets/end-close/recbench)

The workpapers are proposals for offline review. Deployment, production custody, three-way reconciliation, and financial posting are outside the release scope.

[Run the examples](usage.md)
