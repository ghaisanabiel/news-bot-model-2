# ARUS — bot redaksi ekonomi dan investasi

Bot Telegram pribadi: mencari berita, mengajukan kandidat, membuat desain setelah dipilih, lalu mengirim paket siap unggah setelah ditinjau. **Tidak ada kuota komposisi topik.**

## Mulai di komputer ini

1. Pastikan Codex CLI sudah login menggunakan ChatGPT (`codex login status`). Buka **Pengaturan.cmd**, isi token dari BotFather dan nama brand. Klik **Simpan pengaturan**. **Tidak perlu API key OpenAI.**
2. Buka **Mulai Bot.cmd**. Biarkan jendelanya berjalan.
3. Salin perintah `/start KODE_PEMASANGAN` dari jendela pengaturan ke percakapan pribadi bot Telegram milikmu. Ini mengunci bot ke akunmu.
4. Kirim `/cari`. Periksa kandidat, lalu tekan **Bikin konten**.
5. Tinjau gambar dan caption. Pilih **Finalkan** atau **Revisi**.

Dependensi yang dibutuhkan sudah tersedia pada lingkungan pembangunan ini. Jika muncul modul tidak ditemukan, jalankan **Pasang Dependensi.cmd**. Memerlukan Python 3.11+, Codex CLI, login ChatGPT dengan akses Codex, dan koneksi internet. Pemakaian mengikuti batas langganan Codex; jika kuota habis, proses berhenti sampai akses tersedia kembali. Bot tidak beralih otomatis ke API berbayar.

Token tidak perlu dikirim ke percakapan Codex. Nilai disimpan di `.env`, dikecualikan dari Git. Folder proyek berada di OneDrive sehingga `.env` mungkin ikut tersinkron; simpan proyek di folder privat yang tidak dibagikan. Jangan bagikan kode pemasangan. Untuk mengganti pemilik, hentikan bot dan ubah pengaturan pemilik di database setelah mencadangkan data; jangan membagikan database ke pengguna lain.

## Yang sudah diimplementasikan

- Penelusuran web menggunakan Codex CLI resmi dengan login ChatGPT yang sudah tersimpan, tanpa daftar persentase topik. Kunci/token login Codex tidak diekstrak atau disalin oleh bot.
- Cakupan: Indonesia, AS, aliran modal, perusahaan, crypto, komoditas, dan perkembangan global yang relevan.
- Kandidat memakai sumber, tanggal, bukti per fakta, skor editorial, dan catatan ketidakpastian.
- Pencarian web wajib teramati pada hasil Codex. Halaman sumber HTML diambil ulang oleh bot; hanya teks halaman yang berhasil diambil dapat menjadi bukti. Berita lama, sumber sindikasi tunggal, serta fakta tanpa rujukan ditolak.
- Penggabungan berdasarkan event key, URL sumber, dan kemiripan judul. Ini heuristik; tetap mungkin ada duplikat semantik yang terlewat.
- Pairing akun pemilik, pembatasan percakapan pribadi, tombol versi, pencegahan pekerjaan ganda, pencatatan keputusan, dan antrean persisten SQLite.
- Pemeriksaan ulang sebelum produksi dan sebelum finalisasi. Perubahan material mengembalikan berita menjadi kandidat versi baru.
- Penulisan dengan pemetaan klaim ke fakta dan pemeriksaan editorial kedua.
- Template tipografi 1080 × 1350, 1–6 slide, pengecekan ruang teks, caption, alt text, bukti, dan ZIP.
- Revisi lewat `/revisi NOMOR arahan`, daftar pantau, lewati, batalkan, jeda, lanjutkan, dan ulang pekerjaan gagal.
- Batas panggilan AI per hari dan pencatatan token, termasuk reservasi panggilan yang gagal.

## Jadwal awal

- Pencarian setiap 30 menit selama 07.00–22.00 WIB ketika komputer dan bot menyala.
- Rangkuman pukul 07.00, 12.30, dan 18.30 WIB; maksimal tiga kandidat per rangkuman, delapan kandidat per hari.
- `/cari` melakukan pencarian manual dan mengirim kandidat dengan batas harian yang sama.
- Berita semalam dicari pada pagi hari. Ini belum pemantauan 24 jam atau layanan breaking-news instan.
- Maksimal lima berita dalam daftar pantau diperiksa pada setiap jadwal rangkuman, bergiliran berdasarkan waktu pemeriksaan terakhir.
- Komputer mati/tidur atau bot ditutup berarti pemantauan berhenti. Belum dipasang ke server atau Windows startup.

## Perintah

| Perintah | Fungsi |
|---|---|
| `/cari` | Cari dan ajukan kandidat |
| `/daftar` | Lihat 12 berita/pekerjaan terakhir |
| `/lihat 12` | Buka kartu atau unduh paket N-012 |
| `/revisi 12 fokus UMKM` | Buat versi baru dengan arahan |
| `/ulang 12` | Ulang pekerjaan versi terkini yang gagal/terputus |
| `/batal 12` | Batalkan dan nonaktifkan tombol versi lama |
| `/status` | Jadwal, cakupan pencarian terakhir, jumlah panggilan dan token |
| `/jeda` | Jeda pencarian terjadwal; pekerjaan yang telah dipilih tetap berjalan |
| `/lanjut` | Aktifkan kembali jadwal |
| `/bantuan` | Bantuan |

## Pengaturan

Pengaturan lanjutan tersedia di `.env`; mulai ulang bot setelah mengubahnya.

| Nilai | Awal | Arti |
|---|---|---|
| `CODEX_MODEL` | kosong | Memakai model bawaan Codex; boleh diisi model yang tersedia pada akun |
| `BRAND_NAME` | `ARUS` | Nama pada desain |
| `SCAN_MINUTES` | `30` | Interval pencarian, minimal 10 menit |
| `AI_CALL_LIMIT` | `120` | Maksimal permintaan model/hari WIB |
| `DAILY_CANDIDATES` | `8` | Maksimal kandidat baru/hari |

Satu pencarian biasanya memerlukan dua permintaan model; produksi memakai pemeriksaan ulang, penulisan, dan review. Setiap proses Codex dibatasi lima menit. Batas jumlah panggilan adalah kendali lokal, bukan ukuran sisa kuota langganan. Pencarian rutin bisa menghabiskan kuota bersama pemakaian Codex kamu; tingkatkan `SCAN_MINUTES` atau gunakan `/jeda` dan `/cari` bila diperlukan. Tidak ada API key atau fallback tagihan API.

Proses model berjalan dengan izin baca saja; shell, aplikasi terhubung, plugin, hooks, dan multi-agent dimatikan. Token Telegram dan variabel lingkungan berisi rahasia tidak diteruskan ke proses model. Jangan mengekspos bot ini sebagai layanan publik untuk pengguna lain.

## Penyimpanan dan pemulihan

- `data/news.sqlite3`: berita, versi, keputusan, antrean, metadata penelusuran dan pemakaian.
- `output/N-XXX/vY/`: gambar, caption, teks alternatif, naskah dan bukti.
- `output/demo/`: contoh **fiktif**, tidak dikirim ke Telegram dan tidak menggunakan API.

Proses yang terputus tidak memicu AI ulang secara diam-diam. Gunakan `/ulang NOMOR`. Jika pengiriman Telegram gagal setelah hasil tersimpan, gunakan `/lihat NOMOR` untuk mengambil paket yang ada. Pengiriman kandidat dicatat sebelum jaringan dipanggil untuk menghindari kiriman otomatis berulang; kandidat yang gagal terkirim tetap tersedia di `/daftar`.

## Batas versi ini

Versi ini adalah implementasi awal yang bisa dijalankan, bukan seluruh fitur tahap lanjutan dalam rancangan. Belum ada feed berlisensi, kalender ekonomi terintegrasi, grafik data pasar, tiga keluarga template, personalisasi dari perilaku, cloud hosting, publikasi otomatis, atau pemantauan koreksi terhadap semua konten yang sudah difinalkan. Gunakan **Pantau** untuk berita yang masih ingin diikuti sebelum produksi.

Pencarian web tidak menjamin semua sumber terjangkau. Pengambilan sumber langsung saat ini mendukung HTML, bukan PDF, halaman login, atau halaman yang hanya menampilkan isi melalui JavaScript. Penilaian isi, independensi sumber, dan perubahan material masih melibatkan AI; validasi URL tidak membuktikan kebenaran klaim. Pemilik perlu meninjau sumber serta naskah sebelum posting. Kegagalan riset dilaporkan sebagai kegagalan, bukan “tidak ada berita”.

## Verifikasi lokal

```powershell
python -m unittest discover -s tests -v
python -m newsbot --demo
python -m newsbot --check
```

Pengujian otomatis memakai AI dan Telegram tiruan untuk membuktikan alur, validasi, hak akses, dan pemulihan tanpa penggunaan kuota atau kiriman sungguhan. Mode demo merender contoh fiktif. `--check` hanya memeriksa kelengkapan pengaturan; bukan pengujian koneksi. Akses Codex lewat login ChatGPT dan pencarian web sudah diuji langsung. Koneksi Telegram membutuhkan token bot diisi.

Dokumentasi integrasi: [Telegram Bot API](https://core.telegram.org/bots/api), [Codex non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode), [login ChatGPT di Codex](https://learn.chatgpt.com/docs/auth?surface=cli).
