import json
import requests


class TelegramError(RuntimeError):
    pass


class Telegram:
    def __init__(self, token):
        self.base = f'https://api.telegram.org/bot{token}/'

    def call(self, method, data=None, files=None, timeout=40):
        # Never log URLs/exceptions from requests: they contain the bot token.
        try:
            response = requests.post(self.base + method, data=data, files=files, timeout=timeout)
            result = response.json()
        except (requests.RequestException, ValueError):
            raise TelegramError('Koneksi Telegram gagal; periksa jaringan.') from None
        if not result.get('ok'):
            raise TelegramError(f"Telegram menolak permintaan ({result.get('error_code', response.status_code)}).")
        return result['result']

    def updates(self, offset):
        return self.call('getUpdates', {'offset': offset, 'timeout': 20,
                                        'allowed_updates': json.dumps(['message', 'callback_query'])})

    def send(self, chat, text, keyboard=None):
        chunks = []
        while len(text) > 3000:
            cut = text.rfind('\n', 0, 3000)
            if cut < 1:
                cut = 3000
            chunks.append(text[:cut])
            text = text[cut:].lstrip('\n')
        chunks.append(text)
        result = None
        for i, chunk in enumerate(chunks):
            data = {'chat_id': chat, 'text': chunk, 'link_preview_options': json.dumps({'is_disabled': True})}
            if keyboard and i == len(chunks) - 1:
                data['reply_markup'] = json.dumps({'inline_keyboard': keyboard})
            result = self.call('sendMessage', data)
        return result

    def answer(self, callback_id, text='Sedang diproses'):
        return self.call('answerCallbackQuery', {'callback_query_id': callback_id, 'text': text[:180]})

    def file(self, chat, path, photo=False, caption=''):
        with open(path, 'rb') as stream:
            field = 'photo' if photo else 'document'
            return self.call('sendPhoto' if photo else 'sendDocument',
                             {'chat_id': chat, 'caption': caption[:1000]}, {field: stream}, timeout=90)


def buttons(ident, version, preview=False):
    actions = ([('Finalkan', 'final'), ('Revisi', 'revise'), ('Ganti foto', 'photo')]
               if preview else [('Bikin konten', 'build'), ('Cari info lagi', 'research'), ('Pantau', 'watch'), ('Lewati', 'skip')])
    actions.append(('Batalkan', 'cancel')) if preview else None
    result = [{'text': label, 'callback_data': f'{action}:{ident}:{version}'} for label, action in actions]
    return [result[i:i + 2] for i in range(0, len(result), 2)]


def card(row):
    from .models import Story
    story = Story.model_validate_json(row['body'])
    sources = '\n'.join(f'{s.publisher}: {s.url}' for s in story.sources)
    return (f"N-{row['id']:03} · v{row['version']} · {story.category}\n\n{story.title}\n\n"
            f'{story.summary}\n\nKenapa penting: {story.why}\n\nSudut konten: {story.angle}\n\n'
            f'Catatan: {story.uncertainty}\n\nPeristiwa: {story.event_at}\nPublikasi: {story.published_at}\n'
            f"Diperiksa: {row['checked']}\n\nSumber:\n{sources}")
