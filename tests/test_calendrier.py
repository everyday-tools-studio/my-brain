import contextlib
from pathlib import Path
import tempfile
import unittest

from calendrier import coordinates, read_event, sync, write_event
from cerveau import Store


class MemoryCalendar:
    url = "https://example.invalid/agenda/"

    def __init__(self):
        self.rows = {}
        self.version = 0

    def contents(self):
        return dict(self.rows)

    @contextlib.contextmanager
    def request(self, method, href, data=None, **headers):
        if href in self.rows:
            assert headers.get("If-Match") == self.rows[href][0]
        else:
            assert headers.get("If-None-Match") == "*"
        self.version += 1
        tag = f'"{self.version}"'
        if method == "DELETE":
            del self.rows[href]
        else:
            self.rows[href] = (tag, data.decode())
        yield type("Response",(),{"headers":{"ETag":tag}})()


class CalendarTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name))
        self.remote = MemoryCalendar()
        self.event = self.store.save({"id":"rdv-1","kind":"event","title":"Réunion","when":"2026-11-19T11:30:00+01:00","source":"SMS confidentiel"})

    def test_roundtrip_edit_and_delete(self):
        sync(self.store, self.remote)
        href, (etag, ics) = next(iter(self.remote.rows.items()))
        self.assertNotIn("confidentiel", ics)
        self.assertEqual(read_event(ics)[2],coordinates(self.event))
        self.remote.rows[href] = ('"remote"',ics.replace("Réunion","Dentiste"))
        sync(self.store, self.remote)
        current = self.store.get("rdv-1")
        self.assertEqual(current["title"],"Dentiste")
        self.assertEqual(current["source"],"SMS confidentiel")
        self.store.save({**current,"deleted":True})
        sync(self.store,self.remote)
        self.assertEqual(self.remote.rows,{})
        self.assertEqual(sync(self.store,self.remote),[])

    def test_remote_creation_deletion(self):
        foreign = self.remote.url+"z.ics"
        self.remote.rows[foreign] = ('"1"',write_event({**self.event,"id":"foreign"},None).decode())
        sync(self.store,self.remote)
        imported = next(i for i in self.store.list_items()[0] if i["id"]!="rdv-1")
        del self.remote.rows[foreign]
        sync(self.store,self.remote)
        self.assertTrue(self.store.get(imported["id"])["deleted"])

    def test_conflict_requires_choice(self):
        sync(self.store,self.remote)
        href, (_, ics) = next(iter(self.remote.rows.items()))
        self.remote.rows[href] = ('"remote"',ics.replace("Réunion","Autre titre"))
        self.store.save({**self.event,"title":"Titre local"})
        self.assertTrue(sync(self.store,self.remote)[0].startswith("Conflit"))
        self.assertEqual(self.store.get("rdv-1")["title"],"Titre local")
        sync(self.store,self.remote,("rdv-1","distant"))
        self.assertEqual(self.store.get("rdv-1")["title"],"Autre titre")
