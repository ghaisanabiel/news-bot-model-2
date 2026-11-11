import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIB = timezone(timedelta(hours=7), 'WIB')


def now():
    return datetime.now(WIB)


def load_env(path=None):
    path = path or ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())


@dataclass
class Config:
    token: str
    pairing_code: str
    model: str = ''
    brand: str = 'ARUS'
    scan_minutes: int = 30
    ai_call_limit: int = 120
    daily_candidates: int = 8

    @classmethod
    def load(cls):
        load_env()
        config = cls(os.getenv('TELEGRAM_BOT_TOKEN', ''),
                     os.getenv('PAIRING_CODE', ''), os.getenv('CODEX_MODEL', ''),
                     os.getenv('BRAND_NAME', 'ARUS'), int(os.getenv('SCAN_MINUTES', '30')),
                     int(os.getenv('AI_CALL_LIMIT', '120')), int(os.getenv('DAILY_CANDIDATES', '8')))
        if not all((config.token, config.pairing_code)):
            raise ValueError('Pengaturan belum lengkap. Jalankan python configure.py terlebih dahulu.')
        if len(config.pairing_code) < 16 or config.scan_minutes < 10 or config.ai_call_limit < 1 or config.daily_candidates < 1:
            raise ValueError('Pengaturan tidak valid: kode minimal 16 karakter, interval minimal 10 menit, batas positif.')
        return config
