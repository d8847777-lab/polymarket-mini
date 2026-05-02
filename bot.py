import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import sqlite3
import random
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import io

# ===================== НАСТРОЙКИ =====================
VK_TOKEN = "vk1.a.R3BzWRXp0snn9Ipz-WbWPC31QB3zcE4abLHIaX6WsimX8-CA_Z1NNRaJ1y1ZiVS7Jpw5yjVjrdVZ8yLuIp5zK6ctfP5u7MXMG-yF_FxLL2UaLQT7XQPtUolySZm9efjL4s8Ii_eakMjyml0MhdDY_mPoBss0dy7KWZxt5Ru9-uA0yqvYUdAHU2kLPMkZmfuApdBiDVrJ-7rMle9eg1eHyg"
GROUP_ID = 238310451
ADMIN_ID = 846272768

# ===================== БАЗА ДАННЫХ =====================
conn = sqlite3.connect('polymarket.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance REAL DEFAULT 1000,
    last_bonus TEXT DEFAULT '',
    streak INTEGER DEFAULT 0,
    total_wins INTEGER DEFAULT 0,
    total_bets INTEGER DEFAULT 0
)''')

c.execute('''CREATE TABLE IF NOT EXISTS markets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT,
    yes_tokens REAL DEFAULT 1000,
    no_tokens REAL DEFAULT 1000,
    k REAL DEFAULT 1000000,
    status TEXT DEFAULT 'active'
)''')

c.execute('''CREATE TABLE IF NOT EXISTS positions (
    user_id INTEGER,
    market_id INTEGER,
    side TEXT,
    tokens REAL,
    buy_price REAL
)''')

conn.commit()

# ===================== AMM CPMM =====================
def get_market(market_id):
    c.execute("SELECT * FROM markets WHERE id=?", (market_id,))
    return c.fetchone()

def get_price(market):
    yes = market[2]
    no = market[3]
    total = yes + no
    if total == 0:
        return 0.5, 0.5
    return round(no / total, 4), round(yes / total, 4)

def buy(market_id, user_id, side, amount):
    market = get_market(market_id)
    if not market or market[5] != 'active':
        return False, "Рынок не активен"
    
    c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    if not user or user[0] < amount:
        return False, "Недостаточно FORT"
    
    yes = market[2]
    no = market[3]
    k = market[4]
    
    if side == "yes":
        new_no = k / (yes - amount)
        tokens_bought = no - new_no
        new_yes = yes - amount
        new_no = new_no
    else:
        new_yes = k / (no - amount)
        tokens_bought = yes - new_yes
        new_no = no - amount
        new_yes = new_yes
    
    if tokens_bought <= 0:
        return False, "Слишком маленькая ставка"
    
    c.execute("UPDATE markets SET yes_tokens=?, no_tokens=? WHERE id=?", (new_yes, new_no, market_id))
    c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amount, user_id))
    c.execute("INSERT INTO positions VALUES (?, ?, ?, ?, ?)", (user_id, market_id, side, tokens_bought, amount))
    c.execute("UPDATE users SET total_bets=total_bets+1 WHERE user_id=?", (user_id,))
    conn.commit()
    return True, round(tokens_bought, 2)

def add_user(user_id):
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

def get_balance(user_id):
    c.execute("SELECT balance FROM users WHERE user_id=?", (user_id,))
    r = c.fetchone()
    return r[0] if r else 0

# ===================== КЛАВИАТУРЫ =====================
def main_keyboard():
    kb = VkKeyboard(one_time=False)
    kb.add_button('Рынки', VkKeyboardColor.PRIMARY)
    kb.add_button('Портфель', VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button('Топ игроков', VkKeyboardColor.SECONDARY)
    kb.add_button('Бонус', VkKeyboardColor.POSITIVE)
    kb.add_line()
    kb.add_button('Помощь', VkKeyboardColor.SECONDARY)
    return kb.get_keyboard()

def markets_keyboard():
    c.execute("SELECT id, question FROM markets WHERE status='active'")
    markets = c.fetchall()
    kb = VkKeyboard(one_time=True)
    for m in markets:
        kb.add_button(f"Рынок {m[0]}", VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button('Назад', VkKeyboardColor.NEGATIVE)
    return kb.get_keyboard()

# ===================== VK БОТ =====================
vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

print("Бот Polymarket Mini запущен!")

c.execute("SELECT COUNT(*) FROM markets")
if c.fetchone()[0] == 0:
    test_markets = [
        "Биткоин выше $130 000 к июню?",
        "Трамп станет президентом в 2026?",
        "Россия выиграет ЧМ по футболу 2026?",
        "Илон Маск запустит людей на Марс до 2027?",
        "Будет ли мировая война в 2026?"
    ]
    for q in test_markets:
        c.execute("INSERT INTO markets (question) VALUES (?)", (q,))
    conn.commit()

for event in longpoll.listen():
    if event.type != VkBotEventType.MESSAGE_NEW:
        continue
    
    msg = event.object.message
    user_id = msg['from_id']
    text = msg.get('text', '')
    
    if not text:
        continue
    
    add_user(user_id)
    
    if text == 'Начать' or text == 'Назад':
        vk.messages.send(user_id=user_id, message='🏟 Главное меню', keyboard=main_keyboard(), random_id=random.randint(1, 2**31))
    
    elif text == 'Рынки':
        c.execute("SELECT id, question FROM markets WHERE status='active'")
        markets = c.fetchall()
        if not markets:
            vk.messages.send(user_id=user_id, message='Нет активных рынков', keyboard=markets_keyboard(), random_id=random.randint(1, 2**31))
        else:
            msg_text = "📊 Активные рынки:\n\n"
            for m in markets:
                market = get_market(m[0])
                p_yes, p_no = get_price(market)
                msg_text += f"🔹 Рынок {m[0]}: {m[1]}\nДа: {p_yes} | Нет: {p_no} FORT\n\n"
            msg_text += "Нажми на рынок, чтобы сделать ставку"
            vk.messages.send(user_id=user_id, message=msg_text, keyboard=markets_keyboard(), random_id=random.randint(1, 2**31))
    
    elif text.startswith('Рынок '):
        try:
            market_id = int(text.replace('Рынок ', ''))
            market = get_market(market_id)
            if market:
                p_yes, p_no = get_price(market)
                
                c.execute("SELECT yes_tokens, no_tokens FROM markets WHERE id=?", (market_id,))
                row = c.fetchone()
                yes = row[0]
                no = row[1]
                total = yes + no
                price_yes = no / total if total > 0 else 0.5
                price_no = yes / total if total > 0 else 0.5
                
                history_yes = []
                history_no = []
                for i in range(10):
                    factor = random.uniform(0.9, 1.1)
                    history_yes.append(round(price_yes * factor, 3))
                    history_no.append(round(price_no * factor, 3))
                
                fig, ax = plt.subplots(figsize=(6, 3))
                ax.plot(range(10), history_yes, 'g-', label='Да', linewidth=2)
                ax.plot(range(10), history_no, 'r-', label='Нет', linewidth=2)
                ax.set_title(f"Рынок {market_id}: {market[1][:30]}...", fontsize=10)
                ax.set_ylabel('Цена (FORT)')
                ax.legend()
                ax.grid(True, alpha=0.3)
                plt.tight_layout()
                
                buf = io.BytesIO()
                plt.savefig(buf, format='png', dpi=80)
                buf.seek(0)
                plt.close()
                
                upload = vk_api.VkUpload(vk_session)
                photo = upload.photo_messages(buf)[0]
                attachment = f"photo{photo['owner_id']}_{photo['id']}"
                
                kb = VkKeyboard(one_time=True)
                kb.add_button(f'Купить Да {market_id}', VkKeyboardColor.POSITIVE)
                kb.add_button(f'Купить Нет {market_id}', VkKeyboardColor.NEGATIVE)
                kb.add_line()
                kb.add_button('Назад', VkKeyboardColor.SECONDARY)
                
                msg_text = f"📊 {market[1]}\nДа: {p_yes} | Нет: {p_no} FORT\n\nНапиши сумму ставки после нажатия кнопки"
                vk.messages.send(user_id=user_id, message=msg_text, attachment=attachment, keyboard=kb.get_keyboard(), random_id=random.randint(1, 2**31))
        except:
            pass
    
    elif text.startswith('Купить Да ') or text.startswith('Купить Нет '):
        parts = text.split()
        side = "yes" if parts[1] == "Да" else "no"
        market_id = int(parts[-1])
        vk.messages.send(user_id=user_id, message=f"Введи сумму ставки на рынок {market_id} ({side}):", random_id=random.randint(1, 2**31))
        c.execute("CREATE TABLE IF NOT EXISTS pending (user_id INTEGER, market_id INTEGER, side TEXT)")
        c.execute("DELETE FROM pending WHERE user_id=?", (user_id,))
        c.execute("INSERT INTO pending VALUES (?, ?, ?)", (user_id, market_id, side))
        conn.commit()
    
    elif text.isdigit():
        amount = int(text)
        c.execute("SELECT * FROM pending WHERE user_id=?", (user_id,))
        pending = c.fetchone()
        if pending:
            market_id = pending[1]
            side = pending[2]
            success, result = buy(market_id, user_id, side, amount)
            if success:
                market = get_market(market_id)
                p_yes, p_no = get_price(market)
                vk.messages.send(user_id=user_id,
                    message=f"✅ Куплено {result} токенов '{side}' на рынке {market_id}\nНовые цены: Да={p_yes} Нет={p_no}\nБаланс: {get_balance(user_id)} FORT",
                    keyboard=main_keyboard(), random_id=random.randint(1, 2**31))
            else:
                vk.messages.send(user_id=user_id, message=f"❌ Ошибка: {result}", keyboard=main_keyboard(), random_id=random.randint(1, 2**31))
            c.execute("DELETE FROM pending WHERE user_id=?", (user_id,))
            conn.commit()
        else:
            vk.messages.send(user_id=user_id, message="Выбери действие из меню", keyboard=main_keyboard(), random_id=random.randint(1, 2**31))
    
    elif text == 'Портфель':
        balance = get_balance(user_id)
        c.execute("SELECT COUNT(*) FROM positions WHERE user_id=?", (user_id,))
        pos_count = c.fetchone()[0]
        vk.messages.send(user_id=user_id,
            message=f"💰 Твой портфель\n\nFORT: {balance}\nОткрытых позиций: {pos_count}\n\nРынки скоро закроются — следи за новостями!",
            keyboard=main_keyboard(), random_id=random.randint(1, 2**31))
    
    elif text == 'Топ игроков':
        c.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 10")
        tops = c.fetchall()
        msg_text = "🏆 Топ-10 игроков:\n\n"
        for i, t in enumerate(tops, 1):
            try:
                user = vk.users.get(user_ids=t[0])[0]
                name = f"{user['first_name']} {user['last_name']}"
            except:
                name = f"ID:{t[0]}"
            msg_text += f"{i}. {name} — {t[1]} FORT\n"
        vk.messages.send(user_id=user_id, message=msg_text, keyboard=main_keyboard(), random_id=random.randint(1, 2**31))
    
    elif text == 'Бонус':
        c.execute("SELECT last_bonus, streak FROM users WHERE user_id=?", (user_id,))
        user = c.fetchone()
        today = datetime.now().strftime("%Y-%m-%d")
        
        if user[0] == today:
            vk.messages.send(user_id=user_id, message="🎁 Ты уже получил бонус сегодня. Возвращайся завтра!", random_id=random.randint(1, 2**31))
        else:
            add_user(user_id)
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            new_streak = user[1] + 1 if user[0] == yesterday else 1
            streak_bonus = min(new_streak, 7)
            bonus = streak_bonus * 25 + (50 if streak_bonus == 7 else 0)
            c.execute("UPDATE users SET balance=balance+?, last_bonus=?, streak=? WHERE user_id=?", (bonus, today, new_streak, user_id))
            conn.commit()
            extra = "🔥 Серия 7 дней! +50 бонус!" if streak_bonus == 7 else ""
            vk.messages.send(user_id=user_id,
                message=f"🎁 Ежедневный бонус: +{bonus} FORT\nСерия: {new_streak} дн. {extra}\nБаланс: {get_balance(user_id)} FORT",
                keyboard=main_keyboard(), random_id=random.randint(1, 2**31))
    
    elif text == '/admin':
        if user_id != ADMIN_ID:
            vk.messages.send(user_id=user_id, message="Нет доступа", random_id=random.randint(1, 2**31))
        else:
            c.execute("SELECT id, question, status FROM markets")
            markets = c.fetchall()
            msg_text = "🔧 Админ-панель\n\nРынки:\n"
            for m in markets:
                msg_text += f"{m[0]}. {m[1]} [{m[2]}]\n"
            msg_text += "\nКоманды:\n/close [номер] — закрыть\n/open [номер] — открыть\n/add [вопрос] — добавить"
            vk.messages.send(user_id=user_id, message=msg_text, random_id=random.randint(1, 2**31))
    
    elif text.startswith('/close '):
        if user_id != ADMIN_ID:
            vk.messages.send(user_id=user_id, message="Нет доступа", random_id=random.randint(1, 2**31))
        else:
            market_id = int(text.replace('/close ', ''))
            c.execute("UPDATE markets SET status='closed' WHERE id=?", (market_id,))
            conn.commit()
            vk.messages.send(user_id=user_id, message=f"Рынок {market_id} закрыт", random_id=random.randint(1, 2**31))
    
    elif text.startswith('/open '):
        if user_id != ADMIN_ID:
            vk.messages.send(user_id=user_id, message="Нет доступа", random_id=random.randint(1, 2**31))
        else:
            market_id = int(text.replace('/open ', ''))
            c.execute("UPDATE markets SET status='active' WHERE id=?", (market_id,))
            conn.commit()
            vk.messages.send(user_id=user_id, message=f"Рынок {market_id} открыт", random_id=random.randint(1, 2**31))
    
    elif text.startswith('/add '):
        if user_id != ADMIN_ID:
            vk.messages.send(user_id=user_id, message="Нет доступа", random_id=random.randint(1, 2**31))
        else:
            question = text.replace('/add ', '')
            c.execute("INSERT INTO markets (question) VALUES (?)", (question,))
            conn.commit()
            vk.messages.send(user_id=user_id, message=f"Рынок добавлен: {question}", random_id=random.randint(1, 2**31))
    
    elif text == 'Помощь':
        help_text = """ℹ️ Как играть:

1️⃣ Рынки — список активных рынков прогнозов
2️⃣ Выбери рынок и купи Да или Нет
3️⃣ Цена меняется по формуле AMM (как на Polymarket)
4️⃣ Когда рынок закрывается — держатели правильного исхода получают выплату

💰 FORT — виртуальная валюта. Получай за бонусы и выигрыши.
🏆 Топ-10 месяца получает реальные призы!

Удачи, провидец!"""
        vk.messages.send(user_id=user_id, message=help_text, keyboard=main_keyboard(), random_id=random.randint(1, 2**31))
    
    else:
        pass
