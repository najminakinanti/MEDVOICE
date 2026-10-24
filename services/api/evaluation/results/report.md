### Model: qwen2.5:3b-instruct-q4_K_M

| field | tampilan | TP | FP | FN | precision | recall |
|---|---|---|---|---|---|---|
| **obat** | mentah | 0 | 8 | 9 | 0.00 | 0.00 |
| **obat** | lolos | 0 | 0 | 9 |   -  | 0.00 |
| **obat** | diterima | 0 | 0 | 9 |   -  | 0.00 |
| **dosis** | mentah | 0 | 5 | 6 | 0.00 | 0.00 |
| **dosis** | lolos | 0 | 0 | 6 |   -  | 0.00 |
| **dosis** | diterima | 0 | 0 | 6 |   -  | 0.00 |
| **alergi** | mentah | 0 | 3 | 3 | 0.00 | 0.00 |
| **alergi** | lolos | 0 | 0 | 3 |   -  | 0.00 |
| **alergi** | diterima | 0 | 0 | 3 |   -  | 0.00 |
| **diagnosis** | mentah | 2 | 3 | 5 | 0.40 | 0.29 |
| **diagnosis** | lolos | 0 | 0 | 7 |   -  | 0.00 |
| **diagnosis** | diterima | 0 | 0 | 7 |   -  | 0.00 |

- kasus: 10  | JSON gagal: 0  | kualitas rendah: 7
- tingkat bukti ditolak validator: 100.00%  | ditandai: 0.00%
- tingkat omisi vs gold (tampilan lolos): 1.00  | rata-rata 'terlewat'/kasus: 5.40
