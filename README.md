# MedVoice Engine

Engine headless voice-to-text → SOAP + usulan kode terminologi untuk RS di Indonesia. Prinsip: **LLM hanya mengusulkan, kode biasa memeriksa, dokter memutuskan**; tidak ada data masuk SIMRS tanpa approve dokter.

**Status: Fase 0-4 dikerjakan pada batas yang dijelaskan di "Status per fase" dan "Belum ada".** Baca bagian itu sebelum mempercayai apa pun.

## Mulai cepat (lokal, sudah diuji di Windows + Docker Desktop + RTX 3050 Ti 4 GB)

```bash
cp .env.example .env                 # ganti SEMUA CHANGE_ME (JWT_SECRET & API_KEY_PEPPER >= 16 karakter)
# GPU NVIDIA untuk LLM: tambahkan  -f docker-compose.gpu.yml  pada setiap `docker compose` di bawah.
# STT tetap di CPU (jangan memaksa cuda tanpa STT_BUILD_GPU=1 + docker-compose.gpu-stt.yml: Whisper akan gagal 500).
docker compose up -d postgres redis
docker compose run --rm migrate
docker compose up -d ollama stt api worker
docker compose exec ollama ollama pull qwen2.5:7b-instruct-q4_K_M      # LLM (default .env.example)
docker compose exec ollama ollama pull bge-m3                           # embedding
docker compose exec api python -m app.admin create-client rs-saya --origin http://localhost:8000
docker compose exec api python -m app.admin create-key rs-saya                                # kunci tampil SEKALI
docker compose exec -e PW=... api python -m app.admin create-doctor rs-saya dr_budi KODE_SIMRS "dr. Budi" --password-env PW
```
Buka `http://localhost:8000/ui/` (login dokter → antrean → consent → rekam dengan transkrip langsung → Selesai → hasil → SOAP → setujui & kirim). API: `/v1/docs`.

### Tanpa membangun image Docker (disarankan untuk pengembangan)
Build image `stt`/`api` lambat (unduh ulang paket pip). Cukup infrastruktur di Docker (postgres, redis, ollama: hanya start), `api` + `stt` + `worker` langsung dari `.venv`:
```powershell
.\run-local.ps1            # start semuanya; Ctrl+C berhenti.  -NoWorker: tanpa worker.  -Build: build ulang UI Vue
```
Skrip membaca `.env`, mengganti nama host Docker (`postgres`, `redis`, `ollama`, `stt`) ke `localhost`, dan memakai cache Hugging Face host untuk model Whisper. Perubahan Python aktif setelah restart skrip.

### Frontend (Vue 3 + Vite), `services/web`
UI mengikuti desain Figma "MedVoice – UI MVP" (layar admin mengikuti frame "09 · Admin"; bagian yang belum punya dasar di sistem, yaitu poli/unit, redaksi data pribadi, dan undangan email, tidak dipalsukan di UI) (login, antrean, consent, rekam + transkrip langsung, hasil: transkrip/info klinis/SOAP/kode, kirim SIMRS, riwayat, mobile rekam). Hasil build dilayani engine di `/ui/` (`services/api/app/static`, jangan diedit tangan).
```bash
cd services/web && npm install
npm run dev        # hot reload di http://localhost:5173/ui/  (meneruskan /v1 + WebSocket ke engine :8000)
npm run build      # tulis ke ../api/app/static
npm test           # uji pendeteksi ucapan (node:test)
```
UI lama (vanilla JS) disimpan di `services/web/legacy/` hanya sebagai arsip; tidak dilayani. Logo pada UI adalah pendekatan SVG; ganti dengan berkas resmi dari Figma di `src/components/Logo.vue`. Halaman **Admin RS** (menu hanya untuk `admin` dan `superadmin`):
- *Pengguna*: kelola pengguna, atur ulang kata sandi, jabatan; layar dua kolom mengikuti Figma (Pengguna | Integrasi ringkas + Data & Privasi). Superadmin melihat daftar rumah sakit + pengguna per RS.
- *Integrasi SIMRS* (3 tab): **Koneksi & pengiriman** (adapter, uji koneksi tersimpan, riwayat pengiriman + *Kirim ulang* idempoten), **Webhook** (URL, rahasia, event, log pengiriman), **Kunci API & origin**. ID dokter di SIMRS diisi lewat form *Ubah data* pengguna.
- *Pengaturan* (2 tab): **Data & Privasi** (masa simpan transkrip, teks persetujuan pasien, masa sesi login; per RS) dan **Log audit** (filter, cari, ekspor CSV aman dari injeksi rumus).
- *Sistem* (hanya superadmin): status STT/LLM/GPU, tabel terminologi, nilai bawaan server.
Login memakai email atau NIP; rumah sakit otomatis dari akun. **Tiga peran** (daftarnya ada di tabel `roles`: kode, label, cakupan `hospital`/`platform`, urutan; hak akses sebenarnya ditegakkan kode, bukan tabel; pengguna juga punya kolom `title` = jabatan bebas seperti *Dokter Umum*/*Sp.PD* untuk tampilan):
- `dokter`: hanya menu klinis (Antrean, Sesi Aktif, Riwayat, Profil); bagian *Admin RS* tidak muncul dan API admin menjawab 403.
- `admin` (admin RS): semua menu, plus *Pengguna*, *Integrasi SIMRS*, *Pengaturan* untuk **rumah sakitnya sendiri** (pengguna RS lain tak terlihat).
- `superadmin` (pengelola platform): semua menu; di *Pengguna* ada **data rumah sakit** (buat/nonaktifkan RS, batas dan kuota) dan **pengguna per rumah sakit**. Akunnya hidup di client khusus `medvoice-platform`, sehingga alur klinisnya (antrean, sesi) berjalan di client itu; sesi dokter RS lain tetap tak bisa dibuka (sesi hanya terlihat oleh pemiliknya). Superadmin pertama dibuat lewat CLI: `python -m app.admin create-superadmin "Nama" --email ... --password-env PW`. Akun pertama tiap RS dijadikan admin oleh migrasi 0007; RS baru dibuat superadmin lewat halaman *Rumah Sakit* (otomatis dengan satu admin), lalu admin RS menambah dokter di halaman *Pengguna*.

### Transkrip langsung (WebSocket)
Browser → `WS /v1/sessions/{id}/live/ws` (token dikirim sebagai pesan pertama, bukan di URL) → engine meneruskan ke `WS stt:/stream`. Detektor ucapan di browser (AudioWorklet 16 kHz) mengirim PCM16 hanya saat ada suara; layanan STT mengirim **teks sementara** (model `STT_PARTIAL_MODEL`, kata stabil tebal + sisa abu-abu) lalu **teks akhir** (`STT_STREAM_FINAL_MODEL`, default `STT_REFINE_MODEL`) yang menggantikannya. Dua pekerja paralel (teks akhir vs sementara) dan "terbaru yang menang" mencegah antrean menumpuk. Tetap hanya pratinjau: tidak disimpan; SOAP dari rekaman penuh. `POST /sessions/{id}/live` lama masih ada.

**Terukur di CPU laptop dev** (klip 45 dtk, mikrofon palsu, `tools/browser_e2e.py --latency-only --naskah ...`): teks sementara `base` ~1,5 dtk setelah mulai bicara; teks final `small` ~2-3 dtk setelah ucapan selesai; WER perkiraan ~0,21 (hanya pembanding antar konfigurasi). Ditolak karena terukur lebih buruk: teks sementara `small` (CPU jenuh, teks final tertinggal >10 dtk, WER 0,25). `large-v3-turbo` di CPU ~7,3 dtk/ucapan: terlalu lambat; hanya layak di GPU. Akurasi/kecepatan yang sebenarnya diinginkan butuh STT di GPU.
Bila port 5432 bentrok (Windows): `POSTGRES_HOST_PORT=5433`.

### Memuat tabel ICD-10 resmi (sekali)
Sumber: WHO ICD-10 versi 2019 (`icd102019en.xml.zip`, SHA-256 `344c571aa9aed3b9ad1c80261b7828c45cfb5fc0b1a5da64aecef354dff5b3d9`), [icdcdn.who.int/icd10](https://icdcdn.who.int/icd10/index.html). Unduh, ekstrak ke folder baru, lalu dari host (venv + `DATABASE_URL`, `LLM_BASE_URL` menunjuk ke host):
```bash
cd services/api
python -m app.terminology.loader icd10 PATH/icd102019en.xml --source-url https://icdcdn.who.int/icd10/claml/icd102019en.xml.zip
EMBEDDING_CPU=false python -m app.terminology.loader icd10 PATH/icd102019en.xml --source-url ... --embed-only   # ~60 menit di GPU 4 GB; boleh dilewati (trigram+FTS tetap jalan)
```
Memuat 14.291 kode (ekspansi modifier WHO seperti E11.9 dan M00.00 dibaca dari berkas itu sendiri). Tabel WHO berbahasa Inggris, jadi diagnosis Indonesia diterjemahkan LLM sebagai *kueri pencarian* saja; **kode tidak pernah berasal dari LLM**. Catatan: INA-CBG memakai ICD-10 yang dilokalkan Kemenkes; **koder RS harus memeriksa kecocokannya**.

## Status per fase

| Fase | Isi | Status |
|---|---|---|
| 0 | struktur, Compose, skema DB | selesai, diuji |
| 1 | rekam→STT→ekstraksi bukti→validator→SOAP→review→approve→adapter SIMRS, API key, job asinkron | selesai, diuji (otomatis + nyata di Docker + browser) |
| 2 | ICD-10 untuk diagnosis (retrieve→pilih→validasi) | selesai, diuji dengan tabel resmi WHO |
| 3 | KFA (obat), LOINC (lab) | **kode & aturan siap, DATA BELUM ADA**: LOINC butuh akun gratis ([loinc.org](https://loinc.org/get-started/getting-loinc/)); KFA butuh kredensial SatuSehat/Kemenkes. Dites hanya dengan data uji palsu berlabel `FAKE-` |
| 4 | tindakan, streaming, diarization, webhook/widget, FHIR | webhook, widget, pratinjau langsung, dua-mikrofon, FHIR+SatuSehat: ada (lihat catatan). **KPTL: sumber resmi tidak ditemukan.** Diarization otomatis satu-kanal: **tidak ada** |

### Memuat tabel lain bila datanya sudah Anda miliki
```bash
python -m app.terminology.loader loinc Loinc.csv --version 2.82 --code-col LOINC_NUM --display-col LONG_COMMON_NAME --extra-cols COMPONENT,SYSTEM --source-url https://loinc.org
python -m app.terminology.loader kfa  ekspor_kfa.csv --version TANGGAL --code-col KOLOM_KODE --display-col KOLOM_NAMA --source-url URL_RESMI
python -m app.terminology.loader kptl kptl.csv --version V --code-col ... --display-col ... --source-url URL_RESMI
```
Begitu tabelnya termuat, pipeline otomatis ikut memetakan obat→KFA, penunjang→LOINC, tindakan→ICD9CM (sistem yang belum dimuat dilewati). Nama kolom di atas harus disesuaikan dengan berkas resmi yang Anda unduh. **KPTL: sumber resmi tidak ditemukan**; saya tidak mengarang isinya. Pemetaan tindakan memakai nama sistem `ICD9CM`; ubah `FIELD_SYSTEM` di `app/terminology/mapper.py` bila ingin `KPTL`.

## Aturan klinis yang ditegakkan kode

- Bukti harus ada di transkrip (normalisasi huruf/tanda baca/koma desimal; awalan format prompt `[3] dokter:` dibuang) → jika tidak: **ditolak**. Segmen/waktu dihitung ulang oleh kode.
- Dosis/angka obat dan nama obat harus ada di bukti; angka kata ("tiga", "dua puluh lima") setara digit.
- Negasi vs status; diagnosis ditolak bila diucapkan pasien; dugaan ("curiga", "kemungkinan") → **ditandai**, tampil terpisah dan berlabel; rencana vs dilakukan.
- Satu mikrofon (pembicara tak diketahui): diagnosis **ditandai** untuk dikonfirmasi dokter. Dua mikrofon (dokter+pasien): label pasti.
- "Terlewat": obat, angka+satuan, istilah vocab yang tak tertutup butir lolos.
- **Kode**: LLM hanya memilih NOMOR dari kandidat tabel resmi; kode diambil dari kandidat dan divalidasi ada di tabel. `terisi` hanya bila butir diterima + keyakinan tinggi + peringkat 1 + kandidat tidak mirip; selain itu `saran` (tidak terisi). Dugaan/negasi/rencana tidak dikodekan sebagai diagnosis; obat "tidak dipakai" dan tindakan "direncanakan" tidak dikodekan; obat/lab riwayat atau rencana hanya saran. Dokter bisa menerima, mengganti (kode wajib ada di tabel), atau mengosongkan.
- JSON LLM rusak → coba ulang 1×, lalu manual. STT kosong → manual. ≥30% butir ditolak → peringatan kualitas rendah. SOAP kosong tak bisa di-approve.
- Audio dihapus setelah STT; pratinjau langsung tidak disimpan. Transkrip dihapus job purge setelah `TRANSCRIPT_RETENTION_DAYS` (30; **dihapus, belum diarsipkan terenkripsi**).
- Trigger DB: SOAP versi AI tak bisa di-approve; submit hanya untuk SOAP ter-approve; `audit_log` append-only.

## API ringkas (`/v1`)

| Endpoint | Auth | Fungsi |
|---|---|---|
| `POST /auth/login` | – | JWT dokter |
| `POST /sessions` | dokter / API key | buat sesi; consent wajib |
| `POST /sessions/{id}/audio` | dokter / API key | multipart `dokter`+`pasien` atau `mixed` |
| `WS /sessions/{id}/live/ws` | **dokter** | transkrip langsung streaming (tidak disimpan) |
| `POST /sessions/{id}/live` | dokter / API key | pratinjau per potongan (cara lama) |
| `GET /me`, `/queue`, `/sessions` | **dokter** | profil; antrean (adapter SIMRS) + statistik; riwayat sesi |
| `POST /sessions/{id}/finish` | dokter / API key | 202; pipeline asinkron (Celery) |
| `GET /sessions/{id}`, `/jobs/{id}` | dokter / API key | polling |
| `GET /sessions/{id}/review` | **dokter** | transkrip, butir, kode, terlewat, SOAP, peringatan |
| `PUT /sessions/{id}/soap` | **dokter** | simpan versi dokter |
| `PUT /sessions/{id}/codes/{cid}` | **dokter** | pilih/ganti/kosongkan kode |
| `GET /terminology/{icd10,kfa,loinc,icd9cm}/search?q=` | semua | cari kode |
| `POST /sessions/{id}/approve` | **dokter** | wajib versi dokter; kalimat bertanda perlu `acknowledge_flagged` |
| `POST /sessions/{id}/submit` | dokter / API key | kirim lewat adapter SIMRS (hanya bila approved; idempoten) |
| `POST /sessions/{id}/widget-token` | **API key** | token widget 1 jam, hanya untuk satu sesi |
| `GET/POST/PUT /admin/users…`, `/admin/integration…`, `/admin/settings…` | **admin RS** | pengelolaan pengguna, integrasi SIMRS, pengaturan; hanya menyentuh RS milik admin, tiap perubahan masuk `audit_log` |
| `GET/POST/PUT /platform/hospitals…` | **superadmin** | daftar/buat/atur RS (aktif, batas, kuota) dan kelola pengguna RS mana pun; tanpa data klinis; tercatat di `audit_log` RS terdampak |
| `GET /admin/audit`, `/admin/audit.csv`, `/admin/integration/submissions` (+`/{id}/retry`), `/admin/integration/webhook-log`, `PUT /admin/settings/privacy`, `/admin/settings/security` | **admin RS** | log audit RS, riwayat & kirim ulang SIMRS, log webhook, pengaturan per RS |
| `GET /platform/system` | **superadmin** | status teknis server (STT/LLM/GPU/terminologi) |
| `POST /me/password` | **dokter** | ganti kata sandi sendiri (wajib kata sandi saat ini) |

**Webhook**: `python -m app.admin set-webhook CLIENT URL`, `webhook-secret CLIENT`. Event `session.processed|approved|submitted`; payload hanya id+status; header `X-MedVoice-Signature: sha256=HMAC(secret, "<timestamp>.<body>")`; retry 5×.
**Widget**: server RS memanggil `widget-token` (API key tak pernah ke browser) lalu halaman memuat `/ui/widget.js` → `MedVoice.mount(...)`; lihat `/ui/widget-demo.html`. Origin yang boleh menyematkan = `--origin` client.
**FHIR/SatuSehat**: `app/fhir.py` membentuk Bundle (Composition SOAP + Condition ICD-10); `app/adapters/satusehat.py` mengirimnya, butuh `refs_resolver` dari SIMRS (ID Patient/Encounter/Practitioner/Organization; tidak dikarang).
**Adapter SIMRS**: hanya `mock` (menyediakan antrean contoh 7 pasien; `list_queue`/`patient_info` opsional di `app/adapters/base.py`); adapter nyata menunggu dokumentasi REST SIMRS Anda (antarmuka: `app/adapters/base.py`).

## Evaluasi dan pemilihan model (10 kasus SIMULASI + 13 istilah kode, **belum dianotasi dokter/koder**)

Perangkat uji: RTX 3050 Ti 4 GB, Whisper `small` int8 di CPU.

| Model LLM | obat P/R | dosis P/R | alergi P/R | diagnosis P/R | ditolak validator | waktu ekstraksi (7 segmen) |
|---|---|---|---|---|---|---|
| qwen2.5:3b q4 (100% GPU) | 0,56 / 0,56 | 1,00 / 0,83 | 0,67 / 0,67 | 1,00 / 0,57 | 0% | ~8-10 dtk* |
| **qwen2.5:7b q4 (46% CPU / 54% GPU)** | **0,75 / 0,67** (diterima: 0,86) | **1,00 / 1,00** | 0,67 / 0,67 | 1,00 / 0,71 | 2,7% | ~55 dtk |

*terukur saat GPU dipakai bersamaan; 3B murni ≈ 52 token/dtk.
Pemetaan ICD-10 (tabel WHO, retrieval hibrida + bge-m3): recall kandidat 0,89; akurasi usulan 3B 0,56 / **7B 0,67**; kode terisi otomatis oleh 7B: 3, semuanya benar (presisi 1,00); sisanya saran. Kesalahan tersisa yang **tak bisa dideteksi validator**: salah status/field (mis. alergi yang dilaporkan pasien tertulis "dinyatakan_dokter") dan pilihan kode yang meleset (mis. "diare akut" → A06.0 sebagai *saran*). **Default: 7B** (terbaik yang muat); pakai 3B bila latensi lebih penting. Gemma 3 tidak bisa dicoba (butuh Ollama lebih baru dari 0.6.5).
Jalankan ulang: `python -m evaluation.run_eval --models ...`, `python -m evaluation.code_eval`, `python -m evaluation.stt_wer ...`. **Jangan memilih model produksi sebelum dokter/koder menganotasi kasus (target ≥100) dan ada rekaman bahasa Indonesia.**

## Pengujian

**Otomatis** (86 lolos + 7 tes skema; Postgres sungguhan, STT/LLM tiruan di tes): validator, SOAP, evaluasi, alur penuh + jalur gagal, isolasi dokter/tenant, CORS/rate limit/kuota, pemetaan kode (aturan klinis, anti-halusinasi, tabel WHO asli), webhook (tanda tangan, tanpa data klinis, kegagalan), token widget (cakupan satu sesi), pratinjau langsung, FHIR/SatuSehat (transport tiruan).
```bash
cd services/api && TEST_ADMIN_URL=postgresql://USER:PASS@localhost:PORT/postgres python -m pytest tests
TEST_DATABASE_URL=postgresql://USER:PASS@localhost:PORT/medvoice_test python -m pytest tests/test_schema.py
```
**Nyata** (`tools/`): `smoke_e2e.py` (Whisper + Qwen + Celery/Redis + Postgres, audio TTS Inggris), `browser_e2e.py` (UI Vue: Chromium + mikrofon palsu; login, antrean, consent, rekam, transkrip langsung via WebSocket + tabel latensi, hasil, SOAP, setujui & kirim; `--latency-only` untuk ukur latensi saja). `browser_upload_e2e.py` dan `browser_widget_e2e.py` sudah disesuaikan ke UI baru tetapi **belum dijalankan ulang** setelah penggantian UI.

## BELUM dites / belum ada: jangan dianggap tersedia

- **Akurasi STT bahasa Indonesia** (belum ada rekaman Indonesia; suara TTS Windows hanya Inggris). Kualitas ekstraksi/kode pada percakapan klinis Indonesia nyata belum terukur; dokter harus tetap meninjau semuanya.
- Data & pemetaan **KFA, LOINC, KPTL/ICD-9-CM** (data tidak tersedia bagi saya; kode siap). FHIR hanya membentuk Condition ICD-10; obat/lab/tindakan belum menjadi resource sendiri.
- **SatuSehat nyata** (hanya transport tiruan; sistem kode KFA FHIR perlu diverifikasi) dan **adapter SIMRS nyata**.
- **Diarization otomatis** untuk rekaman satu kanal (butuh model berlisensi); solusi saat ini: dua mikrofon.
- Transkrip langsung: hanya pratinjau tampilan. Di CPU (laptop dev) teks sementara muncul ~1,3 dtk setelah mulai bicara dan teks akhir (`small`) ~2-3 dtk setelah ucapan selesai; GPU untuk STT belum dicoba. Akurasi teks langsung pada percakapan Indonesia nyata belum dievaluasi. Panel "Terdeteksi sejauh ini" pada desain **tidak** menampilkan ekstraksi langsung (butir klinis hanya dibuat setelah Selesai).
- TLS/reverse proxy, enkripsi kolom transkrip, backup & arsip terenkripsi, login SSO, beban/volume besar, profil GPU untuk STT. Server produksi untuk volume besar perlu GPU ≥ 24 GB; KVM 8 (tanpa GPU) hanya untuk dev data simulasi. **Data tidak boleh keluar jaringan RS** → Hostinger hanya untuk data simulasi.
