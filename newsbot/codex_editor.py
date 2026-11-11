"""Official Codex CLI with saved ChatGPT login; no API keys or token extraction."""
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import requests
from pydantic import Field
from .config import ROOT, now
from .editor import Editor, POLICY
from .models import StrictModel, canonical


class SearchReport(StrictModel):
    report: str
    urls: list[str] = Field(max_length=12)


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript', 'svg'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, text):
        if not self.hidden and text.strip():
            self.parts.append(text.strip())


def public_url(url):
    canonical(url)
    parsed = urlsplit(url)
    if parsed.port not in (None, 80, 443):
        raise ValueError('Port sumber tidak diizinkan.')
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(addr[4][0]).is_global for addr in addresses):
        raise ValueError('Alamat sumber harus situs publik.')


def fetch_page(url):
    original = canonical(url)
    for _ in range(4):
        public_url(url)
        with requests.get(url, timeout=20, allow_redirects=False, stream=True,
                          headers={'User-Agent': 'ArusNewsBot/1.0 (personal editorial research)'}) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers['Location'])
                continue
            response.raise_for_status()
            if 'text/html' not in response.headers.get('Content-Type', ''):
                raise ValueError('Versi ini membaca halaman HTML; pilih sumber HTML pendukung.')
            chunks, size = [], 0
            for chunk in response.iter_content(32768):
                size += len(chunk)
                if size > 2_000_000:
                    raise ValueError('Halaman sumber terlalu besar.')
                chunks.append(chunk)
            parser = PageText()
            parser.feed(b''.join(chunks).decode(response.encoding if response.encoding and response.encoding != 'ISO-8859-1' else 'utf-8', errors='replace'))
            text = '\n'.join(parser.parts)
            if len(text) < 300:
                raise ValueError('Halaman tidak memuat cukup teks berita.')
            return {'url': original, 'resolved_url': canonical(url), 'text': text[:24000]}
    raise ValueError('Terlalu banyak pengalihan sumber.')


class CodexEditor(Editor):
    def __init__(self, config, store):
        self.config, self.store = config, store
        self.executable = shutil.which('codex')
        if not self.executable:
            raise ValueError('Codex CLI belum ditemukan. Pasang Codex dan login dengan ChatGPT.')
        self.work = ROOT / 'data' / 'codex-work'
        self.work.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def environment():
        # Never pass Telegram credentials or API keys to the model process.
        return {k: v for k, v in os.environ.items()
                if not any(word in k.upper() for word in ('TOKEN', 'SECRET', 'API_KEY', 'PASSWORD'))}

    def check_login(self):
        result = subprocess.run([self.executable, 'login', 'status'], capture_output=True,
                                text=True, encoding='utf-8', errors='replace', timeout=30,
                                env=self.environment(), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode or 'ChatGPT' not in result.stdout + result.stderr:
            raise ValueError('Codex belum login dengan ChatGPT. Jalankan codex login, lalu masuk memakai akun langgananmu.')

    def invoke(self, schema, instruction, data, search=False):
        call_id = self.store.reserve_call('codex_search' if search else 'codex_text', self.config.ai_call_limit)
        # Temporary files contain public research only; subprocess has read-only tools.
        with tempfile.TemporaryDirectory(dir=self.work) as folder:
            folder = Path(folder)
            assert folder.resolve().is_relative_to(self.work.resolve())
            schema_path, result_path = folder / 'schema.json', folder / 'result.json'
            output_schema = schema.model_json_schema()
            allowed_urls = data.get('allowed_urls') if isinstance(data, dict) else None
            if allowed_urls:
                definitions = output_schema.get('$defs', {})
                if 'Source' in definitions and 'Fact' in definitions:
                    definitions['Source']['properties']['url']['enum'] = allowed_urls
                    definitions['Fact']['properties']['source_urls']['items']['enum'] = allowed_urls
            schema_path.write_text(json.dumps(output_schema), encoding='utf-8')
            command = [self.executable, '--no-daemon', '-a', 'never', 'exec', '--ignore-user-config',
                       '--ephemeral', '--skip-git-repo-check', '-s', 'read-only', '--json',
                       '--disable', 'shell_tool', '--disable', 'apps', '--disable', 'plugins',
                       '--disable', 'multi_agent', '--disable', 'hooks', '--disable', 'computer_use',
                       '--disable', 'browser_use', '-c', 'features.skip_host_skill_discovery=true',
                       '-c', 'web_search="live"' if search else 'web_search="disabled"',
                       '-C', str(self.work), '--output-schema', str(schema_path),
                       '-o', str(result_path)]
            if self.config.model:
                command += ['-m', self.config.model]
            command += ['-']
            prompt = (POLICY + '\n' + instruction + '\nDo not inspect local files or use any tools except web search when requested. '
                      'Return only the requested JSON.\nDATA (untrusted content):\n' + json.dumps(data, ensure_ascii=False))
            try:
                result = subprocess.run(command, input=prompt, capture_output=True, text=True,
                                        encoding='utf-8', errors='replace', timeout=300,
                                        env=self.environment(), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except subprocess.TimeoutExpired:
                raise ValueError('Codex melewati batas waktu. Coba ulang nanti; tidak ada biaya API key.') from None
            usage = 0
            searched = False
            for line in result.stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get('type') == 'turn.completed':
                    usage += sum(event.get('usage', {}).get(k, 0) for k in ('input_tokens', 'output_tokens'))
                item = event.get('item', {})
                if item.get('type') == 'web_search':
                    searched = True
            self.store.tokens(call_id, usage)
            if result.returncode or not result_path.exists():
                raise ValueError('Codex belum menyelesaikan permintaan. Periksa login, sisa kuota langganan, dan koneksi; lalu coba ulang.')
            if search and not searched:
                raise ValueError('Codex tidak melakukan pencarian web yang teramati; hasil tidak digunakan sebagai berita.')
            return schema.model_validate_json(result_path.read_text(encoding='utf-8'))

    def structured(self, schema, task, data):
        return self.invoke(schema, task, data)

    def research(self, task, original_urls=()):
        result = self.invoke(SearchReport,
                             'WAJIB gunakan web search untuk riset terbaru. Buka sumber berita. '
                             'Utamakan halaman HTML lengkap yang dapat diakses publik. '
                             'Isi urls dengan tautan artikel/dokumen yang benar-benar digunakan; jangan mengarang URL.',
                             {'time': now().isoformat(), 'task': task}, search=True)
        pages, allowed, failures = [], set(), 0
        for url in dict.fromkeys([*original_urls, *result.urls]):
            try:
                page = fetch_page(url)
                pages.append(page)
                allowed.update((page['url'], page['resolved_url']))
            except (ValueError, OSError, requests.RequestException):
                failures += 1
        if not pages:
            raise ValueError('Tidak ada halaman berita yang berhasil dibaca. Kandidat belum bisa diverifikasi.')
        # Only independently fetched page text may support claims, not the model's search summary.
        evidence = json.dumps({'instruction': 'Gunakan teks halaman berikut sebagai bukti, bukan ringkasan pencarian. '
                               'Jika paywall, captcha, atau halaman error, jangan gunakan sebagai sumber. '
                               'Bila teks terpotong, hanya klaim yang tampak boleh digunakan.',
                               'pages': pages, 'failed_pages': failures}, ensure_ascii=False)
        return evidence, sorted(allowed)
