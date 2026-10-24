### Model: qwen2.5:7b-instruct-q4_K_M

| field | tampilan | TP | FP | FN | precision | recall |
|---|---|---|---|---|---|---|
| **obat** | mentah | 8 | 2 | 1 | 0.80 | 0.89 |
| **obat** | lolos | 8 | 2 | 1 | 0.80 | 0.89 |
| **obat** | diterima | 8 | 1 | 1 | 0.89 | 0.89 |
| **dosis** | mentah | 6 | 0 | 0 | 1.00 | 1.00 |
| **dosis** | lolos | 6 | 0 | 0 | 1.00 | 1.00 |
| **dosis** | diterima | 6 | 0 | 0 | 1.00 | 1.00 |
| **alergi** | mentah | 2 | 1 | 1 | 0.67 | 0.67 |
| **alergi** | lolos | 2 | 1 | 1 | 0.67 | 0.67 |
| **alergi** | diterima | 2 | 0 | 1 | 1.00 | 0.67 |
| **diagnosis** | mentah | 4 | 0 | 3 | 1.00 | 0.57 |
| **diagnosis** | lolos | 4 | 0 | 3 | 1.00 | 0.57 |
| **diagnosis** | diterima | 3 | 0 | 4 | 1.00 | 0.43 |

- kasus: 10  | JSON gagal: 0  | kualitas rendah: 0
- tingkat bukti ditolak validator: 0.00%  | ditandai: 8.33%
- tingkat omisi vs gold (tampilan lolos): 0.40  | rata-rata 'terlewat'/kasus: 1.40
