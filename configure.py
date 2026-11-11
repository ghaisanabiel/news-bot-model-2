"""Local-only configuration window. Secrets never pass through the chat."""
import secrets
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    window = tk.Tk()
    window.title('ARUS — Hubungkan bot pribadi')
    window.geometry('680x510')
    window.configure(padx=24, pady=20)
    existing = {}
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                existing[key.strip()] = value.strip()
    tk.Label(window, text='Hubungkan Telegram dan AI', font=('Arial', 17, 'bold')).pack(anchor='w')
    tk.Label(window, text='AI memakai login langganan ChatGPT di Codex. Cukup isi token bot Telegram; tidak perlu API key OpenAI.',
             wraplength=610, justify='left').pack(anchor='w', pady=(8, 18))
    fields = {}
    for key, title, secret in [('TELEGRAM_BOT_TOKEN', 'Token bot Telegram', True),
                               ('BRAND_NAME', 'Nama akun / brand di desain', False)]:
        tk.Label(window, text=title).pack(anchor='w')
        entry = tk.Entry(window, show='*' if secret else '', width=85)
        entry.insert(0, existing.get(key, {'BRAND_NAME': 'ARUS'}.get(key, '')))
        entry.pack(anchor='w', pady=(3, 10))
        fields[key] = entry
    result = tk.StringVar()

    def save():
        values = {key: entry.get().strip() for key, entry in fields.items()}
        if not all(values.values()) or ':' not in values['TELEGRAM_BOT_TOKEN']:
            messagebox.showerror('Belum lengkap', 'Isi semua kolom dan pastikan token Telegram berasal dari BotFather.')
            return
        values['PAIRING_CODE'] = existing.get('PAIRING_CODE') or secrets.token_urlsafe(24)
        values['CODEX_MODEL'] = existing.get('CODEX_MODEL', '')
        for key, default in [('SCAN_MINUTES', '30'), ('AI_CALL_LIMIT', '120'), ('DAILY_CANDIDATES', '8')]:
            values[key] = existing.get(key, default)
        path.write_text('\n'.join(f'{key}={value}' for key, value in values.items()) + '\n', encoding='utf-8')
        result.set('/start ' + values['PAIRING_CODE'])
        messagebox.showinfo('Tersimpan', 'Jalankan Mulai Bot.cmd, lalu kirim perintah pemasangan di bawah ke bot Telegram kamu. Jangan bagikan kode ini.')

    tk.Button(window, text='Simpan pengaturan', command=save, padx=15, pady=5).pack(anchor='w', pady=8)
    tk.Label(window, text='Perintah pemasangan (salin ke percakapan pribadi bot):').pack(anchor='w')
    tk.Entry(window, textvariable=result, state='readonly', width=85).pack(anchor='w', pady=5)
    if existing.get('PAIRING_CODE'):
        result.set('/start ' + existing['PAIRING_CODE'])
    tk.Label(window, text='Pemakaian mengikuti kuota langganan Codex kamu. Folder ini berada di OneDrive; token Telegram dapat ikut tersinkron.',
             wraplength=610, justify='left', fg='#555555').pack(anchor='w', pady=10)
    window.mainloop()


if __name__ == '__main__':
    main()
