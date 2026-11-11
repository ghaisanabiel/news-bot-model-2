import argparse
import logging
import socket
import sys
from .config import Config, ROOT
from .store import Store


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='ARUS — news bot ekonomi pribadi')
    parser.add_argument('--demo', action='store_true', help='Render contoh fiktif tanpa API atau Telegram')
    parser.add_argument('--check', action='store_true', help='Periksa pengaturan lokal tanpa koneksi jaringan')
    args = parser.parse_args()
    if args.demo:
        from .demo import create_demo
        print(create_demo(ROOT / 'output' / 'demo'))
        return
    try:
        config = Config.load()
        if args.check:
            print('Pengaturan lokal lengkap. Koneksi Telegram dan AI belum diuji.')
            return
        # OS-owned local lock releases automatically after crashes; prevents two pollers.
        lock = socket.socket()
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            lock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            lock.bind(('127.0.0.1', 47839))
        except OSError:
            raise ValueError('Bot sudah berjalan atau port lokal 47839 sedang dipakai.') from None
        (ROOT / 'data').mkdir(exist_ok=True)
        from .codex_editor import CodexEditor
        from .telegram import Telegram
        from .app import App
        store = Store(ROOT / 'data' / 'news.sqlite3')
        editor = CodexEditor(config, store)
        editor.check_login()
        App(config, store, editor, Telegram(config.token)).run()
    except KeyboardInterrupt:
        print('Bot dihentikan.')
    except ValueError as exc:
        print(str(exc))
        raise SystemExit(1)
    except Exception as exc:
        print(f'Bot belum dapat berjalan ({type(exc).__name__}). Periksa pengaturan dan koneksi.')
        raise SystemExit(1)


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
    main()
