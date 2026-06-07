import telebot
import mysql.connector
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from config import BOT_TOKEN, DB_NAME, database_config
from Texts import texts 
import threading

telebot.apihelper.API_URL="http://tapi.bale.ai/bot{0}/{1}"

bot = telebot.TeleBot(BOT_TOKEN)

order_reg_state = {}  # {chat_id: {step, data}}
save_model_state = {}  # {chat_id: {step, data}}


@bot.message_handler(func=lambda m: m.text == texts["SAVE_MODEL"])
def handle_save_model(message):
    cid = message.chat.id
    save_model_state[cid] = {"step": "model_name", "data": {}}
    bot.send_message(cid, "نام مدل را وارد کنید:")

@bot.message_handler(func=lambda m: m.chat.id in save_model_state)
def save_model_steps(message):
    cid = message.chat.id
    state = save_model_state[cid]
    step = state["step"]
    data = state["data"]

    if step == "model_name":
        data["model_name"] = message.text
        data["items"] = []
        data["current_item"] = 0
        state["step"] = "item_count"
        bot.send_message(cid, "چند آیتم دارد؟ (عدد وارد کنید)")

    elif step == "item_count":
        if not message.text.isdigit() or int(message.text) < 1:
            bot.send_message(cid, "عدد معتبر وارد کنید:")
            return
        data["item_count"] = int(message.text)
        state["step"] = "item_name"
        bot.send_message(cid, f"نام آیتم ۱:")

    elif step == "item_name":
        idx = data["current_item"]
        data["items"].append({"name": message.text})
        # انتخاب side_type
        kb = InlineKeyboardMarkup()
        kb.row(
            InlineKeyboardButton("بدون طرف", callback_data=f"st_none_{cid}"),
            InlineKeyboardButton("چپ و راست", callback_data=f"st_both_{cid}"),
            InlineKeyboardButton("تک‌طرفه", callback_data=f"st_single_{cid}"),
        )
        bot.send_message(cid, f"نوع آیتم '{message.text}':", reply_markup=kb)
        state["step"] = "item_side"

    elif step == "done":
        pass  # در callback هندل می‌شه

@bot.callback_query_handler(func=lambda c: c.data.startswith("st_"))
def save_model_side_type(call):
    parts = call.data.split("_")
    side = parts[1]   # none / both / single
    cid = int(parts[2])
    state = save_model_state.get(cid)
    if not state:
        return
    data = state["data"]
    data["items"][-1]["side_type"] = side
    data["current_item"] += 1

    bot.answer_callback_query(call.id)
    bot.delete_message(cid, call.message.message_id)

    if data["current_item"] < data["item_count"]:
        state["step"] = "item_name"
        bot.send_message(cid, f"نام آیتم {data['current_item'] + 1}:")
    else:
        # ذخیره در دیتابیس
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(f"USE {DB_NAME}")
        cursor.execute("INSERT INTO models (name) VALUES (%s)", (data["model_name"],))
        model_id = cursor.lastrowid
        for item in data["items"]:
            cursor.execute(
                "INSERT INTO model_items (model_id, name, side_type) VALUES (%s, %s, %s)",
                (model_id, item["name"], item["side_type"])
            )
        conn.commit()
        conn.close()
        del save_model_state[cid]
        bot.send_message(cid, f"✅ مدل '{data['model_name']}' با {data['item_count']} آیتم ذخیره شد.\n(قیمت‌گذاری توسط ادمین انجام می‌شود)", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == texts["ORDER_REGISTRATION"])
def handle_order_registration(message):
    cid = message.chat.id
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"USE {DB_NAME}")
    cursor.execute("SELECT id, name FROM models")
    models = cursor.fetchall()
    conn.close()

    if not models:
        bot.send_message(cid, "هیچ مدلی ثبت نشده است.")
        return

    kb = InlineKeyboardMarkup()
    for mid, mname in models:
        kb.add(InlineKeyboardButton(mname, callback_data=f"ord_model_{mid}"))
    order_reg_state[cid] = {"step": "select_model", "data": {"items": []}}
    bot.send_message(cid, "مدل مورد نظر را انتخاب کنید:", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ord_model_"))
def ord_select_model(call):
    cid = call.message.chat.id
    mid = int(call.data.split("_")[2])
    state = order_reg_state.get(cid)
    if not state:
        return
    state["data"]["model_id"] = mid
    state["data"]["selected_items"] = []

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"USE {DB_NAME}")
    cursor.execute("SELECT id, name FROM model_items WHERE model_id=%s", (mid,))
    items = cursor.fetchall()
    conn.close()

    state["data"]["model_items"] = {i[0]: i[1] for i in items}
    state["step"] = "select_items"

    kb = InlineKeyboardMarkup()
    for iid, iname in items:
        kb.add(InlineKeyboardButton(f"➕ {iname}", callback_data=f"ord_item_{iid}"))
    kb.add(InlineKeyboardButton("✅ تأیید انتخاب‌ها", callback_data="ord_items_done"))
    bot.edit_message_text("آیتم‌های مورد نظر را انتخاب کنید:", cid, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ord_item_"))
def ord_toggle_item(call):
    cid = call.message.chat.id
    iid = int(call.data.split("_")[2])
    state = order_reg_state.get(cid)
    if not state:
        return
    selected = state["data"]["selected_items"]
    if iid in selected:
        selected.remove(iid)
    else:
        selected.append(iid)
    # نمایش وضعیت آپدیت‌شده
    items = state["data"]["model_items"]
    kb = InlineKeyboardMarkup()
    for item_id, item_name in items.items():
        prefix = "✅" if item_id in selected else "➕"
        kb.add(InlineKeyboardButton(f"{prefix} {item_name}", callback_data=f"ord_item_{item_id}"))
    kb.add(InlineKeyboardButton("✅ تأیید انتخاب‌ها", callback_data="ord_items_done"))
    bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=kb)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "ord_items_done")
def ord_items_done(call):
    cid = call.message.chat.id
    state = order_reg_state.get(cid)
    if not state or not state["data"]["selected_items"]:
        bot.answer_callback_query(call.id, "حداقل یک آیتم انتخاب کنید.")
        return
    bot.delete_message(cid, call.message.message_id)
    state["data"]["qty_queue"] = list(state["data"]["selected_items"])
    state["data"]["quantities"] = {}
    state["step"] = "enter_qty"
    _ask_qty(cid)

def _ask_qty(cid):
    state = order_reg_state[cid]
    queue = state["data"]["qty_queue"]
    if not queue:
        _ask_side_type(cid)
        return
    iid = queue[0]
    iname = state["data"]["model_items"][iid]
    bot.send_message(cid, f"تعداد '{iname}' را وارد کنید:")

@bot.message_handler(func=lambda m: order_reg_state.get(m.chat.id, {}).get("step") == "enter_qty")
def ord_enter_qty(message):
    cid = message.chat.id
    if not message.text.isdigit() or int(message.text) < 1:
        bot.send_message(cid, "عدد معتبر وارد کنید:")
        return
    state = order_reg_state[cid]
    iid = state["data"]["qty_queue"].pop(0)
    state["data"]["quantities"][iid] = int(message.text)
    _ask_qty(cid)

def _ask_side_type(cid):
    state = order_reg_state[cid]
    # پیدا کردن آیتم‌هایی که side_type != 'none'
    selected = state["data"]["selected_items"]
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"USE {DB_NAME}")
    cursor.execute(
        f"SELECT id, name, side_type FROM model_items WHERE id IN ({','.join(['%s']*len(selected))})",
        selected
    )
    rows = cursor.fetchall()
    conn.close()
    needs_side = [(r[0], r[1]) for r in rows if r[2] != "none"]
    state["data"]["side_queue"] = needs_side
    state["data"]["hand_sides"] = {}
    state["step"] = "enter_side"
    _ask_next_side(cid)

def _ask_next_side(cid):
    state = order_reg_state[cid]
    queue = state["data"]["side_queue"]
    if not queue:
        _finalize_order(cid)
        return
    iid, iname = queue[0]
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("چپ", callback_data=f"ord_side_left_{iid}"),
        InlineKeyboardButton("راست", callback_data=f"ord_side_right_{iid}"),
        InlineKeyboardButton("هر دو", callback_data=f"ord_side_none_{iid}"),
    )
    bot.send_message(cid, f"طرف '{iname}':", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ord_side_"))
def ord_select_side(call):
    cid = call.message.chat.id
    parts = call.data.split("_")
    side = parts[2]   # left / right / none
    iid = int(parts[3])
    state = order_reg_state.get(cid)
    if not state:
        return
    state["data"]["hand_sides"][iid] = side
    state["data"]["side_queue"].pop(0)
    bot.delete_message(cid, call.message.message_id)
    bot.answer_callback_query(call.id)
    _ask_next_side(cid)

def _finalize_order(cid):
    state = order_reg_state[cid]
    data = state["data"]
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"USE {DB_NAME}")

    # پیدا کردن user_id
    cursor.execute("SELECT id FROM users WHERE chat_id=%s", (cid,))
    row = cursor.fetchone()
    if not row:
        bot.send_message(cid, "ابتدا /start را بزنید.")
        conn.close()
        return
    user_id = row[0]

    # ثبت سفارش
    cursor.execute("INSERT INTO orders (user_id) VALUES (%s)", (user_id,))
    order_id = cursor.lastrowid

    # ثبت آیتم‌ها
    for iid in data["selected_items"]:
        cursor.execute("SELECT price FROM model_items WHERE id=%s", (iid,))
        price_row = cursor.fetchone()
        unit_price = price_row[0] if price_row and price_row[0] else 0
        cursor.execute(
            "INSERT INTO order_items (order_id, model_item_id, quantity, unit_price, hand_side) VALUES (%s,%s,%s,%s,%s)",
            (order_id, iid, data["quantities"][iid], unit_price, data["hand_sides"].get(iid, "none"))
        )

    conn.commit()
    conn.close()
    del order_reg_state[cid]
    bot.send_message(cid, f"✅ سفارش #{order_id} با موفقیت ثبت شد.", reply_markup=main_menu())


















def info_listener(messages):
    """
    این تابع تمام پیام‌های ورودی را قبل از پردازش توسط هندلرها، مانیتور می‌کند.
    """
    for message in messages:
        user_id = message.chat.id
        username = message.chat.username or "No Username"
        text = message.text or f"[{message.content_type}]"
        
        print(f"\n--- [New Message] ---")
        print(f"👤 User: {username} ({user_id})")
        print(f"💬 Content: {text}")
        print(f"----------------------\n")
bot.set_update_listener(info_listener)

# ---------------------------------------- database ----------------------------------------

def get_connection():
    return mysql.connector.connect(
        database=DB_NAME,
        **database_config
    )

# ---------------------------------------- activities ---------------------------------------

def orders_activities(call):
    chat_id = call.message.chat.id
    
    conn = mysql.connector.connect(**database_config, database=DB_NAME)   
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT status, COUNT(*) as cnt 
        FROM orders 
        WHERE user_id = (SELECT id FROM users WHERE chat_id = %s)
        GROUP BY status
    """, (chat_id,))
    rows = cursor.fetchall()
    cursor.close()
    
    stats = {r['status']: r['cnt'] for r in rows}
    total = sum(stats.values())
    
    status_fa = {
        'pending':     '🕐 در انتظار',
        'confirmed':   '✅ تأیید شده',
        'in_progress': '🔧 در حال انجام',
        'delivered':   '📦 تحویل داده شده',
        'cancelled':   '❌ لغو شده',
    }
    
    if total == 0:
        text = "📋 هیچ سفارشی ثبت نشده است."
    else:
        lines = ["📊 *خلاصه سفارشات شما:*\n"]
        for status, fa in status_fa.items():
            if status in stats:
                lines.append(f"{fa}: {stats[status]} عدد")
        text = "\n".join(lines)
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🕐 در انتظار",callback_data="orders_filter_pending"),
        InlineKeyboardButton("✅ تأیید شده",          callback_data="orders_filter_confirmed"),
        InlineKeyboardButton("🔧 در حال انجام",       callback_data="orders_filter_in_progress"),
        InlineKeyboardButton("📦 تحویل داده شده",    callback_data="orders_filter_delivered"),
        InlineKeyboardButton("❌ لغو شده",            callback_data="orders_filter_cancelled"),
    )
    markup.add(
        InlineKeyboardButton("➕ ثبت سفارش جدید",    callback_data="new_order"),
        InlineKeyboardButton("🚫 لغو سفارش",         callback_data="cancel_order_menu"),
    )
    markup.add(
        InlineKeyboardButton("🔙 بازگشت",            callback_data="back_more"),
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id,parse_mode="Markdown", reply_markup=markup)
    bot.answer_callback_query(call.id)

def orders_filter_activities(call):
    chat_id = call.message.chat.id
    status = call.data.replace("orders_filter_", "")

    conn = mysql.connector.connect(**database_config, database=DB_NAME)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT o.id, o.created_at, o.notes
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE u.chat_id = %s AND o.status = %s
        ORDER BY o.created_at DESC LIMIT 10
    """, (chat_id, status))
    orders = cursor.fetchall()
    cursor.close()
    conn.close()
    
    status_fa = {
        'pending': '🕐 در انتظار', 'confirmed': '✅ تأیید شده',
        'in_progress': '🔧 در حال انجام', 'delivered': '📦 تحویل داده شده',
        'cancelled': '❌ لغو شده',
    }
    
    if not orders:
        text = f"هیچ سفارشی با وضعیت *{status_fa[status]}* یافت نشد."
    else:
        lines = [f"📋 سفارشات *{status_fa[status]}*:\n"]
        for o in orders:
            notes = f" — {o['notes']}" if o['notes'] else ""
            lines.append(f"• سفارش #{o['id']} | {str(o['created_at'])[:10]}{notes}")
        text = "\n".join(lines)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 بازگشت به سفارشات", callback_data="orders"))
    
    bot.edit_message_text(text, chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)
    bot.answer_callback_query(call.id)

def cancel_order_menu_activities(call):
    chat_id = call.message.chat.id
    
    # فقط pending و confirmed قابل لغو هستند
    cursor = get_connection().cursor(dictionary=True)
    cursor.execute("""
        SELECT o.id, o.status, o.created_at
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE u.chat_id = %s AND o.status IN ('pending', 'confirmed')
        ORDER BY o.created_at DESC""", (chat_id,))
    orders = cursor.fetchall()
    cursor.close()
    
    if not orders:
        bot.answer_callback_query(call.id, "سفارش قابل لغوی وجود ندارد.", show_alert=True)
        return
    
    markup = InlineKeyboardMarkup()
    for o in orders:
        markup.add(InlineKeyboardButton(
            f"❌ لغو سفارش #{o['id']} ({str(o['created_at'])[:10]})",
            callback_data=f"do_cancel_{o['id']}"
        ))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="orders"))
    
    bot.edit_message_text("کدام سفارش را میخواهید لغو کنید؟",
                          chat_id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

def do_cancel_activities(call):
    chat_id = call.message.chat.id
    order_id = int(call.data.replace("do_cancel_", ""))
    
    conn = get_connection()
    cursor = conn.cursor()
    # بررسی مالکیت و وضعیت قابل لغو
    cursor.execute("""
        UPDATE orders o
        JOIN users u ON o.user_id = u.id
        SET o.status = 'cancelled'
        WHERE o.id = %s AND u.chat_id = %s AND o.status IN ('pending', 'confirmed')
    """, (order_id, chat_id))
    get_connection().commit()
    affected = cursor.rowcount
    cursor.close()
    
    if affected:
        bot.answer_callback_query(call.id, f"سفارش #{order_id} لغو شد.", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "امکان لغو این سفارش وجود ندارد.", show_alert=True)
    # بازگشت به منوی سفارشات
    handle_orders(call)


# ---------------------------------------- key boards ----------------------------------------

def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        KeyboardButton(texts["ORDER_REGISTRATION"]),
        KeyboardButton(texts["SAVE_MODEL"])
    )
    markup.add(
        KeyboardButton(texts["MORE"])
    )
    return markup

def more_menu():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(texts["ORDER_HISTORY"], callback_data="orders"))
    markup.add(InlineKeyboardButton(texts["FINANCE"], callback_data="finence"))
    markup.add(InlineKeyboardButton(texts["HELP"], callback_data="help"))
    markup.add(InlineKeyboardButton(texts["ABOAT_US"], callback_data="aboat_us"))
    markup.add(InlineKeyboardButton(texts["SUPORT"], callback_data="suport"))


    return markup

# ---------------------------------------- comands handlers ----------------------------------------

@bot.message_handler(commands=["start"])
def start(message):
    cid = message.chat.id

    bot.send_message(
        cid,
        texts["WELCOME"],
        reply_markup=main_menu()
    )



# ---------------------------------------- text handlers ----------------------------------------

@bot.message_handler(func=lambda message: message.text == texts["ORDER_REGISTRATION"])
def handle_order_registration(message):
    cid = message.chat.id

@bot.message_handler(func=lambda message: message.text == texts["SAVE_MODEL"])
def handle_save_model(message):
    cid = message.chat.id

@bot.message_handler(func=lambda message: message.text == texts["MORE"])
def handle_more(message):
    cid = message.chat.id

    bot.send_message(cid, texts["MORE_TEXT"], reply_markup=more_menu())


# ---------------------------------------- callback handlers ----------------------------------------


@bot.callback_query_handler(func=lambda call: call.data == "orders")
def handle_orders(call):
    orders_activities(call)
    
@bot.callback_query_handler(func=lambda call: call.data.startswith("orders_filter_"))
def handle_orders_filter(call):
    orders_filter_activities(call)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_order_menu")
def handle_cancel_order_menu(call):
    cancel_order_menu_activities(call)


@bot.callback_query_handler(func=lambda call: call.data.startswith("do_cancel_"))
def handle_do_cancel(call):
    
    do_cancel_activities(call)









@bot.callback_query_handler(func=lambda call: call.data == "finence")
def handle_finence(call):



    bot.send_message(call.message.chat.id, "")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "help")
def handle_help(call):
    bot.send_message(call.message.chat.id, texts["help_message"])
    bot.answer_callback_query(call.id)
    def send_back():
        bot.send_message(
            chat_id=call.message.chat.id,
            text=texts["MORE_TEXT"],
            reply_markup=more_menu()
        )

    threading.Timer(3, send_back).start()

@bot.callback_query_handler(func=lambda call: call.data == "aboat_us")
def handle_aboat_us(call):
    bot.send_message(call.message.chat.id, texts["aboatus_message"])
    bot.answer_callback_query(call.id)
    
    def send_back():
        bot.send_message(
            chat_id=call.message.chat.id,
            text=texts["MORE_TEXT"],
            reply_markup=more_menu()
        )

    threading.Timer(3, send_back).start() 
    
@bot.callback_query_handler(func=lambda call: call.data == "suport")
def handle_suport(call):

    bot.send_message(call.message.chat.id, texts["suport_message"])
    bot.answer_callback_query(call.id)

    def send_back():
        bot.send_message(
            chat_id=call.message.chat.id,
            text=texts["MORE_TEXT"],
            reply_markup=more_menu()
        )

    threading.Timer(3, send_back).start()
    
@bot.callback_query_handler(func=lambda call: call.data == "back_more")
def handle_suport(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    

    bot.edit_message_text(
    chat_id=chat_id,
    message_id=message_id,
    text=texts["MORE_TEXT"],
    reply_markup=more_menu()
)


print ("robot is running")
bot.infinity_polling()