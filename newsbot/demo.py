from .config import now
from .models import Story, Draft, validate_draft
from .render import render_package


def example_story():
    stamp = now().isoformat()
    url = 'https://example.com/simulasi'
    return Story(event_key='simulasi-kebijakan', title='SIMULASI: memahami perubahan kebijakan',
                 category='Ekonomi Indonesia', summary='Contoh fiktif untuk menguji tata letak, bukan berita nyata.',
                 why='Membantu pembaca memahami jalur dampak kebijakan.', angle='Pahami konteks sebelum menyimpulkan',
                 event_at=stamp, published_at=stamp, score=80, verified=True,
                 uncertainty='Semua isi contoh ini fiktif dan tidak boleh digunakan sebagai berita.',
                 sources=[dict(url=url, title='Dokumen simulasi', publisher='Contoh', origin='simulasi',
                               primary=True, published_at=stamp, read_full=True)],
                 facts=[dict(id='F1', text='Materi ini hanya contoh fiktif, bukan pengumuman kebijakan.',
                             source_urls=[url], evidence='Contoh fiktif untuk pengujian desain.')])


def example_draft():
    return Draft(slides=[
        dict(title='Kebijakan berubah. Apa yang perlu kamu pahami?',
             body='SIMULASI — contoh desain konten ekonomi. Tidak ada keputusan kebijakan aktual yang diberitakan di sini.', fact_ids=['F1']),
        dict(title='Mulai dari fakta, lalu lihat konteks.',
             body='Pada berita nyata, bagian ini akan memuat keputusan, periode, dan sumber resmi. Angka tidak diisi jika buktinya belum tersedia.', fact_ids=['F1']),
        dict(title='Dampak perlu bukti. Bukan sekadar dugaan.',
             body='Bagian analisis akan menjelaskan kemungkinan dampak secara bersyarat. Contoh ini tidak berisi rekomendasi investasi.', fact_ids=['F1']),
        dict(title='Pilih berita. Tinjau. Baru bagikan.',
             body='Bot mengajukan kandidat, kamu menentukan sudutnya, lalu memeriksa desain dan caption sebelum paket difinalkan.', fact_ids=['F1'])],
                 caption='SIMULASI FIKTIF. Contoh tampilan ARUS, bukan berita aktual atau rekomendasi investasi.',
                 alt_text=['Contoh fiktif sampul berita ekonomi.', 'Contoh slide penjelasan fakta.',
                           'Contoh slide analisis bersyarat.', 'Contoh slide alur editorial.'])


def create_demo(destination):
    story, draft = example_story(), example_draft()
    validate_draft(draft, story)
    return render_package(story, draft, destination, 'ARUS', 0, 1, demo=True)[1]
