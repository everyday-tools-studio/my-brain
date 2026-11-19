"""Bidirectional sync of simple timed events in one explicitly selected CalDAV collection."""
import argparse
import base64
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, build_opener
from xml.etree import ElementTree as ET
from uuid import NAMESPACE_URL, uuid5

from integrations import NoRedirect

DAV = "{DAV:}"
CAL = "{urn:ietf:params:xml:ns:caldav}"
QUERY = b'''<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/><c:calendar-data/></d:prop><c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT"/></c:comp-filter></c:filter></c:calendar-query>'''


def coordinates(value):
    if not value or value["kind"] != "event" or value.get("deleted") or not value.get("when"):
        return None
    return [value["title"], dt.datetime.fromisoformat(value["when"]).astimezone(dt.timezone.utc).isoformat()]


class Collection:
    def __init__(self, url, user, password):
        self.url = url.rstrip("/") + "/"
        parts = urlsplit(self.url)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.query or parts.fragment:
            raise ValueError("URL HTTPS de collection CalDAV attendue.")
        self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()

    def request(self, verb, href, data=None, **headers):
        url = urljoin(self.url, href)
        if not url.startswith(self.url):
            raise ValueError("Ressource extérieure au calendrier sélectionné.")
        req = Request(url, method=verb, data=data, headers={"Authorization": self.auth, **headers})
        return build_opener(NoRedirect()).open(req, timeout=25)

    def contents(self):
        with self.request("REPORT", self.url, QUERY, Depth="1", **{"Content-Type":"application/xml"}) as response:
            if response.status != 207:
                raise ValueError("Réponse multistatut CalDAV attendue.")
            document = ET.fromstring(response.read(32 * 1024 * 1024))
        if document.tag != DAV + "multistatus":
            raise ValueError("Liste CalDAV incomplète.")
        resources = {}
        for row in document.findall(DAV+"response"):
            href = urljoin(self.url, row.findtext(DAV+"href") or "")
            if href == self.url:
                continue
            props = next((p.find(DAV+"prop") for p in row.findall(DAV+"propstat")
                          if " 200 " in (p.findtext(DAV+"status") or "") and p.find(".//"+CAL+"calendar-data") is not None), None)
            if props is None or not props.findtext(DAV+"getetag") or not props.findtext(CAL+"calendar-data"):
                raise ValueError("Lecture incomplète du calendrier distant. Réessayer.")
            resources[href] = (props.findtext(DAV+"getetag"), props.findtext(CAL+"calendar-data"))
        return resources


def read_event(ics):
    from icalendar import Calendar
    cal = Calendar.from_ical(ics)
    events = cal.walk("VEVENT")
    if len(events) != 1:
        return None
    event = events[0]
    if any(key in event for key in ("RRULE", "RDATE", "RECURRENCE-ID", "ATTENDEE", "ORGANIZER")) or not event.get("DTSTART"):
        return None
    start = event.decoded("DTSTART")
    if not isinstance(start, dt.datetime):
        return None
    return cal, event, [str(event.get("SUMMARY") or "Rendez-vous"), start.astimezone(dt.timezone.utc).isoformat()]


def write_event(item, original):
    from icalendar import Calendar, Event
    start = dt.datetime.fromisoformat(item["when"]).astimezone(dt.timezone.utc)
    if original:
        cal, event, _ = read_event(original)
        if "DTEND" in event:
            duration = event.decoded("DTEND") - event.decoded("DTSTART")
            del event["DTEND"]
            event.add("dtend", start + duration)
    else:
        cal, event = Calendar(), Event()
        cal.add("prodid", "-//Mon cerveau//FR")
        cal.add("version", "2.0")
        cal.add_component(event)
        event.add("uid", item["id"]+"@mon-cerveau")
    for key, value in (("dtstart", start), ("summary", item["title"]), ("dtstamp", dt.datetime.now(dt.timezone.utc))):
        event.pop(key.upper(), None)
        event.add(key, value)
    return cal.to_ical()


def sync(store, remote, resolve=None):
    # The bindings share the application database so encrypted backups include sync history.
    changes = []
    with (store.directory / ".caldav-lock").open("a") as lock, store.connect() as db:
        fcntl.flock(lock, fcntl.LOCK_EX)
        db.execute("CREATE TABLE IF NOT EXISTS calendar_bindings (collection TEXT, href TEXT, id TEXT, signature TEXT, etag TEXT, PRIMARY KEY(collection,href))")
        bindings = {h:(i,json.loads(s),t) for h,i,s,t in db.execute(
            "SELECT href,id,signature,etag FROM calendar_bindings WHERE collection=?", (remote.url,))}
        other = db.execute("SELECT 1 FROM calendar_bindings WHERE collection<>? LIMIT 1",(remote.url,)).fetchone()
        if other:
            raise ValueError("Ce profil est déjà lié à un autre calendrier.")
        items = {i["id"]:i for i in store.list_items()[0]}
        remote_items = remote.contents()
        local_ids = {v[0] for v in bindings.values()}
        for item in items.values():
            if item["id"] not in local_ids and coordinates(item):
                href = urljoin(remote.url, item["id"]+".ics")
                bindings[href] = (item["id"], None, None)
        for href in sorted(set(bindings) | set(remote_items)):
            key, baseline, old_etag = bindings.get(href, (str(uuid5(NAMESPACE_URL,href)),None,None))
            item = items.get(key)
            local = coordinates(item)
            etag, ics = remote_items.get(href,(None,None))
            parsed = read_event(ics) if ics else None
            if ics and parsed is None:
                continue
            distant = parsed[2] if parsed else None
            if local != distant:
                local_changed = local != baseline
                remote_changed = distant != baseline
                if local_changed and remote_changed:
                    choice = resolve[1] if resolve and resolve[0] == key else None
                    if not choice:
                        changes.append(f"Conflit {key} : choisir local ou distant.")
                        continue
                    local_changed = choice == "local"
                if local_changed:
                    headers = {"If-Match":etag} if etag else {"If-None-Match":"*"}
                    if local:
                        with remote.request("PUT", href, write_event(item,ics), **headers, **{"Content-Type":"text/calendar; charset=utf-8"}) as res:
                            etag = res.headers.get("ETag")
                    else:
                        with remote.request("DELETE",href, **headers):
                            pass
                    changes.append("Export "+key)
                else:
                    if distant:
                        store.save({**(item or {}), "id":key, "kind":"event","title":distant[0],"when":distant[1],"deleted":False})
                    elif item:
                        store.save({**item, "deleted":True})
                    local = distant
                    changes.append("Import "+key)
            if local:
                db.execute("INSERT OR REPLACE INTO calendar_bindings VALUES (?,?,?,?,?)", (remote.url,href,key,json.dumps(local),etag))
            else:
                db.execute("DELETE FROM calendar_bindings WHERE collection=? AND href=?", (remote.url,href))
    return changes


def main():
    from cerveau import Store
    parser = argparse.ArgumentParser(description="Synchroniser le calendrier CalDAV sélectionné.")
    parser.add_argument("--data-dir", required=True, type=Path, help="Même répertoire que le service Mon cerveau.")
    parser.add_argument("--watch", action="store_true", help="Répéter toutes les deux minutes.")
    parser.add_argument("--resolve", nargs=2, metavar=("ID","local|distant"))
    args = parser.parse_args()
    if args.resolve and args.resolve[1] not in ("local","distant"):
        parser.error("Choisissez local ou distant.")
    try:
        remote = Collection(*(os.environ[k] for k in ("CERVEAU_CALDAV_URL","CERVEAU_CALDAV_USER","CERVEAU_CALDAV_PASSWORD")))
    except KeyError as err:
        parser.error("Variable manquante : "+err.args[0])
    store = Store(args.data_dir)
    while True:
        try:
            for status in sync(store,remote,args.resolve): print(status, flush=True)
        except Exception as err:
            print(f"Synchronisation interrompue ({type(err).__name__}).",file=sys.stderr)
            if not args.watch: return 1
        if not args.watch: return 0
        args.resolve = None
        time.sleep(120)


if __name__ == "__main__":
    sys.exit(main())
