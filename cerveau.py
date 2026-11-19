"""Mon cerveau : stockage local, serveur PC et synchronisation Android."""
import argparse
import base64
import binascii
import contextlib
import datetime as dt
import fcntl
import getpass
import hashlib
import http.server
import io
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import struct
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit
import uuid

WEB = Path(__file__).resolve().parent / 'web'
MAX_AUDIO = 24 * 1024 * 1024
MAX_REQUEST = MAX_AUDIO + 2 * 1024 * 1024
LAN_NETWORKS = tuple(ipaddress.ip_network(network) for network in ('192.168.0.0/16', '10.0.0.0/8', '172.16.0.0/12'))
FIELDS = ('id', 'kind', 'title', 'body', 'when', 'done', 'pinned', 'source', 'audio', 'deleted', 'annotations')
MAX_ANNOTATIONS = 200


class Conflict(Exception):
    def __init__(self, current):
        self.current = current
        super().__init__("La fiche a changé depuis sa lecture.")


def validate_annotations(entries):
    if not isinstance(entries, list):
        raise ValueError('annotations doit être une liste.')
    if len(entries) > MAX_ANNOTATIONS:
        raise ValueError('Trop d’annotations sur cette fiche.')
    cleaned = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Chaque annotation doit être un objet JSON.')
        ann_id = entry.get('id', '')
        text = entry.get('text', '')
        at = entry.get('at', '')
        author = entry.get('author', '')
        if not isinstance(ann_id, str) or not re.fullmatch(r'[A-Za-z0-9_.:@-]{1,128}', ann_id):
            raise ValueError('Identifiant d’annotation invalide.')
        if not isinstance(text, str) or not text.strip() or len(text) > 4096:
            raise ValueError('Le texte d’une annotation doit contenir entre 1 et 4096 caractères.')
        if not isinstance(at, str) or len(at) > 64:
            raise ValueError('Horodatage d’annotation invalide.')
        if at:
            try:
                dt.datetime.fromisoformat(at)
            except ValueError:
                raise ValueError('Horodatage ISO d’annotation attendu.') from None
        if not isinstance(author, str) or len(author) > 64:
            raise ValueError('Auteur d’annotation invalide.')
        cleaned.append({'id': ann_id, 'text': text.strip(), 'at': at, 'author': author.strip()})
    return cleaned


def validate(item):
    if not isinstance(item, dict):
        raise ValueError('Fiche JSON attendue.')
    result = {}
    for key in FIELDS:
        if key in ('done', 'pinned', 'deleted'):
            value = item.get(key, False)
            if type(value) is not bool:
                raise ValueError(f'{key} doit être un booléen.')
        elif key == 'annotations':
            value = validate_annotations(item.get(key, []))
        else:
            value = item.get(key, '')
            if not isinstance(value, str):
                raise ValueError(f'{key} doit être du texte.')
            limit = {'audio': MAX_AUDIO, 'id': 128, 'title': 8192, 'when': 64}.get(key, 512 * 1024)
            if len(value) > limit:
                raise ValueError(f'{key} dépasse la taille autorisée.')
        result[key] = value
    if not re.fullmatch(r'[A-Za-z0-9_.:@-]{1,128}', result['id']):
        raise ValueError('Identifiant de fiche invalide.')
    if result['kind'] not in ('note', 'task', 'event', 'review'):
        raise ValueError('Type de fiche inconnu.')
    if result['when']:
        try:
            dt.datetime.fromisoformat(result['when'])
        except ValueError:
            raise ValueError('Date ISO attendue.') from None
    if type(item.get('rev', 0)) is not int or item.get('rev', 0) < 0:
        raise ValueError('Révision entière positive ou nulle attendue.')
    if result['audio'] and not re.match(r'^data:audio/[\w.+-]+(?:;[\w.+=,-]+)*;base64,', result['audio']):
        raise ValueError('Format audio attendu : data URL audio en base64.')
    return result


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.path = self.directory / 'cerveau.sqlite3'
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript("""
                CREATE TABLE IF NOT EXISTS media (hash TEXT PRIMARY KEY, audio TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions (
                    seq INTEGER PRIMARY KEY, id TEXT NOT NULL, rev INTEGER NOT NULL,
                    data TEXT NOT NULL, modified TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(id,rev)
                );
                CREATE TABLE IF NOT EXISTS heads (id TEXT PRIMARY KEY, seq INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS changed ON heads(seq);
            """)
        self.path.chmod(0o600)

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20, isolation_level=None)
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def unpack(db, data, rev, summary=False):
        item = json.loads(data)
        item.setdefault('annotations', [])
        if summary:
            item['hasAudio'] = bool(item['audio'])
            item['audio'] = ''
        elif item['audio']:
            item['audio'] = db.execute('SELECT audio FROM media WHERE hash=?', (item['audio'],)).fetchone()[0]
        return dict(item, rev=rev)

    def get(self, item_id):
        with self.connect() as db:
            row = db.execute('SELECT data,rev FROM revisions JOIN heads USING(seq) WHERE heads.id=?', (item_id,)).fetchone()
            return self.unpack(db, *row) if row else None

    def history(self, item_id, summary=False):
        with self.connect() as db:
            return [dict(self.unpack(db, data, rev, summary=summary), modified=modified) for data, rev, modified in db.execute(
                'SELECT data,rev,modified FROM revisions WHERE id=? ORDER BY rev', (item_id,))]

    def list_items(self, since=0):
        items, cursor, _ = self.page(since)
        return items, cursor

    def page(self, since, limit=None, summary=False):
        with self.connect() as db:
            db.execute('BEGIN')
            high = db.execute('SELECT COALESCE(MAX(seq),0) FROM revisions').fetchone()[0]
            rows = db.execute(
                'SELECT data,rev,seq FROM heads JOIN revisions USING(seq) WHERE seq>? ORDER BY seq LIMIT ?',
                (since, -1 if limit is None else limit + 1))
            items = []
            cursor = high
            for data,rev,seq in rows:
                if limit is not None and len(items) == limit:
                    return items, cursor, True
                items.append(self.unpack(db, data, rev, summary))
                cursor = seq
            return items, high, False

    @staticmethod
    def append(db, item, rev):
        seq = db.execute('INSERT INTO revisions(id,rev,data) VALUES(?,?,?)',
                         (item['id'], rev, json.dumps(item, ensure_ascii=False))).lastrowid
        db.execute('INSERT OR REPLACE INTO heads(id,seq) VALUES(?,?)', (item['id'], seq))

    def save(self, item):
        packed = validate(item)
        audio = packed['audio']
        if audio:
            packed['audio'] = hashlib.sha256(audio.encode()).hexdigest()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT data,rev FROM heads JOIN revisions USING(seq) WHERE heads.id=?', (packed['id'],)).fetchone()
            current_rev = row[1] if row else 0
            if row:
                existing = json.loads(row[0])
                existing.setdefault('annotations', [])
                if existing == packed:
                    db.commit()
                    return dict(packed, audio=audio, rev=current_rev)
            if item.get('rev', 0) != current_rev:
                raise Conflict(self.unpack(db, *row) if row else None)
            if audio and not db.execute('SELECT 1 FROM media WHERE hash=?', (packed['audio'],)).fetchone():
                try:
                    base64.b64decode(audio.split(',', 1)[1], validate=True)
                except (binascii.Error, ValueError):
                    raise ValueError('Audio base64 illisible.') from None
                db.execute('INSERT INTO media VALUES(?,?)', (packed['audio'], audio))
            if packed['pinned'] and not packed['deleted']:
                for data, rev in db.execute("""
                    SELECT data,rev FROM heads JOIN revisions USING(seq)
                    WHERE heads.id<>? AND json_extract(data,'$.pinned') AND NOT json_extract(data,'$.deleted')
                """, (packed['id'],)).fetchall():
                    previous = json.loads(data)
                    previous['pinned'] = False
                    self.append(db, previous, rev + 1)
            self.append(db, packed, current_rev + 1)
            db.commit()
        return dict(packed, audio=audio, rev=current_rev + 1)


def certificate(directory):
    path, key = directory / 'pc.crt', directory / 'pc.key'
    with (directory / '.certificate-lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.is_file() and key.is_file():
            return path, key
        with tempfile.TemporaryDirectory(dir=directory) as tmp:
            crt_tmp, key_tmp = Path(tmp) / 'cert', Path(tmp) / 'key'
            subprocess.run(['openssl', 'req', '-new', '-newkey', 'rsa:3072', '-nodes', '-x509',
                            '-sha256', '-days', '825', '-subj', '/CN=Mon cerveau PC', '-out',
                            str(crt_tmp), '-keyout', str(key_tmp)], check=True, stderr=subprocess.PIPE)
            key_tmp.chmod(0o600)
            os.replace(key_tmp, key)
            os.replace(crt_tmp, path)
    return path, key


def pair(store, url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.path not in ('', '/') or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('Indiquer l’adresse HTTPS du PC, sans chemin.')
    cert, _ = certificate(store.directory)
    digest = hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()
    token = secrets.token_urlsafe(32)
    devices = store.directory / 'devices'
    devices.mkdir(mode=0o700, exist_ok=True)
    (devices / hashlib.sha256(token.encode()).hexdigest()).touch(mode=0o600)
    return {'url': url.rstrip('/'), 'token': token, 'fingerprint': digest}



def desktop_pairing(bind, store):
    if bind is None:
        raise RuntimeError('La synchronisation Wi-Fi est désactivée. Relancer le service PC avec serve --lan.')
    host, port = bind
    if host == '0.0.0.0':
        host = home_lan_address()
    if not host or not any(ipaddress.ip_address(host) in network for network in LAN_NETWORKS):
        raise RuntimeError('Adresse Wi-Fi privée introuvable. Se connecter au réseau du téléphone, puis relancer avec serve --lan --lan-host ADRESSE_DU_PC.')
    config = pair(store, f'https://{host}:{port}')
    try:
        import qrcode
        import PIL.Image
    except ImportError:
        return config
    png = io.BytesIO()
    qrcode.make(json.dumps(config, separators=(',', ':'))).save(png, format='PNG')
    return dict(config, qr='data:image/png;base64,' + base64.b64encode(png.getvalue()).decode('ascii'))


def home_lan_address():
    # Choose a connected Wi-Fi interface first, otherwise the physical default route.
    # SIOCGIFADDR reads the kernel address of the interface and transmits no packet.
    interfaces = {name for _, name in socket.if_nameindex()}
    wireless = sorted(n for n in interfaces if (Path('/sys/class/net') / n / 'wireless').exists())
    routes = []
    for line in Path('/proc/net/route').read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) > 7 and fields[1] == '00000000' and int(fields[3], 16) & 1:
            routes.append((int(fields[6]), fields[0]))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        for name in dict.fromkeys(wireless + [n for _, n in sorted(routes)]):
            if name.startswith(('docker', 'veth', 'tun', 'wg', 'tailscale')):
                continue
            try:
                request = struct.pack('256s', os.fsencode(name)[:15])
                result = fcntl.ioctl(sock.fileno(), 0x8915, request)
            except OSError:
                continue
            address = ipaddress.ip_address(result[20:24])
            if any(address in network for network in LAN_NETWORKS):
                return str(address)
    return None

def json_out(value):
    print(json.dumps(value, ensure_ascii=False))


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, bind, store, lan=False):
        self.store = store
        self.lan = lan
        self.pairing_bind = None
        super().__init__(bind, Handler)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'MonCerveau'
    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, fmt, *args):
        pass

    def send(self, code, body, media='application/json; charset=utf-8'):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', media)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' data: blob:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        if self.server.lan:
            auth = self.headers.get('Authorization', '')
            if re.fullmatch(r'Bearer [A-Za-z0-9_-]{43}', auth):
                digest = hashlib.sha256(auth[7:].encode()).hexdigest()
                if (self.server.store.directory / 'devices' / digest).is_file():
                    return True
            self.send(401, {'error': 'Appairage requis.'})
            return False
        port = self.server.server_port
        good_hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if port == 80:
            good_hosts |= {'127.0.0.1','localhost'}
        host = self.headers.get('Host', '')
        origin = self.headers.get('Origin')
        if host not in good_hosts or (origin is not None and origin != f'http://{host}') or self.headers.get('Sec-Fetch-Site') == 'cross-site':
            self.send(403, {'error': 'Origine locale requise.'})
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        request = urlsplit(self.path)
        params = parse_qs(request.query)
        if request.path == '/api/item':
            item = self.server.store.get(params.get('id',[''])[0])
            return self.send(200, {'item': item}) if item else self.send(404, {'error': 'Fiche introuvable.'})
        if request.path == '/api/history' and not self.server.lan:
            revisions = self.server.store.history(params.get('id', [''])[0], summary=True)
            return self.send(200, {'history': revisions}) if revisions else self.send(404, {'error': 'Fiche introuvable.'})
        if request.path == '/api/items':
            try:
                since = int(params.get('since', ['0'])[0])
                limit = int(params['limit'][0]) if 'limit' in params else None
                if limit is not None and not 1 <= limit <= 1000:
                    raise ValueError()
                if not 0 <= since <= 2**63-1:
                    raise ValueError()
            except ValueError:
                return self.send(400, {'error': 'Curseur incorrect.'})
            items, cursor, more = self.server.store.page(since, limit, params.get('audio') == ['summary'])
            return self.send(200, {'items': items, 'cursor': cursor, 'more': more})
        if request.path == '/api/provider' and not self.server.lan:
            from integrations import provider_info
            return self.send(200, provider_info())
        if not self.server.lan:
            name = request.path.lstrip('/') or 'index.html'
            # Serve only project UI assets, never a path derived from arbitrary directories.
            asset = (WEB / name).resolve()
            if asset.is_relative_to(WEB) and asset.is_file() and not any(s.startswith('.') for s in asset.relative_to(WEB).parts):
                return self.send(200, asset.read_bytes(), mimetypes.guess_type(asset.name)[0] or 'application/octet-stream')
        self.send(404, {'error': 'Introuvable.'})

    def do_POST(self):
        if not self.allowed():
            return
        if self.headers.get_content_type() != 'application/json':
            return self.send(415, {'error': 'Content-Type application/json requis.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_REQUEST:
                return self.send(413, {'error': 'Taille de la requête incorrecte.'})
            doc = json.loads(self.rfile.read(length))
            if not isinstance(doc, dict):
                raise ValueError('Objet JSON attendu.')
            path = urlsplit(self.path).path
            if path == '/api/pair' and not self.server.lan:
                return self.send(200, desktop_pairing(self.server.pairing_bind, self.server.store))
            if path == '/api/items':
                return self.send(200, {'item': self.server.store.save(doc)})
            if not self.server.lan and path in ('/api/analyze','/api/transcribe'):
                item = self.server.store.get(doc.get('id', '') if isinstance(doc.get('id'), str) else '')
                if not item or item['deleted']:
                    return self.send(404, {'error': 'Fiche introuvable.'})
                if path == '/api/analyze':
                    if doc.get('consent') is not True:
                        return self.send(403, {'error': 'Accord explicite requis pour ce message.'})
                    from integrations import analyze_item, provider_info
                    if type(doc.get('rev')) is not int or doc['rev'] != item['rev'] or doc.get('provider') != provider_info()['name']:
                        return self.send(409, {'error': 'La fiche ou le destinataire a changé. Relire la demande.'})
                    return self.send(200, {'result': analyze_item(item)})
                from integrations import transcribe_item
                return self.send(200, {'text': transcribe_item(item)})
            self.send(404, {'error': 'Introuvable.'})
        except Conflict as exc:
            self.send(409, {'error': 'conflict', 'item': exc.current})
        except (ValueError, UnicodeError, RecursionError) as exc:
            self.send(400, {'error': str(exc)})
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            self.send(503, {'error': str(exc)})
        except sqlite3.Error:
            self.send(503, {'error': 'Stockage indisponible. Réessayer.'})


def backup_passphrase(path, confirm=False):
    if path:
        path = Path(path).expanduser()
        if path.stat().st_mode & 0o077:
            raise ValueError('Le fichier de phrase secrète doit être accessible au propriétaire seul (chmod 600).')
        value = path.read_bytes().rstrip(b'\r\n')
    else:
        value = getpass.getpass('Phrase secrète de sauvegarde : ').encode()
        if confirm and value != getpass.getpass('Confirmer la phrase secrète : ').encode():
            raise ValueError('Les phrases secrètes diffèrent.')
    if not value or b'\n' in value or b'\r' in value:
        raise ValueError('Phrase secrète vide ou multiligne.')
    return value


def crypt(source, output, password, encrypt, gnupg):
    args = ['gpg', '--homedir', str(gnupg), '--batch', '--yes', '--no-symkey-cache',
            '--pinentry-mode', 'loopback', '--passphrase-fd', '0', '--output', str(output)]
    args += ['--symmetric', '--cipher-algo', 'AES256'] if encrypt else ['--decrypt']
    proc = subprocess.run(args + [str(source)], input=password + b'\n', capture_output=True)
    if proc.returncode:
        raise ValueError('Échec du chiffrement GPG.' if encrypt else 'Sauvegarde illisible ou phrase secrète incorrecte.')


def backup(store, destination, password):
    destination = Path(destination).expanduser().resolve()
    if destination.exists():
        raise ValueError('Le fichier de sauvegarde existe déjà.')
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Plaintext never leaves the protected application profile.
    with tempfile.TemporaryDirectory(dir=store.directory) as tmp, tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as out:
        out.close()
        try:
            snapshot = Path(tmp) / 'snapshot.sqlite3'
            with store.connect() as db, contextlib.closing(sqlite3.connect(snapshot)) as dest:
                db.backup(dest)
            crypt(snapshot, out.name, password, True, tmp)
            os.link(out.name, destination)
        finally:
            Path(out.name).unlink(missing_ok=True)
    return destination


def restore(directory, source, password):
    directory = Path(directory).expanduser().resolve()
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    if any(directory.iterdir()):
        raise ValueError('Choisir un profil de restauration vide (option --data-dir).')
    with tempfile.TemporaryDirectory(dir=directory) as tmp:
        snapshot = Path(tmp) / 'snapshot.sqlite3'
        crypt(Path(source).expanduser().resolve(), snapshot, password, False, tmp)
        with contextlib.closing(sqlite3.connect(snapshot)) as db:
            db.execute('PRAGMA trusted_schema=OFF')
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise ValueError('Instantané SQLite endommagé.')
            for table, columns in {'heads': {'id','seq'}, 'revisions': {'seq','id','rev','data','modified'},
                                   'media': {'hash','audio'}}.items():
                if {row[1] for row in db.execute(f'PRAGMA table_info({table})')} != columns:
                    raise ValueError('Format de sauvegarde inconnu.')
            if db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('view','trigger') LIMIT 1").fetchone():
                raise ValueError('Schéma de sauvegarde inattendu.')
        snapshot.chmod(0o600)
        os.link(snapshot, directory / 'cerveau.sqlite3')


def start_backup(store, destination, password):
    folder = Path(destination).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError('Brancher le support et créer le répertoire de sauvegarde avant de lancer le service.')
    expected_device = folder.stat().st_dev
    def worker():
        while True:
            filename = folder / f'mon-cerveau-{dt.date.today().isoformat()}.gpg'
            try:
                if folder.stat().st_dev != expected_device:
                    raise OSError('Le support de sauvegarde a changé.')
                if not filename.exists():
                    backup(store, filename, password)
            except (OSError, sqlite3.Error, ValueError) as exc:
                print(f'Sauvegarde quotidienne : {exc}', file=sys.stderr, flush=True)
            time.sleep(3600)
    threading.Thread(target=worker, daemon=True).start()


def serve(store, args):
    if bool(args.backup_dir) != bool(args.passphrase_file):
        raise ValueError('Utiliser --backup-dir avec --passphrase-file.')
    with contextlib.ExitStack() as stack:
        local = stack.enter_context(Server(('127.0.0.1', args.port), store))
        if args.lan:
            cert, key = certificate(store.directory)
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.minimum_version = ssl.TLSVersion.TLSv1_2
            tls.load_cert_chain(cert, key)
            lan = stack.enter_context(Server((args.lan_host, args.lan_port), store, lan=True))
            lan.socket = tls.wrap_socket(lan.socket, server_side=True)
            threading.Thread(target=lan.serve_forever, daemon=True).start()
            stack.callback(lan.shutdown)
            local.pairing_bind = lan.server_address
        if args.backup_dir:
            start_backup(store, args.backup_dir, backup_passphrase(args.passphrase_file))
        import integrations
        if hasattr(integrations, 'start_background'):
            integrations.start_background(store)
        print(f'Mon cerveau : http://127.0.0.1:{local.server_port}', flush=True)
        local.serve_forever()


KIND_LABELS = {'note': 'Note', 'task': 'Tâche', 'event': 'Rendez-vous', 'review': 'À confirmer'}


def format_markdown(item, level=1):
    heading = '#' * level
    lines = [f'{heading} {item["title"]}']
    meta = [f'Type : {KIND_LABELS.get(item["kind"], item["kind"])}']
    if item.get('when'):
        meta.append(f'Date : {item["when"]}')
    if item['kind'] == 'task':
        meta.append('Statut : terminée' if item.get('done') else 'Statut : en cours')
    if item.get('pinned'):
        meta.append('Épinglée : oui')
    if item.get('audio') or item.get('hasAudio'):
        meta.append('Mémo vocal : oui')
    lines.append('- ' + ' · '.join(meta))
    if item.get('body'):
        lines.extend(['', item['body'].strip()])
    if item.get('source'):
        quoted = '\n'.join('> ' + line for line in item['source'].strip().splitlines())
        lines.extend(['', f'{heading}# Message d’origine', quoted])
    annotations = item.get('annotations') or []
    if annotations:
        lines.extend(['', f'{heading}# Annotations'])
        for entry in annotations:
            prefix = ' · '.join(part for part in (entry.get('author'), entry.get('at')) if part)
            lines.append(f'- **[{prefix}]** {entry["text"]}' if prefix else f'- {entry["text"]}')
    return '\n'.join(lines)


def agent_grant_file(store, name):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name):
        raise ValueError('Nom d’agent invalide.')
    return store.directory / 'agents' / name


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    data = Path(os.getenv('XDG_DATA_HOME') or Path.home() / '.local' / 'share') / 'mon-cerveau'
    parser.add_argument('--data-dir', default=str(data), help='Profil personnel hors dépôt')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('serve')
    p.add_argument('--port', type=int, default=8743)
    p.add_argument('--lan', action='store_true', help='Activer la synchronisation HTTPS')
    p.add_argument('--lan-host', default='0.0.0.0')
    p.add_argument('--lan-port', default=8744, type=int)
    p.add_argument('--backup-dir')
    p.add_argument('--passphrase-file')
    sub.add_parser('pair').add_argument('--url', required=True)
    sub.add_parser('unpair-all')
    p = sub.add_parser('list')
    p.add_argument('--kind', choices=['note', 'task', 'event', 'review'])
    p.add_argument('--search', default='')
    sub.add_parser('get').add_argument('id')
    sub.add_parser('history').add_argument('id')
    p = sub.add_parser('annotate')
    p.add_argument('id')
    p.add_argument('text')
    p.add_argument('--author', default='Moi')
    p = sub.add_parser('export')
    p.add_argument('--id')
    p.add_argument('--kind', choices=['note', 'task', 'event', 'review'])
    p.add_argument('--format', choices=['md', 'json'], default='md')
    sub.add_parser('grant-task').add_argument('agent')
    sub.add_parser('revoke-task').add_argument('agent')
    p = sub.add_parser('add-task')
    p.add_argument('--agent', required=True)
    p.add_argument('--id', help='Identifiant stable pour rejouer une demande')
    p.add_argument('--body', default='')
    p.add_argument('title')
    for command in ('backup', 'restore'):
        p = sub.add_parser(command)
        p.add_argument('file')
        p.add_argument('--passphrase-file')
    args = parser.parse_args(argv)
    if args.command == 'restore':
        restore(args.data_dir, args.file, backup_passphrase(args.passphrase_file))
        return
    store = Store(args.data_dir)
    if args.command == 'serve':
        serve(store, args)
    elif args.command == 'pair':
        json_out(pair(store, args.url))
    elif args.command == 'unpair-all':
        for device in (store.directory / 'devices').glob('*'):
            device.unlink()
    elif args.command == 'list':
        text = args.search.casefold()
        items, _ = store.list_items()
        def searchable(item):
            notes = '\n'.join(a['text'] for a in item.get('annotations', []))
            return (item['title'] + '\n' + item['body'] + '\n' + item['source'] + '\n' + notes).casefold()
        json_out([{k: v for k,v in item.items() if k != 'audio'} for item in items
                  if not item['deleted'] and (not args.kind or item['kind'] == args.kind)
                  and text in searchable(item)])
    elif args.command == 'get':
        item = store.get(args.id)
        if not item:
            raise ValueError('Fiche introuvable.')
        json_out(item)
    elif args.command == 'history':
        json_out(store.history(args.id))
    elif args.command == 'annotate':
        item = store.get(args.id)
        if not item or item['deleted']:
            raise ValueError('Fiche introuvable.')
        entry = {
            'id': str(uuid.uuid4()),
            'text': args.text,
            'at': dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
            'author': args.author,
        }
        updated = dict(item, annotations=list(item.get('annotations', [])) + [entry])
        json_out(store.save(updated))
    elif args.command == 'export':
        if args.id:
            item = store.get(args.id)
            if not item or item['deleted']:
                raise ValueError('Fiche introuvable.')
            if args.format == 'json':
                json_out({**{k: v for k, v in item.items() if k != 'audio'}, 'hasAudio': bool(item['audio'])})
            else:
                print(format_markdown(item, level=1))
        else:
            items, _ = store.list_items()
            selected = [i for i in items if not i['deleted'] and (not args.kind or i['kind'] == args.kind)]
            if args.format == 'json':
                json_out([{**{k: v for k, v in i.items() if k != 'audio'}, 'hasAudio': bool(i['audio'])} for i in selected])
            else:
                print('\n\n---\n\n'.join(format_markdown(i, level=2) for i in selected))
    elif args.command in ('grant-task','revoke-task','add-task'):
        grant = agent_grant_file(store, args.agent)
        if args.command == 'grant-task':
            grant.parent.mkdir(mode=0o700, exist_ok=True)
            grant.touch(mode=0o600)
        elif args.command == 'revoke-task':
            grant.unlink(missing_ok=True)
        elif grant.is_file():
            json_out(store.save({'id': args.id or str(uuid.uuid4()), 'kind':'task',
                                 'title':args.title, 'body':args.body, 'source':f'Agent {args.agent}'}))
        else:
            raise ValueError('Cet agent a accès en lecture seule.')
    elif args.command == 'backup':
        print(backup(store, args.file, backup_passphrase(args.passphrase_file, confirm=True)))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (ValueError, OSError, sqlite3.Error, Conflict, subprocess.SubprocessError) as error:
        sys.exit(str(error))
