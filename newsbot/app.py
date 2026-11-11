import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import timedelta
from pathlib import Path
from .config import ROOT, now
from .models import Story, Draft, parse_date
from .render import render_package
from .photos import cover_photo, credit_line
from .telegram import TelegramError, buttons, card

HELP = '''ARUS — asisten redaksi ekonomi & investasi

/cari — cari berita sekarang dan kirim kandidat
/daftar — lihat kandidat dan pekerjaan terakhir
/lihat 12 — buka berita N-012
/revisi 12 fokus dampaknya ke UMKM — revisi sudut/naskah
/ulang 12 — ulang pekerjaan yang gagal
/status — status, cakupan pencarian dan pemakaian
/jeda — hentikan pencarian terjadwal
/lanjut — aktifkan pencarian terjadwal
/batal 12 — batalkan berita/produksi
/bantuan — menu ini

Kandidat dikirim pukul 07.00, 12.30, 18.30 WIB. Tidak ada kuota topik.
Pilih berita → tinjau desain → finalkan. Tidak memposting ke media sosial otomatis.'''


class App:
    def __init__(self, config, store, editor, telegram, output=None):
        self.config, self.store, self.editor, self.tg = config, store, editor, telegram
        self.output = Path(output or ROOT / 'output')
        self.stop = threading.Event()

    def owner(self):
        return self.store.get('owner')

    def send(self, text, keyboard=None):
        if self.owner():
            return self.tg.send(self.owner(), text, keyboard)

    def active(self, ident, version, statuses):
        row = self.store.story(ident)
        return row if row and row['version'] == version and row['status'] in statuses else None

    def show(self, ident):
        row = self.store.story(ident)
        if not row:
            self.send('Nomor berita tidak ditemukan.')
            return
        self.send(card(row), buttons(ident, row['version'], preview=row['status'] in ('preview', 'final')))
        if row['status'] in ('preview', 'final') and row['package']:
            self.tg.file(self.owner(), row['package'], caption=f"N-{ident:03} v{row['version']} · {row['status']}")

    def handle(self, update):
        callback = update.get('callback_query')
        message = callback.get('message', {}) if callback else update.get('message', {})
        sender = (callback or message).get('from', {})
        chat = message.get('chat', {})
        if chat.get('type') != 'private' or not sender.get('id'):
            if callback:
                self.tg.answer(callback['id'], 'Gunakan percakapan pribadi dengan bot.')
            return
        uid = str(sender['id'])
        text = message.get('text', '').strip()
        if not self.owner():
            if not callback and text.startswith('/start ') and hmac.compare_digest(text[7:].strip(), self.config.pairing_code):
                self.store.set('owner', uid)
                self.store.log('paired', 'Owner connected')
                self.send('Terhubung ke akun kamu.\n\n' + HELP)
            return
        if uid != self.owner() or str(chat.get('id')) != self.owner():
            if callback:
                self.tg.answer(callback['id'], 'Bot ini hanya untuk pemiliknya.')
            return
        if callback:
            try:
                self.tg.answer(callback['id'])
            except TelegramError:
                logging.warning('Telegram could not acknowledge button; processing the action anyway.')
            self.action(callback.get('data', ''))
        else:
            self.command(text, update['update_id'])

    def command(self, text, update_id):
        parts = text.split(maxsplit=2)
        cmd = parts[0].split('@')[0].lower() if parts else ''
        if cmd in ('/start', '/bantuan', '/help'):
            self.send(HELP)
        elif cmd == '/cari':
            if self.store.enqueue(f'manual:{update_id}', 'scan', payload='notify'):
                self.send('Pencarian masuk antrean. Aku akan kirim kandidat yang lolos pemeriksaan.')
        elif cmd in ('/jeda', '/lanjut'):
            self.store.set('paused', int(cmd == '/jeda'))
            self.send('Pencarian terjadwal dijeda. Pekerjaan yang sudah kamu pilih tetap diproses.' if cmd == '/jeda'
                      else 'Pencarian terjadwal aktif kembali.')
        elif cmd == '/status':
            calls, tokens = self.store.usage()
            self.send(f"Jadwal: {'dijeda' if self.store.get('paused') == '1' else 'aktif'}\n"
                      f"Pencarian terakhir: {self.store.get('last_scan', 'belum ada')}\n"
                      f"AI hari ini: {calls}/{self.config.ai_call_limit} panggilan, {tokens} token tercatat.\n"
                      'Ini batas penggunaan, bukan batas biaya rupiah.\n\nCakupan terakhir: '
                      + self.store.get('coverage', 'Belum ada penelusuran.'))
        elif cmd == '/daftar':
            with self.store.db() as db:
                rows = db.execute('SELECT id,status,body FROM stories ORDER BY id DESC LIMIT 12').fetchall()
            self.send('\n'.join(f"N-{r['id']:03} [{r['status']}] {Story.model_validate_json(r['body']).title}" for r in rows)
                      + '\n\nGunakan /lihat NOMOR.' if rows else 'Belum ada berita. Gunakan /cari.')
        elif cmd in ('/lihat', '/ulang', '/revisi', '/batal'):
            if len(parts) < 2 or not parts[1].isdigit():
                self.send('Sertakan nomor berita, contoh /lihat 12 atau /revisi 12 fokus rupiah.')
                return
            ident = int(parts[1])
            row = self.store.story(ident)
            if not row:
                self.send('Nomor berita tidak ditemukan.')
                return
            if cmd == '/lihat':
                self.show(ident)
            elif cmd == '/ulang':
                self.store.failed_retry(ident, row['version'])
                self.send('Pekerjaan gagal/terputus versi ini dimasukkan kembali jika tersedia.')
            elif cmd == '/batal':
                self.store.update(ident, status='cancelled', version=row['version'] + 1)
                self.send('Dibatalkan. Hasil pekerjaan yang masih berjalan tidak akan dikirim.')
            elif len(parts) < 3:
                self.send(f'Contoh: /revisi {ident} judul lebih sederhana, fokus dampaknya ke UMKM.')
            elif row['status'] not in ('preview', 'candidate', 'final', 'watch'):
                self.send('Berita sedang diproses atau sudah dibatalkan. Tunggu pratinjau terlebih dahulu.')
            else:
                version = row['version'] + 1
                self.store.update(ident, version=version, status='candidate', draft=None, package=None, note=parts[2][:1500])
                self.store.enqueue(f'build:{ident}:{version}', 'build', ident, version)
                self.send('Arahan revisi diterima. Fakta akan diperiksa ulang sebelum naskah dibuat.')
        else:
            self.send('Gunakan tombol pada kandidat atau /bantuan. Untuk arahan khusus: /revisi NOMOR arahan kamu.')

    def action(self, data):
        try:
            action, ident, version = data.split(':')
            ident, version = int(ident), int(version)
        except (ValueError, TypeError):
            return
        row = self.store.story(ident)
        if not row or row['version'] != version:
            self.send('Tombol ini berasal dari versi lama. Gunakan /lihat NOMOR untuk versi terbaru.')
            return
        status = row['status']
        if action in ('skip', 'cancel'):
            self.store.update(ident, status='skipped' if action == 'skip' else 'cancelled', version=version + 1)
            self.send('Berita dilewati.' if action == 'skip' else 'Produksi dibatalkan.')
        elif action == 'revise':
            self.send(f'Kirim /revisi {ident} diikuti arahanmu, contoh: fokus dampaknya ke rupiah.')
        elif action == 'watch' and status == 'candidate':
            self.store.update(ident, status='watch')
            self.send('Masuk daftar pantau. Aku periksa lagi pada jadwal rangkuman berikutnya.')
        elif action in ('build', 'research', 'final', 'photo'):
            allowed = {'build': ('candidate', 'watch'), 'research': ('candidate', 'watch'), 'final': ('preview',), 'photo': ('preview',)}
            if status not in allowed[action]:
                self.send('Pilihan sudah diproses atau tidak berlaku. Gunakan /lihat NOMOR.')
                return
            kind = 'check' if action == 'research' else action
            if self.store.enqueue(f'{kind}:{ident}:{version}', kind, ident, version):
                self.send('Aku cari foto lain dengan izin penggunaan yang sesuai.' if kind == 'photo'
                          else 'Masuk antrean. Aku cek sumber dan perkembangan terbaru terlebih dahulu.')
            else:
                self.send(f'Pilihan ini sudah tercatat. Jika sebelumnya gagal, gunakan /ulang {ident}.')

    def deliver_candidates(self):
        remaining = max(0, min(3, self.config.daily_candidates - self.store.sent_today()))
        delivered = 0
        for row in self.store.candidates():
            story = Story.model_validate_json(row['body'])
            if now() - parse_date(story.published_at) > timedelta(hours=48):
                self.store.update(row['id'], status='expired')
                continue
            if delivered >= remaining:
                break
            # Reserve before network delivery; uncertain sends are never silently retried.
            self.store.update(row['id'], sent_day=now().date().isoformat())
            self.send(card(row), buttons(row['id'], row['version']))
            delivered += 1
        return delivered

    def scan(self, notify=False):
        with self.store.db() as db:
            rows = db.execute('SELECT body FROM stories ORDER BY id DESC LIMIT 80').fetchall()
        known = [{'event_key': (s := Story.model_validate_json(r[0])).event_key, 'title': s.title} for r in rows]
        result = self.editor.scan(known)
        for story in result.stories:
            self.store.add(story)
        self.store.set('coverage', result.coverage)
        self.store.set('last_scan', now().isoformat())
        if notify:
            delivered = self.deliver_candidates()
            if not delivered:
                self.send('Belum ada kandidat baru yang lolos, atau batas kiriman harian sudah tercapai.\n\n'
                          'Cakupan pencarian: ' + result.coverage)

    def process_story(self, job):
        ident, version, kind = job['story_id'], job['version'], job['kind']
        statuses = ('preview',) if kind in ('final', 'photo') else ('candidate', 'watch')
        row = self.active(ident, version, statuses)
        if not row:
            return
        previous = row['status']
        if not self.store.transition(ident, version, statuses, status='working'):
            return
        try:
            story = Story.model_validate_json(row['body'])
            if kind == 'photo':
                draft = Draft.model_validate_json(row['draft'])
                prior = self.output / f'N-{ident:03}'
                used = {json.loads(path.read_text(encoding='utf-8'))['id'] for path in prior.glob('v*/foto-kredit.json')}
                photo = cover_photo(story, used)
                if not photo:
                    raise ValueError('Belum ada foto alternatif yang cocok dan punya izin penggunaan. Pratinjau sebelumnya masih tersedia.')
                self.publish_preview(row, story, draft, photo, new_version=version + 1)
                return
            recently_rechecked = (
                kind == 'build'
                and self.store.get(f'rechecked_version:{ident}') == str(version)
                and now() - parse_date(row['checked']) < timedelta(minutes=15)
            )
            check = None if recently_rechecked else self.editor.recheck(story)
            if not self.active(ident, version, ('working',)):
                return
            if check is not None and (check.material_change or kind == 'check'):
                # Any explicit research creates a new reviewable version; no implicit approval.
                if not self.store.transition(ident, version, ('working',), body=check.story.model_dump_json(), version=version + 1,
                                             status='candidate', draft=None, package=None, checked=now().isoformat()):
                    return
                self.store.set(f'rechecked_version:{ident}', version + 1)
                self.send(f'N-{ident:03}: {check.explanation}\nTinjau versi terbaru sebelum produksi.')
                self.show(ident)
                return
            if kind == 'watch':
                self.store.transition(ident, version, ('working',), status='watch', checked=now().isoformat())
                return
            if kind == 'final':
                if not self.store.transition(ident, version, ('working',), status='final', checked=now().isoformat()):
                    return
                self.tg.file(self.owner(), row['package'], caption=f'N-{ident:03} v{version} · FINAL — siap kamu unggah.')
                self.send('Paket berisi gambar PNG, caption, teks alternatif, naskah, dan sumber. Tidak diposting otomatis.')
                return
            # Draft strictly from approved evidence. New research confirmed no material change.
            draft = self.editor.produce(story, row['note'])
            if not self.active(ident, version, ('working',)):
                return
            self.publish_preview(row, story, draft, cover_photo(story))
        except Exception:
            self.store.transition(ident, version, ('working',), status=previous)
            raise

    def publish_preview(self, row, story, draft, photo, new_version=None):
        ident, previous_version = row['id'], row['version']
        version = new_version or previous_version
        if not self.active(ident, previous_version, ('working',)):
            return
        destination = self.output / f'N-{ident:03}' / f'v{version}'
        slides, package = render_package(story, draft, destination, self.config.brand, ident, version, photo=photo)
        if not self.store.transition(ident, previous_version, ('working',), status='preview', version=version,
                                     draft=draft.model_dump_json(), package=str(package), checked=row['checked'] if new_version else now().isoformat()):
            return
        for index, path in enumerate(slides, 1):
            if not self.active(ident, version, ('preview',)):
                return
            self.tg.file(self.owner(), path, photo=True, caption=f'PRATINJAU N-{ident:03} v{version} · {index}/{len(slides)}')
        self.send(draft.caption + ('\n\n' + credit_line(photo.credit) if photo else ''))
        self.send('Periksa semua slide dan caption. Finalkan akan memeriksa fakta sekali lagi.', buttons(ident, version, True))

    def tick(self, clock=None):
        clock = clock or now()
        if not self.owner() or self.store.get('paused') == '1':
            return
        # Sleep/offline time is not backfilled into a flood of notifications.
        if 7 <= clock.hour < 22:
            slot = int(clock.timestamp()) // (self.config.scan_minutes * 60)
            self.store.enqueue(f'scheduled-scan:{slot}', 'scan')
        for hour, minute in ((7, 0), (12, 30), (18, 30)):
            target = clock.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if timedelta(0) <= clock - target < timedelta(minutes=30):
                key = f'digest:{target.isoformat()}'
                if self.store.enqueue(key, 'digest'):
                    with self.store.db() as db:
                        watched = db.execute("SELECT id,version FROM stories WHERE status='watch' ORDER BY checked LIMIT 5").fetchall()
                    for row in watched:
                        self.store.enqueue(f"watch:{key}:{row['id']}", 'watch', row['id'], row['version'])

    def work_once(self):
        job = self.store.claim()
        if not job:
            return False
        try:
            if job['kind'] == 'scan':
                if job['payload'] == 'notify' or (self.store.get('paused') != '1' and 7 <= now().hour < 22):
                    self.scan(job['payload'] == 'notify')
            elif job['kind'] == 'digest':
                if self.store.get('paused') != '1' and 7 <= now().hour < 22:
                    self.deliver_candidates()
            else:
                self.process_story(job)
            self.store.finish(job['id'])
        except Exception as exc:
            self.store.finish(job['id'], 'failed')
            # Error types only: third-party exception strings can contain credentials or request bodies.
            detail = str(exc)[:700] if type(exc) is ValueError else type(exc).__name__
            self.store.log('job_failed', f"job={job['id']} {detail}")
            try:
                target = f"N-{job['story_id']:03}: " if job['story_id'] else ''
                self.send(f'{target}Proses belum selesai: {detail}\n' +
                          (f"Gunakan /ulang {job['story_id']} untuk mencoba kembali." if job['story_id'] else 'Gunakan /cari untuk mencoba lagi.'))
            except Exception:
                logging.warning('Failed to deliver job failure notice; use /status and /daftar.')
        return True

    def worker(self):
        while not self.stop.is_set():
            self.tick()
            if not self.work_once():
                self.stop.wait(1)

    def run(self):
        me = self.tg.call('getMe')
        webhook = self.tg.call('getWebhookInfo')
        if webhook.get('url'):
            raise ValueError('Bot ini memiliki webhook aktif. Gunakan bot khusus atau hapus webhook lama terlebih dahulu.')
        interrupted = self.store.recover()
        print(f"Bot @{me['username']} aktif. Ctrl+C untuk berhenti.")
        if not self.owner():
            print('Buka bot Telegram kamu, lalu kirim kode pemasangan yang ditampilkan saat pengaturan.')
        elif interrupted:
            self.send('Ada pekerjaan yang terputus saat aplikasi berhenti. Gunakan /daftar dan /ulang NOMOR untuk melanjutkan.')
        thread = threading.Thread(target=self.worker, daemon=True)
        thread.start()
        offset = int(self.store.get('offset', '0'))
        try:
            while not self.stop.is_set():
                try:
                    for update in self.tg.updates(offset):
                        self.handle(update)
                        offset = update['update_id'] + 1
                        self.store.set('offset', offset)
                except Exception as exc:
                    logging.warning('Telegram polling interrupted (%s). Retrying.', type(exc).__name__)
                    self.stop.wait(5)
        finally:
            self.stop.set()
            thread.join(timeout=5)
