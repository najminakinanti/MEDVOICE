### Model: replay:qwen2.5_3b-instruct-q4_K_M_raw

| field | tampilan | TP | FP | FN | precision | recall |
|---|---|---|---|---|---|---|
| **obat** | mentah | 0 | 8 | 9 | 0.00 | 0.00 |
| **obat** | lolos | 0 | 8 | 9 | 0.00 | 0.00 |
| **obat** | diterima | 0 | 7 | 9 | 0.00 | 0.00 |
| **dosis** | mentah | 0 | 5 | 6 | 0.00 | 0.00 |
| **dosis** | lolos | 0 | 5 | 6 | 0.00 | 0.00 |
| **dosis** | diterima | 0 | 4 | 6 | 0.00 | 0.00 |
| **alergi** | mentah | 0 | 3 | 3 | 0.00 | 0.00 |
| **alergi** | lolos | 0 | 3 | 3 | 0.00 | 0.00 |
| **alergi** | diterima | 0 | 2 | 3 | 0.00 | 0.00 |
| **diagnosis** | mentah | 2 | 3 | 5 | 0.40 | 0.29 |
| **diagnosis** | lolos | 2 | 3 | 5 | 0.40 | 0.29 |
| **diagnosis** | diterima | 1 | 1 | 6 | 0.50 | 0.14 |

- kasus: 10  | JSON gagal: 0  | kualitas rendah: 0
- tingkat bukti ditolak validator: 0.00%  | ditandai: 20.00%
- tingkat omisi vs gold (tampilan lolos): 0.93  | rata-rata 'terlewat'/kasus: 2.00
