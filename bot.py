# bot.py
import os
from dotenv import load_dotenv  # ← додано
load_dotenv()  # ← додано: завантажує .env

import json
import random
import httpx
import traceback
from flask import Flask, request
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# 🔐 Безпечне завантаження секретів (з .env або змінних середовища)
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не встановлено! Додайте його в .env або в Environment Variables.")

TEACHER_CHAT_ID = int(os.getenv("TEACHER_CHAT_ID", "0"))
GROQ_KEY = os.getenv("GROQ_KEY", "")

bot = telebot.TeleBot(TOKEN)
user_data = {}

def escape_md(s):
    if not isinstance(s, str):
        s = str(s) if s is not None else ""
    s = s.replace('\\', '\\\\')
    for ch in '_*[]()~`>#+-=|{}.!':
        s = s.replace(ch, '\\' + ch)
    return s

# Завантаження статичних питань
STATIC_QUESTIONS = {}
if os.path.exists("questions.json"):
    try:
        with open("questions.json", "r", encoding="utf-8") as f:
            STATIC_QUESTIONS = json.load(f)
        total = sum(len(v) for v in STATIC_QUESTIONS.values())
        print(f"✅ Завантажено {total} статичних питань")
    except Exception as e:
        print(f"❌ Помилка у questions.json: {e}")
else:
    print("⚠️ questions.json не знайдено")

THEMES = list(STATIC_QUESTIONS.keys()) or [
    "Layout XML", "UI Components", "Knockout JS", "RequireJS", "PHTML Templates"
]

def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for t in THEMES:
        kb.add(KeyboardButton(t))
    return kb

def mode_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    kb.add(
        KeyboardButton("📄 Тільки статичні"),
        KeyboardButton("🚀 Тільки динамічні"),
        KeyboardButton("🔀 Гібридний (30% / 70%)")
    )
    return kb

def numbers_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=5)
    for i in range(1, 11):
        kb.add(KeyboardButton(str(i)))
    kb.add(KeyboardButton("Назад"))
    return kb

def generate_questions(theme, count):
    if not GROQ_KEY:
        print("⚠️ GROQ_KEY відсутній — динаміка вимкнена")
        return []

    prompt = f"""Ти — експерт з Magento 2 Frontend. Створи {count} питань українською для теми «{theme}».

❗ Правила:
1. Питання — практичні («як зробити?»), конкретні (назви файлів, атрибутів).
2. Варіанти (4 шт):
   - 1 правильний (технічно точний)
   - 2 правдоподібні помилки
   - 1 абсурд
3. correct — індекс (0–3)
4. explanation — 1–2 речення, чому саме цей варіант.

Приклад:
[
  {{
    "question": "Як оголосити модуль у requirejs-config.js?",
    "options": ["paths", "deps", "shim", "map"],
    "correct": 0,
    "explanation": "Модулі оголошуються в paths."
  }},
  {{
    "question": "Як оголосити модуль у requirejs-config.js?",
    "options": [
      "var config = {{ map: {{ '*': {{ myModule: 'Vendor_Module/js/my-module' }} }} }};",
      "var config = {{ paths: {{ 'myModule': 'Vendor_Module/my-module' }} }};",
      "var config = {{ shim: {{ myModule: {{ deps: ['jquery'] }} }} }};",
      "define(['myModule'], function() {{ console.log('Module registered'); }});"
    ],
    "correct": 0,
    "explanation": "Модуль оголошують через map у requirejs-config.js, де вказують ключ та шлях до JS-файлу."
  }}
]

➡️ Повертай ТІЛЬКИ чистий JSON-масив.
"""

    try:
        with httpx.Client(timeout=45) as client:
            r = client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                json={
                    "model": "llama-3.3-70b-versatile",  # ✅ Актуальна модель (після 24.01.2025)
                    "temperature": 0.3,
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            if r.status_code != 200:
                print(f"❌ Groq помилка: {r.status_code}")
                return []
            text = r.json()["choices"][0]["message"]["content"].strip()
            for prefix in ["```json", "```"]:
                if text.startswith(prefix):
                    text = text[len(prefix):].strip()
            if text.endswith("```"):
                text = text[:-3].strip()
            data = json.loads(text)
            valid = []
            for q in data:
                if (isinstance(q.get("question"), str) and
                    isinstance(q.get("options"), list) and len(q["options"]) == 4 and
                    isinstance(q.get("correct"), int) and 0 <= q["correct"] <= 3 and
                    isinstance(q.get("explanation"), str)):
                    valid.append(q)
            return valid
    except Exception as e:
        print(f"💥 Помилка генерації: {e}")
        return []

def get_questions(theme, count, mode):
    static = STATIC_QUESTIONS.get(theme, [])
    questions = []

    if mode == "static":
        if static:
            questions = random.sample(static, min(count, len(static)))
    elif mode == "dynamic":
        questions = generate_questions(theme, count)
        while len(questions) < count and static:
            questions.append(random.choice(static))
    elif mode == "hybrid":
        static_count = max(1, int(count * 0.3)) if static else 0
        if static and static_count > 0:
            questions.extend(random.sample(static, min(static_count, len(static))))
        needed = count - len(questions)
        if needed > 0:
            questions.extend(generate_questions(theme, needed))
        while len(questions) < count and static:
            questions.append(random.choice(static))

    random.shuffle(questions)
    return questions[:count]

# === Handlers ===
@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🎓 Magento 2 Frontend тренажер\nОберіть тему:", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text in THEMES)
def theme(m):
    user_data[m.chat.id] = {"theme": m.text}
    bot.send_message(m.chat.id, "Оберіть режим тестування:", reply_markup=mode_menu())

@bot.message_handler(func=lambda m: m.text in [
    "📄 Тільки статичні", "🚀 Тільки динамічні", "🔀 Гібридний (30% / 70%)"
])
def select_mode(m):
    mode_map = {
        "📄 Тільки статичні": "static",
        "🚀 Тільки динамічні": "dynamic",
        "🔀 Гібридний (30% / 70%)": "hybrid"
    }
    user_data[m.chat.id]["mode"] = mode_map[m.text]
    bot.send_message(m.chat.id, f"Режим: {m.text}\nСкільки питань (1–10)?", reply_markup=numbers_kb())

@bot.message_handler(func=lambda m: m.text.isdigit() and 1 <= int(m.text) <= 10)
def count(m):
    try:
        n = int(m.text)
        data = user_data.get(m.chat.id)
        if not data or "theme" not in data or "mode" not in data:
            bot.send_message(m.chat.id, "Спочатку оберіть тему та режим.", reply_markup=main_menu())
            return
        qs = get_questions(data["theme"], n, data["mode"])
        if not qs:
            bot.send_message(m.chat.id, "Не вдалося згенерувати питання.")
            return
        user_data[m.chat.id].update({"q": qs, "i": 0, "ok": 0, "log": []})
        static_used = len([q for q in qs if q in STATIC_QUESTIONS.get(data["theme"], [])])
        bot.send_message(m.chat.id, f"Готово! {n} питань (статичних: {static_used})")
        ask(m.chat.id)
    except Exception as e:
        print("❗ Помилка в count():", e)
        bot.send_message(m.chat.id, "Сталася помилка. /start")

def ask(cid):
    try:
        u = user_data.get(cid)
        if not u or u["i"] >= len(u["q"]):
            result(cid)
            return
        qq = u["q"][u["i"]]
        kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for o in qq["options"]:
            kb.add(KeyboardButton(o))
        safe_q = escape_md(qq["question"])
        bot.send_message(cid, f"*Питання {u['i']+1}/{len(u['q'])}*\n\n`{safe_q}`",
                         parse_mode="MarkdownV2", reply_markup=kb)
    except Exception as e:
        print("❗ Помилка в ask():", e)
        bot.send_message(cid, "Помилка. /start")

@bot.message_handler(func=lambda m: True)
def answer(m):
    try:
        u = user_data.get(m.chat.id)
        if not u or u["i"] >= len(u["q"]):
            return
        qq = u["q"][u["i"]]
        correct = qq["options"][qq["correct"]]
        if m.text == correct:
            u["ok"] += 1
        u["log"].append({"q": qq["question"], "u": m.text, "c": correct, "e": qq["explanation"]})
        u["i"] += 1
        ask(m.chat.id)
    except Exception as e:
        print("❗ Помилка в answer():", e)
        if m.chat.id in user_data:
            del user_data[m.chat.id]
        bot.send_message(m.chat.id, "Помилка. /start")

def result(cid):
    try:
        u = user_data.get(cid)
        if not u:
            return
        total = len(u["q"])
        text = f"*🎓 Тест завершено\\!*\n*✅ Правильних: {u['ok']}/{total} \\({u['ok']/total:.0%}\\)*\n\n*🔍 Розбір:*\n\n"
        for i, x in enumerate(u["log"], 1):
            q, u_ans, c_ans, e = map(escape_md, [x["q"], x["u"], x["c"], x["e"]])
            if x["u"] == x["c"]:
                text += f"✅ *{i}/{total}*\n`{q}`\n→ {e}\n\n"
            else:
                text += f"❌ *{i}/{total}*\n`{q}`\nТвоя: `{u_ans}`\nПравильна: `{c_ans}`\n→ {e}\n\n"
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("Надіслати результат викладачу"))
        bot.send_message(cid, text, parse_mode="MarkdownV2", reply_markup=kb)
    except Exception as e:
        print("❗ Fallback plain:", e)
        u = user_data.get(cid)
        if not u:
            return
        plain = f"🎓 Тест завершено!\n✅ Правильних: {u['ok']}/{len(u['q'])}\n\nРозбір:\n"
        for i, x in enumerate(u["log"], 1):
            plain += f"{i}. {x['q']}\n→ Ваша: {x['u']}\n→ Правильна: {x['c']}\n→ {x['e']}\n\n"
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add(KeyboardButton("Надіслати результат викладачу"))
        bot.send_message(cid, plain, reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "Надіслати результат викладачу")
def send_to_teacher(m):
    try:
        u = user_data.get(m.chat.id)
        if not u:
            bot.send_message(m.chat.id, "Дані втрачені. /start")
            return
        summary = f"Результат від {m.from_user.full_name}\nТема: {u['theme']}\n✅ {u['ok']}/{len(u['q'])}"
        bot.send_message(TEACHER_CHAT_ID, summary)
        bot.forward_message(TEACHER_CHAT_ID, m.chat.id, m.message_id)
        bot.send_message(m.chat.id, "📬 Надіслано викладачу!", reply_markup=main_menu())
        if m.chat.id in user_data:
            del user_data[m.chat.id]
    except Exception as e:
        print("❗ Помилка в send_to_teacher:", e)
        bot.send_message(m.chat.id, "Не вдалося надіслати.")

# === Webhook для Render ===
app = Flask(__name__)

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        json_string = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "", 200
    return "", 403

@app.route("/setwebhook")
def set_webhook():
    # Викликається один раз після деплою
    url = f"{os.getenv('WEBHOOK_URL', '').rstrip('/')}/{TOKEN}"
    if not url or url == f"/{TOKEN}":
        return "❌ WEBHOOK_URL не встановлено! Додайте його в Environment Variables.", 400
    result = bot.set_webhook(url=url)
    return f"✅ Webhook встановлено на {url}: {result}"

@app.route("/")
def health():
    return "✅ Бот працює! Перейдіть до Telegram і напишіть /start"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)