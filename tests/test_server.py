from concurrent.futures import ThreadPoolExecutor
import contextlib
import http.client
import hashlib
import ssl
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest

from cerveau import Conflict, Server, Store, backup, certificate, pair, restore


def task(i='t1', **changes):
    return dict({'id': i, 'kind': 'task', 'title': 'Relire la note'}, **changes)


class ServerTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.store = Store(self.root/'profil')

    def test_optimistic_retries_deletion_and_cursor(self):
        initial = self.store.save(task())
        self.assertEqual(self.store.save(task()), initial)
        items, first = self.store.list_items()
        self.assertEqual(items, [initial])
        moved = self.store.save(dict(initial, done=True))
        with self.assertRaises(Conflict) as ctx:
            self.store.save(dict(initial, title='Autre'))
        self.assertEqual(ctx.exception.current, moved)
        self.assertEqual(self.store.list_items(first)[0], [moved])
        deleted = self.store.save(dict(moved, deleted=True))
        self.assertTrue(self.store.list_items()[0][0]['deleted'])
        self.assertEqual([obj['rev'] for obj in self.store.history('t1')], [1,2,3])
        self.assertEqual(self.store.get('t1'), deleted)

    def test_concurrent_edits_and_single_pin(self):
        loaded = self.store.save(task(pinned=True))
        def save_one(title):
            try:
                return self.store.save(dict(loaded, title=title))
            except Conflict:
                return None
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(save_one, ['Deux', 'Trois']))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.store.save(task('t2', pinned=True))
        self.assertFalse(self.store.get('t1')['pinned'])
        self.assertTrue(self.store.get('t2')['pinned'])

    def test_audio_kept_once_and_in_history(self):
        audio = 'data:audio/webm;codecs=opus;base64,YWJj'
        item = self.store.save(task(audio=audio))
        self.store.save(dict(item, body='Transcription'))
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM media').fetchone()[0], 1)
        self.assertEqual(self.store.history('t1')[0]['audio'], audio)
        with self.assertRaises(ValueError):
            self.store.save(task('other', audio='data:audio/wav;base64,???'))
        self.assertIsNone(self.store.get('other'))

    def test_page_without_large_audio_and_next_cursor(self):
        for i in range(3):
            self.store.save(task(f'id-{i}', audio='data:audio/ogg;base64,QUJD'))
        rows,cursor,more = self.store.page(0, limit=1, summary=True)
        self.assertTrue(rows[0]['hasAudio'])
        self.assertEqual(rows[0]['audio'], '')
        self.assertTrue(more)
        middle, cursor, more = self.store.page(cursor, limit=1)
        self.assertEqual(middle[0]['id'], 'id-1')
        self.assertTrue(more)
        final, cursor, more = self.store.page(cursor, limit=1)
        self.assertEqual(final[0]['id'], 'id-2')
        self.assertFalse(more)
        self.assertEqual(self.store.list_items(cursor)[0], [])

    @unittest.skipUnless(shutil.which('gpg'), 'GnuPG requis')
    def test_backup_restore_audio_and_wrong_password(self):
        item = self.store.save(task(audio='data:audio/wav;base64,QUJD'))
        destination = self.root/'archive.gpg'
        backup(self.store, destination, b'phrase de test')
        self.assertNotIn(b'SQLite format', destination.read_bytes())
        restored = self.root/'profil-restaure'
        with self.assertRaises(ValueError):
            restore(restored, destination, b'mauvaise phrase')
        restore(restored, destination, b'phrase de test')
        self.assertEqual(Store(restored).get('t1'), item)
        with self.assertRaises(ValueError):
            restore(restored, destination, b'phrase de test')

    def request(self, srv, method, path, payload=None, **headers):
        with contextlib.closing(http.client.HTTPConnection('127.0.0.1', srv.server_port, timeout=5)) as client:
            if payload is not None:
                headers.setdefault('Content-Type', 'application/json')
            client.request(method, path, None if payload is None else json.dumps(payload), headers)
            response = client.getresponse()
            data = json.loads(response.read())
            return response.status, data

    @contextlib.contextmanager
    def running(self, lan=False):
        with Server(('127.0.0.1',0), self.store, lan=lan) as srv:
            worker = threading.Thread(target=srv.serve_forever)
            worker.start()
            try:
                yield srv
            finally:
                srv.shutdown()
                worker.join()

    def test_local_route_validation(self):
        with self.running() as srv:
            self.assertEqual(self.request(srv,'POST','/api/pair',{})[0],503)
            srv.pairing_bind = ('127.0.0.1',8744)
            self.assertEqual(self.request(srv,'POST','/api/pair',{})[0],503)
            srv.pairing_bind = ('192.168.1.10',8744)
            status,config = self.request(srv,'POST','/api/pair',{})
            self.assertEqual(status,200)
            self.assertEqual(config['url'],'https://192.168.1.10:8744')
            self.assertRegex(config['fingerprint'],'^[a-f0-9]{64}$')
            self.assertRegex(config['token'],'^[A-Za-z0-9_-]{43}$')
            if 'qr' in config:
                self.assertTrue(config['qr'].startswith('data:image/png;base64,'))
            self.assertEqual(self.request(srv,'POST','/api/pair',{},Origin='https://other.example')[0],403)
            self.assertEqual(self.request(srv,'GET','/api/items',Host='other.example')[0],403)
            self.assertEqual(self.request(srv,'POST','/api/items',task(),Origin='http://elsewhere.example')[0],403)
            self.assertEqual(self.request(srv,'POST','/api/items',task(),**{'Content-Type':'text/plain'})[0],415)
            self.assertEqual(self.request(srv,'POST','/api/items',task())[0],200)
            self.assertEqual(self.request(srv,'POST','/api/items',task(title='Révision dépassée'))[0],409)
            self.assertEqual(self.request(srv,'POST','/api/analyze',{'id':'t1','consent':False})[0],403)
            self.assertEqual(self.request(srv,'POST','/api/analyze',{'id':'t1','rev':9,'provider':'test','consent':True})[0],409)
            self.assertEqual(self.request(srv,'GET','/api/items?since=0')[1]['items'][0]['title'],'Relire la note')

    @unittest.skipUnless(shutil.which('openssl'), 'OpenSSL requis')
    def test_paired_api(self):
        pairing = pair(self.store,'https://192.0.2.1:8744')
        self.assertRegex(pairing['fingerprint'], '^[a-f0-9]{64}$')
        token = {'Authorization':'Bearer ' + pairing['token']}
        with Server(('127.0.0.1',0),self.store,lan=True) as srv:
            cert,key = certificate(self.store.directory)
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(cert,key)
            srv.socket = tls.wrap_socket(srv.socket,server_side=True)
            worker = threading.Thread(target=srv.serve_forever)
            worker.start()
            try:
                context = ssl.create_default_context(cafile=str(cert))
                context.check_hostname = False
                with contextlib.closing(http.client.HTTPSConnection('127.0.0.1',srv.server_port,context=context)) as client:
                    client.connect()
                    peer = client.sock.getpeercert(binary_form=True)
                    self.assertEqual(hashlib.sha256(peer).hexdigest(),pairing['fingerprint'])
                    client.request('GET','/api/items',headers=token)
                    self.assertEqual(client.getresponse().status,200)
            finally:
                srv.shutdown()
                worker.join()
        with self.running(lan=True) as srv:
            self.assertEqual(self.request(srv,'GET','/api/items')[0],401)
            self.assertEqual(self.request(srv,'POST','/api/items',task(),**token)[0],200)
            self.assertEqual(self.request(srv,'GET','/api/items',**token)[1]['cursor'],1)
            self.assertEqual(self.request(srv,'GET','/api/history?id=t1',**token)[0],404)
            self.assertEqual(self.request(srv,'POST','/api/analyze',{'id':'t1','consent':True},**token)[0],404)
            self.assertEqual(self.request(srv,'GET','/',**token)[0],404)
            self.assertEqual(self.request(srv,'POST','/api/pair',{},**token)[0],404)

    def test_annotations_history_api_and_cli_export(self):
        import io
        from cerveau import main
        created = self.store.save(task(
            'r1',
            kind='review',
            title='Confirmer la livraison',
            source='SMS · Livraison prévue vendredi matin',
            annotations=[{'id': 'a1', 'text': 'Demander le créneau exact', 'at': '2026-05-01T09:00:00Z', 'author': 'Moi'}],
        ))
        self.assertEqual(len(created['annotations']), 1)
        with self.assertRaises(ValueError):
            self.store.save(task('bad-ann', annotations=[{'id': 'a1', 'text': '   '}]))
        with self.assertRaises(ValueError):
            self.store.save(task('bad-ann-id', annotations=[{'id': 'bad id!', 'text': 'ok'}]))

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main(['--data-dir', str(self.store.directory), 'annotate', 'r1', 'Code portail 4821', '--author', 'Note'])
        annotated = json.loads(out.getvalue())
        self.assertEqual(annotated['rev'], 2)
        self.assertEqual(len(annotated['annotations']), 2)

        search_out = io.StringIO()
        with contextlib.redirect_stdout(search_out):
            main(['--data-dir', str(self.store.directory), 'list', '--search', 'portail'])
        found = json.loads(search_out.getvalue())
        self.assertEqual([i['id'] for i in found], ['r1'])

        md_out = io.StringIO()
        with contextlib.redirect_stdout(md_out):
            main(['--data-dir', str(self.store.directory), 'export', '--id', 'r1', '--format', 'md'])
        md = md_out.getvalue()
        self.assertIn('# Confirmer la livraison', md)
        self.assertIn('## Message d’origine', md)
        self.assertIn('## Annotations', md)
        self.assertIn('Code portail 4821', md)

        with self.running() as srv:
            status, payload = self.request(srv, 'GET', '/api/history?id=r1')
            self.assertEqual(status, 200)
            self.assertEqual([r['rev'] for r in payload['history']], [1, 2])
            self.assertEqual(self.request(srv, 'GET', '/api/history?id=missing')[0], 404)


if __name__ == '__main__':
    unittest.main()
