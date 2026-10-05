"""
سرور ساده برای تست: صفحه وب موقعیت + ربات بله (چند کاربره)

این سرور دو کار می‌کند:
1. صفحه index.html را سرو می‌کند و موقعیت ارسالی از هر کاربر را
   بر اساس شناسه چت او (chat_id) ذخیره می‌کند (پس چند نفر همزمان
   پشتیبانی می‌شوند، نه فقط یک نفر).
2. با متد long-polling به ربات بله وصل می‌شود:
   - وقتی کاربر /start بزند، یک لینک شخصی (با uid خودش) برایش می‌فرستد.
   - وقتی کاربر کلمه "آدرس" یا "موقعیت" بفرستد، آخرین موقعیت ذخیره‌شده‌
     ی همان کاربر را برایش پاسخ می‌دهد.

نکته: برای اجرای این سرور به صورت دائمی (تا همیشه به ربات جواب بدهد)،
باید روی یک سرور/هاست همیشه-روشن اجرا شود، نه فقط روی گوشی خودت در لحظه.
در پایین فایل README راهنمای اجرا هست.
"""

import json
import os
import threading
import time
from pathlib import Path

import requests
from flask import Flask, request, jsonify, send_from_directory

BOT_TOKEN = os.environ.get("BALE_TOKEN", "PUT_YOUR_TOKEN_HERE")
API_URL = f"https://tapi.bale.ai/bot{BOT_TOKEN}"
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:5000")  # آدرس عمومی سروری که این فایل را اجرا می‌کند

DB_FILE = Path(__file__).parent / "locations.json"
STATIC_DIR = Path(__file__).parent / "static"

app = Flask(__name__, static_folder=None)
_lock = threading.Lock()


def load_db():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    return {}


def save_db(db):
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def bale_send_message(chat_id, text):
    try:
        requests.post(f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=10)
    except Exception as e:
        print("خطا در ارسال پیام:", e)


# ---------- صفحه وب ----------

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/location", methods=["POST"])
def api_location():
    data = request.get_json(force=True)
    uid = str(data.get("uid", ""))
    if not uid:
        return jsonify({"ok": False, "error": "uid missing"}), 400

    with _lock:
        db = load_db()
        db[uid] = {
            "lat": data.get("lat"),
            "lng": data.get("lng"),
            "address": data.get("address"),
            "ts": time.time(),
        }
        save_db(db)

    return jsonify({"ok": True})


# ---------- ربات بله (long polling) ----------

def handle_update(update):
    message = update.get("message")
    if not message:
        return
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()

    if text == "/start":
        link = f"{PUBLIC_URL}/?uid={chat_id}"
        bale_send_message(
            chat_id,
            "سلام! برای ثبت موقعیتت روی این لینک بزن و دکمه داخل صفحه را فشار بده:\n"
            f"{link}\n\n"
            "بعد از ثبت، هر وقت بنویسی «آدرس» یا «موقعیت»، آخرین موقعیتت رو برات می‌فرستم.",
        )
        return

    if text in ("آدرس", "موقعیت", "ادرس"):
        with _lock:
            db = load_db()
        entry = db.get(str(chat_id))
        if not entry:
            bale_send_message(chat_id, "هنوز موقعیتی برای تو ثبت نشده. اول از دکمه داخل لینک استفاده کن.")
        else:
            age_min = int((time.time() - entry["ts"]) / 60)
            bale_send_message(
                chat_id,
                f"📍 آخرین موقعیت ثبت‌شده ({age_min} دقیقه پیش):\n{entry['address']}",
            )
        return

    bale_send_message(chat_id, "برای شروع /start را بفرست. بعد از ثبت موقعیت، بنویس «آدرس» تا موقعیتت رو بهت بدم.")


def polling_loop():
    offset = 0
    print("ربات بله شروع به کار کرد (long polling)...")
    while True:
        try:
            resp = requests.get(f"{API_URL}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=40)
            data = resp.json()
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                handle_update(update)
        except Exception as e:
            print("خطا در polling:", e)
            time.sleep(3)


if __name__ == "__main__":
    if BOT_TOKEN == "PUT_YOUR_TOKEN_HERE":
        print("⚠️  اول توکن ربات بله رو توی متغیر محیطی BALE_TOKEN بذار.")
    t = threading.Thread(target=polling_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
