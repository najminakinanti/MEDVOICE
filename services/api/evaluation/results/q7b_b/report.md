### Model: replay:qwen2.5_7b-instruct-q4_K_M_raw

| field | tampilan | TP | FP | FN | precision | recall |
|---|---|---|---|---|---|---|
| **obat** | mentah | 7 | 2 | 2 | 0.78 | 0.78 |
| **obat** | lolos | 6 | 2 | 3 | 0.75 | 0.67 |
| **obat** | diterima | 6 | 1 | 3 | 0.86 | 0.67 |
| **dosis** | mentah | 6 | 0 | 0 | 1.00 | 1.00 |
| **dosis** | lolos | 6 | 0 | 0 | 1.00 | 1.00 |
| **dosis** | diterima | 6 | 0 | 0 | 1.00 | 1.00 |
| **alergi** | mentah | 2 | 1 | 1 | 0.67 | 0.67 |
| **alergi** | lolos | 2 | 1 | 1 | 0.67 | 0.67 |
| **alergi** | diterima | 2 | 1 | 1 | 0.67 | 0.67 |
| **diagnosis** | mentah | 5 | 0 | 2 | 1.00 | 0.71 |
| **diagnosis** | lolos | 5 | 0 | 2 | 1.00 | 0.71 |
| **diagnosis** | diterima | 3 | 0 | 4 | 1.00 | 0.43 |

- kasus: 10  | JSON gagal: 0  | kualitas rendah: 1
- tingkat bukti ditolak validator: 2.70%  | ditandai: 13.51%
- tingkat omisi vs gold (tampilan lolos): 0.45  | rata-rata 'terlewat'/kasus: 1.60
