#!/usr/bin/env python3
"""Telegram-controlled LinkedIn invitation planner (preview only).

No LinkedIn credentials, browser automation, or auto-sending.
Python 3.11+, standard library only.
"""
import csv
import io
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

LOG = logging.getLogger("telegram-agent")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
OWNER_RAW = os.environ.get("TELEGRAM_OWNER_ID", "").strip()
if not TOKEN or not OWNER_RAW.isdigit():
    raise SystemExit("TELEGRAM_BOT_TOKEN and numeric TELEGRAM_OWNER_ID are required in Railway Variables")
OWNER_ID = int(OWNER_RAW)
API = f"https://api.telegram.org/bot{TOKEN}/"
FILE_API = f"https://api.telegram.org/file/bot{TOKEN}/"
DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "agent.sqlite3"
TZ = ZoneInfo("Asia/Baku")
BATCH_SIZE = 5
INTERVAL = timedelta(hours=2)
START_HOUR = 9
END_HOUR = 19
MAX_DAILY = 20
MAX_SEVEN_DAYS = 60
MAX_IMPORT = 500
HELP = (
    "LinkedIn AI Assistant — təhlükəsiz preview rejimi.\n"
    "LinkedIn-ə avtomatik dəvət GÖNDƏRMİR.\n\n"
    "/add Ad Soyad | https://www.linkedin.com/in/username/ | Qeyd\n"
    "/queue — növbəti 5 profil\n"
    "/run — 5 profil üçün planlaşdırma dövrəsi\n"
    "/auto_on — hər 2 saatda bir yoxlama (09:00–19:00)\n"
    "/auto_off — avtomatik dövrəni dayandır\n"
    "/status — vəziyyət\n"
    "/mark sent <profil URL> — əl ilə göndərilən dəvəti qeyd et\n"
    "/report — son 15 hadisə\n"
    "/export — CSV hesabat\n"
    "/draft Ad | Vəzifə | Şirkət | Məqsəd — mətn şablonu\n"
    "CSV sənədi də göndərə bilərsiniz: name,profile_url,note\n"
)


def now_utc():
    return datetime.now(timezone.utc)


def conn():
    c = sqlite3.connect(DB_PATH, timeout=20)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with conn() as db:
        db.execute("CREATE TABLE IF NOT EXISTS profiles (id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL UNIQUE, note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL, last_preview_at TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, profile_id INTEGER, event TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', ts TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('auto_on', '0')")


def setting(db, key, default=""):
    row = db.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(db, key, value):
    db.execute("INSERT INTO config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def tg(method, payload=None, timeout=45):
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
    req = Request(API + method, data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        result = json.load(resp)
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result.get('description', 'unknown')}")
    return result["result"]


def say(message, chat_id=OWNER_ID):
    try:
        for i in range(0, len(message), 3800):
            tg("sendMessage", {"chat_id": chat_id, "text": message[i:i + 3800], "disable_web_page_preview": True})
    except Exception:
        LOG.exception("Could not send Telegram message")


def send_csv(filename, text):
    boundary = "----linkedin-agent-boundary"
    parts = [
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{OWNER_ID}\r\n").encode(),
        (f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{filename}\"\r\nContent-Type: text/csv; charset=utf-8\r\n\r\n").encode(),
        text.encode("utf-8-sig"),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    req = Request(API + "sendDocument", data=b"".join(parts), headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urlopen(req, timeout=45) as resp:
        result = json.load(resp)
    if not result.get("ok"):
        raise RuntimeError("CSV could not be sent")


def normalize_url(text):
    s = text.strip()
    parsed = urlparse(s)
    if parsed.scheme != "https" or parsed.netloc.lower() not in ("linkedin.com", "www.linkedin.com"):
        raise ValueError("Yalnız https://www.linkedin.com/in/... profil linki qəbul olunur.")
    match = re.fullmatch(r"/in/([A-Za-z0-9_%-]+)/?", parsed.path)
    if not match:
        raise ValueError("Link bu formada olmalıdır: https://www.linkedin.com/in/username/")
    return f"https://www.linkedin.com/in/{match.group(1)}/"


def add_profile(db, name, url, note=""):
    if not name.strip() or len(name) > 120:
        raise ValueError("Ad boş və ya 120 simvoldan uzun ola bilməz.")
    clean_url = normalize_url(url)
    cursor = db.execute("INSERT OR IGNORE INTO profiles(name,url,note,status,created_at) VALUES(?,?,?,?,?)", (name.strip(), clean_url, note[:250], "pending", now_utc().isoformat()))
    return bool(cursor.rowcount)


def queue(db, limit=BATCH_SIZE):
    return db.execute("SELECT * FROM profiles WHERE status='pending' ORDER BY COALESCE(last_preview_at,'') ASC,id ASC LIMIT ?", (limit,)).fetchall()


def format_profiles(rows):
    return "\n\n".join(f"{i}. {r['name']}\n{r['url']}" + (f"\nQeyd: {r['note']}" if r['note'] else "") for i, r in enumerate(rows, 1))


def do_preview(db, trigger="manual"):
    rows = queue(db)
    if not rows:
        if trigger == "manual": say("Hazırda növbədə profil yoxdur. /add ilə əlavə edin.")
        return
    stamp = now_utc().isoformat()
    for row in rows:
        db.execute("UPDATE profiles SET last_preview_at=? WHERE id=?", (stamp, row["id"]))
        db.execute("INSERT INTO events(profile_id,event,detail,ts) VALUES (?,?,?,?)", (row["id"], "preview", trigger, stamp))
    set_setting(db, "last_run", stamp)
    say(f"5 nəfərlik yoxlama dövrəsi ({trigger})\n\n{format_profiles(rows)}\n\nBu yalnız planlaşdırmadır: LinkedIn dəvəti göndərilməyib.")


def status(db):
    count = db.execute("SELECT COUNT(*) FROM profiles WHERE status='pending'").fetchone()[0]
    completed = db.execute("SELECT COUNT(*) FROM profiles WHERE status='manual_sent'").fetchone()[0]
    now = now_utc()
    count24 = db.execute("SELECT COUNT(*) FROM events WHERE event='manual_sent' AND ts>=?", ((now - timedelta(days=1)).isoformat(),)).fetchone()[0]
    count7 = db.execute("SELECT COUNT(*) FROM events WHERE event='manual_sent' AND ts>=?", ((now - timedelta(days=7)).isoformat(),)).fetchone()[0]
    auto = setting(db, "auto_on") == "1"
    local = now.astimezone(TZ).strftime("%d.%m.%Y %H:%M")
    return (f"Bot statusu ({local}, Bakı)\n"
            f"Avtomatik yoxlama: {'AKTİV' if auto else 'BAĞLI'}\n"
            f"Növbədə: {count}\nƏl ilə göndərilmiş kimi qeyd edilən: {completed}\n"
            f"24 saatda əl ilə qeyd: {count24}/{MAX_DAILY}\n"
            f"7 gündə əl ilə qeyd: {count7}/{MAX_SEVEN_DAYS}\n"
            "Qrup: 5 | Interval: 2 saat | Saatlar: 09:00–19:00\n"
            "Rejim: PREVIEW. Bot LinkedIn-ə dəvət göndərmir.")


def handle_command(text):
    pieces = text.strip().split(" ", 1)
    command = pieces[0].split("@")[0].lower()
    arg = pieces[1].strip() if len(pieces) > 1 else ""
    with conn() as db:
        if command in ("/start", "/help"):
            say(HELP)
        elif command == "/status":
            say(status(db))
        elif command == "/add":
            vals = [v.strip() for v in arg.split("|", 2)]
            if len(vals) < 2:
                say("İstifadə: /add Ad Soyad | https://www.linkedin.com/in/username/ | Qeyd")
            else:
                try:
                    added = add_profile(db, vals[0], vals[1], vals[2] if len(vals)>2 else "")
                    say("Profil növbəyə əlavə edildi." if added else "Bu profil artıq siyahıdadır.")
                except ValueError as exc: say(str(exc))
        elif command == "/queue":
            rows = queue(db)
            say("Növbəti 5 profil:\n\n" + format_profiles(rows) if rows else "Növbədə profil yoxdur.")
        elif command == "/run":
            do_preview(db, "manual")
        elif command in ("/auto_on", "/startauto"):
            set_setting(db,"auto_on","1")
            set_setting(db,"last_run",now_utc().isoformat())
            say("2 saatlıq yoxlama aktivdir (Bakı 09:00–19:00). İlk avtomatik yoxlama təxminən 2 saat sonra olacaq. /run indi yoxlayır. Dəvət göndərilmir.")
        elif command in ("/auto_off", "/stopauto"):
            set_setting(db,"auto_on","0")
            say("Avtomatik yoxlama dayandırıldı.")
        elif command == "/mark":
            # e.g. /mark sent https://www.linkedin.com/in/example/
            mark_parts = arg.split(maxsplit=1)
            if len(mark_parts) != 2 or mark_parts[0].lower() != "sent":
                say("İstifadə: /mark sent https://www.linkedin.com/in/username/")
            else:
                try:
                    clean = normalize_url(mark_parts[1])
                    row = db.execute("SELECT id,status FROM profiles WHERE url=?", (clean,)).fetchone()
                    if row is None: say("Bu profil növbədə yoxdur. Əvvəlcə /add istifadə edin.")
                    elif row["status"] == "manual_sent": say("Bu profil artıq əl ilə göndərilmiş kimi qeyd edilib.")
                    else:
                        stamp = now_utc().isoformat()
                        db.execute("UPDATE profiles SET status='manual_sent' WHERE id=?", (row["id"],))
                        db.execute("INSERT INTO events(profile_id,event,detail,ts) VALUES (?,?,?,?)", (row["id"],"manual_sent","user_reported",stamp))
                        say("Əl ilə göndərilmiş kimi qeyd edildi. Bu LinkedIn-dən alınan təsdiq deyil.")
                except ValueError as exc: say(str(exc))
        elif command == "/report":
            rows = db.execute("SELECT e.ts,e.event,p.name,e.detail FROM events e LEFT JOIN profiles p ON p.id=e.profile_id ORDER BY e.id DESC LIMIT 15").fetchall()
            if not rows: say("Hələ hadisə qeydi yoxdur.")
            else: say("Son 15 qeydə alınmış hadisə:\n\n" + "\n".join(f"{r['ts'][:16]} | {r['name'] or '-'} | {r['event']} ({r['detail']})" for r in rows) + "\n\n'preview' göndəriş demək deyil.")
        elif command == "/export":
            rows = db.execute("SELECT name,url,note,status,created_at,last_preview_at FROM profiles ORDER BY id").fetchall()
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["name", "profile_url", "note", "status", "created_at_utc", "last_preview_at_utc"])
            writer.writerows(tuple(r) for r in rows)
            send_csv("linkedin_agent_report.csv",buf.getvalue())
        elif command == "/draft":
            vals = [v.strip() for v in arg.split("|", 3)]
            if len(vals)<4: say("İstifadə: /draft Ad | Vəzifə | Şirkət | Məqsəd")
            else:
                name, role, company, purpose = vals
                template = f"Salam, {name}. {company} şirkətində {role} sahəsində fəaliyyətinizi maraqla izləyirəm. {purpose} üçün sizinlə əlaqə qurmaq istərdim."
                say("Dəvət üçün mətn şablonu (AI deyil):\n\n"+template[:200])
        else:
            say("Naməlum əmr. /help göndərin.")


def handle_document(document):
    filename = document.get("file_name", "")
    if not filename.lower().endswith(".csv"):
        say("Yalnız UTF-8 CSV qəbul olunur (name,profile_url,note).")
        return
    if document.get("file_size", 0) > 2_000_000:
        say("CSV faylı 2 MB-dan kiçik olmalıdır.")
        return
    meta = tg("getFile",{"file_id":document["file_id"]})
    path = meta["file_path"]
    with urlopen(FILE_API + quote(path, safe="/"),timeout=35) as resp:
        content = resp.read(2_000_001)
    if len(content)>2_000_000:
        say("CSV faylı çox böyükdür.")
        return
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        if not {"name","profile_url"}.issubset(set(reader.fieldnames or [])):
            say("CSV başlıqları belə olmalıdır: name,profile_url,note")
            return
        added = duplicates = errors = 0
        with conn() as db:
            for row in reader:
                if added + duplicates + errors >= MAX_IMPORT: break
                try:
                    if add_profile(db,row.get("name", ""),row.get("profile_url", ""),row.get("note", "")): added+=1
                    else: duplicates+=1
                except (ValueError, KeyError, AttributeError): errors+=1
        say(f"CSV import bitdi: əlavə edildi {added}, dublikat {duplicates}, xətalı {errors}. (Maksimum {MAX_IMPORT} sətir.)")
    except UnicodeDecodeError:
        say("Fayl UTF-8 kodlaşdırmasında olmalıdır.")


def maybe_auto_run():
    with conn() as db:
        if setting(db,"auto_on") != "1": return
        now = now_utc()
        local = now.astimezone(TZ)
        if not START_HOUR <= local.hour < END_HOUR: return
        raw = setting(db,"last_run")
        if raw:
            try:
                last = datetime.fromisoformat(raw)
                if now-last < INTERVAL:return
            except ValueError: pass
        if not queue(db):
            set_setting(db,"last_run",now.isoformat())
            return
        do_preview(db,"automatic")


def main():
    init_db()
    LOG.info("Starting Telegram invitation planner (preview only) with DB at %s", DB_PATH)
    tg("deleteWebhook", {"drop_pending_updates":False})
    offset = None
    while True:
        try:
            maybe_auto_run()
            payload = {"timeout": 25, "allowed_updates": ["message"]}
            if offset is not None: payload["offset"] = offset
            updates = tg("getUpdates",payload,timeout=40)
            for update in updates:
                offset = update["update_id"]+1
                msg = update.get("message",{})
                sender = msg.get("from",{})
                chat = msg.get("chat",{})
                if sender.get("id") != OWNER_ID or chat.get("type") != "private": continue
                if "text" in msg: handle_command(msg["text"])
                elif "document" in msg: handle_document(msg["document"])
        except (HTTPError,URLError,TimeoutError) as e:
            LOG.warning("Temporary network/API issue: %s",e)
            time.sleep(5)
        except KeyboardInterrupt:
            raise
        except Exception:
            LOG.exception("Unhandled error in poll loop")
            time.sleep(5)


if __name__ == "__main__":
    main()
