# -*- coding: utf-8 -*-
# روبو البيع فواتساب — ملابس (نسخة التجربة)
# بدل غير البلوك ديال المنتوجات اللي لتحت، بلا ما تقرب للكود.

# ============== المنتوجات (بدل من هنا) ==============
# سمية المتجر:
STORE_NAME = "المتجر ديالي"
# كل منتوج عندو 4 خانات. باش تزيد منتوج آخر، نسخ البلوك كامل من { حتى },
# ولصقو تحت منو، وبدل المعلومات. خاص الفاصلة , تبقى بين كل بلوك وبلوك.
PRODUCTS = [
    {
        "name": "بيجامة فيلور",
        "price": "حبة = 200 درهم، زوج = 350 درهم، ثلاثة = 500 درهم",
        "sizes": "من S حتى 6XL",
        "colors": "الأزرق",
        "notes": "الدفع عند الاستلام، التوصيل كيديرو صاحب المتجر بنفسو",
    },
]
# =====================================================

import os
import threading

import requests
from flask import Flask, request, jsonify

VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
WABA_ID = os.environ.get("WABA_ID", "2607346956425879")

GRAPH_URL = "https://graph.facebook.com/v22.0"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    + GEMINI_MODEL + ":generateContent?key=" + GEMINI_API_KEY
)



def subscribe_waba():
    if not WHATSAPP_TOKEN or not WABA_ID:
        print("SUBSCRIBE_WABA skipped: missing WHATSAPP_TOKEN or WABA_ID", flush=True)
        return
    url = "https://graph.facebook.com/v21.0/" + WABA_ID + "/subscribed_apps"
    headers = {"Authorization": "Bearer " + WHATSAPP_TOKEN}
    try:
        r = requests.post(url, headers=headers, timeout=30)
        print("SUBSCRIBE_WABA", r.status_code, r.text[:300], flush=True)
    except Exception as e:
        print("SUBSCRIBE_WABA error", repr(e), flush=True)


subscribe_waba()

def build_prompt():
    catalog = ""
    for i, p in enumerate(PRODUCTS, 1):
        catalog += (
            f"{i}) {p['name']} | الثمن: {p['price']} | "
            f"المقاسات: {p['sizes']} | الألوان: {p['colors']} | {p['notes']}\n"
        )
    return (
        f"أنت وكيل ذكي ديال {STORE_NAME}، متجر ملابس، كتجاوب على الزبناء "
        "فواتساب بالدارجة المغربية بالحروف العربية، بأسلوب مهذب وقريب. "
        "جاوب باختصار وبلا حشو، واستعمل الإيموجي باعتدال (🌿 ✅).\n"
        "قواعد صارمة:\n"
        "1. عمرك تخترع معلومة. جاوب غير من لائحة المنتوجات اللي لتحت. "
        "ما كايناش تما = قول «غنسول ونرجع ليك فأقرب وقت».\n"
        "2. الدفع عند الاستلام (COD).\n"
        "3. قبل تأكيد أي طلب، جمع وتأكد: الاسم الكامل، رقم الهاتف، المدينة، "
        "العنوان الكامل، المنتوج، المقاس، اللون، والعدد.\n"
        "4. فاش تكمل، عاود كتب الطلب كامل مع الثمن وسولو: «واش نأكد الطلب؟» "
        "وما تأكد حتى يجاوب بنعم ولا كلمة واضحة بحالها.\n"
        "5. إلا طلب تخفيض، جاوبو بأدب أن هادا الثمن الأخير، بلا وعود.\n"
        "6. إلا بان متردد، غاضب، ولا بغى إنسان، قولو: «غيتواصل معاك صاحب "
        "المتجر مباشرة فأقرب وقت».\n"
        "7. الرسائل الصوتية: جاوب عادي، وطلب الاسم والعنوان مكتوبين.\n"
        "8. إلا هضر على موضوع آخر، جاوب باحترام ورجعو للطلب.\n"
        "لائحة المنتوجات:\n" + catalog
    )


app = Flask(__name__)
HISTORY = {}
HISTORY_LIMIT = 20
SEEN_MESSAGES = set()


def gemini_reply(user_id, text):
    history = HISTORY.setdefault(user_id, [])
    contents = list(history) + [{"role": "user", "parts": [{"text": text}]}]
    payload = {
        "system_instruction": {"parts": [{"text": build_prompt()}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2000},
    }
    resp = requests.post(GEMINI_URL, json=payload, timeout=30)
    try:
        answer = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        print("GEMINI_ERROR", resp.status_code, resp.text[:300], flush=True)
        return None
    history.append({"role": "user", "parts": [{"text": text}]})
    history.append({"role": "model", "parts": [{"text": answer}]})
    del history[:-HISTORY_LIMIT]
    return answer


def send_whatsapp(to, text):
    url = GRAPH_URL + "/" + PHONE_NUMBER_ID + "/messages"
    headers = {"Authorization": "Bearer " + WHATSAPP_TOKEN}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    print("WA_SEND", r.status_code, r.text[:300], flush=True)


def handle_message(msg):
    user_id = msg.get("from", "")
    msg_type = msg.get("type", "")
    if msg_type == "text":
        text = msg.get("text", {}).get("body", "").strip()
    elif msg_type == "audio":
        text = "(رسالة صوتية من الزبون: جاوبو عادي وطلب منو يكتب الاسم والعنوان بالكتابة)"
    else:
        text = None
    if not user_id or not text:
        return
    answer = gemini_reply(user_id, text)
    if answer:
        send_whatsapp(user_id, answer)


@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode", "")
    token = request.args.get("hub.verify_token", "")
    challenge = request.args.get("hub.challenge", "")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "forbidden", 403


@app.route("/webhook", methods=["POST"])
def incoming():
    data = request.get_json(silent=True) or {}
    print("WEBHOOK_IN", str(data)[:200], flush=True)
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    msg_id = msg.get("id", "")
                    if msg_id and msg_id in SEEN_MESSAGES:
                        continue
                    SEEN_MESSAGES.add(msg_id)
                    threading.Thread(target=handle_message, args=(msg,)).start()
    except Exception:
        pass
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET"])
def home():
    return "bot is running", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
