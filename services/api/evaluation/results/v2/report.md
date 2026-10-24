### Model: qwen2.5:3b-instruct-q4_K_M

| field | tampilan | TP | FP | FN | precision | recall |
|---|---|---|---|---|---|---|
| **obat** | mentah | 5 | 4 | 4 | 0.56 | 0.56 |
| **obat** | lolos | 5 | 4 | 4 | 0.56 | 0.56 |
| **obat** | diterima | 5 | 4 | 4 | 0.56 | 0.56 |
| **dosis** | mentah | 5 | 0 | 1 | 1.00 | 0.83 |
| **dosis** | lolos | 5 | 0 | 1 | 1.00 | 0.83 |
| **dosis** | diterima | 5 | 0 | 1 | 1.00 | 0.83 |
| **alergi** | mentah | 1 | 2 | 2 | 0.33 | 0.33 |
| **alergi** | lolos | 1 | 2 | 2 | 0.33 | 0.33 |
| **alergi** | diterima | 1 | 2 | 2 | 0.33 | 0.33 |
| **diagnosis** | mentah | 4 | 0 | 3 | 1.00 | 0.57 |
| **diagnosis** | lolos | 4 | 0 | 3 | 1.00 | 0.57 |
| **diagnosis** | diterima | 3 | 0 | 4 | 1.00 | 0.43 |

- kasus: 10  | JSON gagal: 0  | kualitas rendah: 0
- tingkat bukti ditolak validator: 0.00%  | ditandai: 9.09%
- tingkat omisi vs gold (tampilan lolos): 0.70  | rata-rata 'terlewat'/kasus: 1.80
