import telebot
import mysql.connector
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from config import BOT_TOKEN, DB_NAME, database_config
from Texts import texts 
import threading

telebot.apihelper.API_URL="http://tapi.bale.ai/bot{0}/{1}"

bot = telebot.TeleBot(BOT_TOKEN)

order_reg_state = {}  # {chat_id: {step, data}}
save_model_state = {}  # 
admin_add_user_state = {}  
admin_edit_user_state = {}  
admin_item_state = {}  # {chat_id: {step, model_id, item_id, field}}








# در فایل dll.py

def update_model_name(self, model_id, new_name):
    query = "UPDATE models SET name = %s WHERE id = %s"
    return self.execute_query(query, (new_name, model_id))

def delete_model(self, model_id):
    query = "DELETE FROM models WHERE id = %s"
    return self.execute_query(query, (model_id,))

def count_model_items(self, model_id):
    query = "SELECT COUNT(*) FROM model_items WHERE model_id = %s"
    result = self.fetch_all(query, (model_id,))
    return result[0][0] if result else 0



@bot.message_handler(func=lambda message: message.text == "مدیریت مدل‌ها 🏗️" and message.chat.id in ADMIN_IDS)
def admin_models_list(message):
    models = db.get_models()
    markup = InlineKeyboardMarkup()
    
    for model in models:
        # نمایش هر مدل با دکمه‌های ویرایش و حذف
        markup.row(
            InlineKeyboardButton(f"📁 {model[1]}", callback_data=f"ignore"),
            InlineKeyboardButton("✏️", callback_data=f"admin_model_edit_{model[0]}"),
            InlineKeyboardButton("❌", callback_data=f"admin_model_delete_{model[0]}")
        )
    
    markup.add(InlineKeyboardButton("➕ افزودن مدل جدید", callback_data="admin_model_add"))
    markup.add(InlineKeyboardButton("🔄 مدیریت آیتم‌ها", callback_data="admin_items_manage"))
    
    bot.send_message(message.chat.id, "🏗️ **لیست مدل‌های موجود:**\nیکی از گزینه‌های زیر را انتخاب کنید:", 
                     reply_markup=markup, parse_mode="Markdown")




@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_model_delete_"))
def handle_delete_model(call):
    model_id = int(call.data.split("_")[3])
    item_count = db.count_model_items(model_id)
    
    markup = InlineKeyboardMarkup()
    if item_count > 0:
        # نمایش هشدار در صورت وجود آیتم
        markup.add(InlineKeyboardButton(f"⚠️ بله، حذف شود ({item_count} آیتم حذف می‌شوند)", 
                                             callback_data=f"confirm_model_del_{model_id}"))
    else:
        markup.add(InlineKeyboardButton("✅ تایید حذف", callback_data=f"confirm_model_del_{model_id}"))
    
    markup.add(InlineKeyboardButton("🔙 انصراف", callback_data="admin_models_list"))
    
    bot.edit_message_text(f"آیا از حذف این مدل اطمینان دارید؟\nتعداد آیتم‌های وابسته: {item_count}", 
                          call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_model_del_"))
def confirm_delete_model(call):
    model_id = int(call.data.split("_")[3])
    if db.delete_model(model_id):
        bot.answer_callback_query(call.id, "✅ مدل با موفقیت حذف شد.")
        admin_models_list(call.message) # بازگشت به لیست
    else:
        bot.answer_callback_query(call.id, "❌ خطا در حذف مدل.")





















# ---------------------------------------- database ----------------------------------------

def get_connection():
    return mysql.connector.connect(
        database=DB_NAME,
        **database_config
    )

# --------------------   --------------------

def notify_admins(text, order_id=None, markup=None):
    """ارسال نوتیفیکیشن به همه ادمین‌ها"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.chat_id FROM admins a JOIN users u ON a.user_id = u.id
    """)
    admins = cursor.fetchall()
    cursor.close()
    conn.close()
    for (admin_cid,) in admins:
        try:
            bot.send_message(admin_cid, text, parse_mode="Markdown", reply_markup=markup)
        except:
            pass

def admin_orders_list(chat_id, message_id, status="pending", edit=False):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT o.id, o.created_at, o.notes, u.name, u.phone
        FROM orders o JOIN users u ON o.user_id = u.id
        WHERE o.status = %s
        ORDER BY o.created_at DESC LIMIT 20
    """, (status,))
    orders = cursor.fetchall()
    cursor.close()
    conn.close()

    status_fa = {
        'pending': '🕐 در انتظار', 'confirmed': '✅ تأیید شده',
        'in_progress': '🔧 در حال انجام', 'delivered': '📦 تحویل داده شده',
        'cancelled': '❌ لغو شده',}

    if not orders:
        text = f"هیچ سفارشی با وضعیت *{status_fa[status]}* وجود ندارد."
    else:
        lines = [f"📋 سفارشات *{status_fa[status]}* ({len(orders)} عدد):\n"]
        for o in orders:
            note = f" — {o['notes']}" if o['notes'] else ""
            lines.append(f"• #{o['id']} | {o['name']} | {str(o['created_at'])[:10]}{note}")
        text = "\n".join(lines)

    markup = InlineKeyboardMarkup(row_width=3)
    # فیلتر وضعیت‌ها
    markup.add(
        InlineKeyboardButton("🕐 در انتظار", callback_data="admin_orders_pending"),
        InlineKeyboardButton("✅ تأیید شده", callback_data="admin_orders_confirmed"),
        InlineKeyboardButton("🔧 در حال انجام", callback_data="admin_orders_in_progress"),
        InlineKeyboardButton("📦 تحویل داده شده", callback_data="admin_orders_delivered"),
        InlineKeyboardButton("❌ لغو شده", callback_data="admin_orders_cancelled"),
    )
    for o in orders:
        markup.add(InlineKeyboardButton(
            f"🔍 #{o['id']} — {o['name']}",
            callback_data=f"admin_order_detail_{o['id']}"
        ))

    if edit:
        bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

# ---------------------------------------- activities ---------------------------------------

def is_registered(chat_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE chat_id = %s", (chat_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return True
    return False

def is_superuser(chat_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_superuser FROM users WHERE chat_id = %s", (chat_id,))
    result = cursor.fetchone()
    conn.close()
    if result and result[0]:
        return True
    return False

def is_admin(chat_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM admins a
        JOIN users u ON a.user_id = u.id
        WHERE u.chat_id = %s
    """, (chat_id,))
    result = cursor.fetchone()
    conn.close()
    return bool(result)

def orders_activities(call):
    bot.answer_callback_query(call.id)
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
    for o in orders:
        markup.add(InlineKeyboardButton(
            f"🔍 جزئیات سفارش #{o['id']}",
            callback_data=f"order_detail_{o['id']}"
        ))
    markup.add(InlineKeyboardButton("🔙 بازگشت به سفارشات", callback_data="orders"))

    
    bot.edit_message_text(text, chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)
    bot.answer_callback_query(call.id)

def cancel_order_menu_activities(call):
    chat_id = call.message.chat.id
    
    # فقط pending و confirmed قابل لغو هستند
    conn = mysql.connector.connect(**database_config, database=DB_NAME)
    cursor = conn.cursor(dictionary=True)
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
    conn.commit()              
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    
    if affected:
        bot.answer_callback_query(call.id, f"سفارش #{order_id} لغو شد.", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "امکان لغو این سفارش وجود ندارد.", show_alert=True)
    # بازگشت به منوی سفارشات
    bot.delete_message(chat_id, call.message.message_id)

    handle_orders(call)

def _ask_qty(cid):
    state = order_reg_state[cid]
    queue = state["data"]["qty_queue"]
    if not queue:
        _ask_side_type(cid)
        return
    iid = queue[0]
    iname = state["data"]["model_items"][iid]
    bot.send_message(cid, f"تعداد '{iname}' را وارد کنید:")

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

def _ask_notes(cid):
    state = order_reg_state[cid]
    state["step"] = "enter_notes"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⏭ بدون توضیحات", callback_data="ord_skip_notes"))
    bot.send_message(cid, "توضیحات سفارش را وارد کنید:", reply_markup=markup)

def _ask_next_side(cid):
    state = order_reg_state[cid]
    queue = state["data"]["side_queue"]
    if not queue:
        _ask_notes(cid)   
        return
    iid, iname = queue[0]
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("چپ", callback_data=f"ord_side_left_{iid}"),
        InlineKeyboardButton("راست", callback_data=f"ord_side_right_{iid}"),
        InlineKeyboardButton("هر دو", callback_data=f"ord_side_none_{iid}"),
    )
    bot.send_message(cid, f"طرف '{iname}':", reply_markup=markup)

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
    notes = data.get("notes")
    cursor.execute("INSERT INTO orders (user_id, notes) VALUES (%s,%s)", (user_id, notes))
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
    cursor.execute("SELECT name, phone FROM users WHERE id=%s", (user_id,))
    urow = cursor.fetchone()
    uname = urow[0] if urow else "نامشخص"
    uphone = urow[1] if urow else "—"

    conn.close()
    notify_admins(
        f"🔔 *سفارش جدید ثبت شد*\n"
        f"شماره سفارش: #{order_id}\n"
        f"کاربر: {uname} | {uphone}\n"
        f"chat_id: `{cid}`"
    )

    del order_reg_state[cid]
    bot.send_message(cid, f"✅ سفارش #{order_id} با موفقیت ثبت شد.", reply_markup=main_menu())

def order_registration(message):
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

    markup = InlineKeyboardMarkup()
    for mid, mname in models:
        markup.add(InlineKeyboardButton(mname, callback_data=f"ord_model_{mid}"))
    order_reg_state[cid] = {"step": "select_model", "data": {"items": []}}
    bot.send_message(cid, "مدل مورد نظر را انتخاب کنید:", reply_markup=markup)

def finance_activities(call):
    chat_id = call.message.chat.id
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT COALESCE(SUM(d.total_amount), 0) AS total,
               COALESCE(SUM(d.paid_amount), 0)  AS paid
        FROM debts d JOIN users u ON d.user_id = u.id
        WHERE u.chat_id = %s
    """, (chat_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    total = int(row['total'])
    paid  = int(row['paid'])
    text = (
        "💼 *وضعیت مالی شما*\n\n"
        f"📌 مجموع بدهی: {total:,} تومان\n"
        f"✅ پرداخت شده: {paid:,} تومان\n"
        f"🔴 مانده: {total - paid:,} تومان"
    )
    bot.edit_message_text(text, chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=finance_menu())
    bot.answer_callback_query(call.id)

def finance_debts_activities(call):
    chat_id = call.message.chat.id
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT d.order_id, d.total_amount, d.paid_amount, o.created_at
        FROM debts d
        JOIN orders o ON d.order_id = o.id
        JOIN users u ON d.user_id = u.id
        WHERE u.chat_id = %sORDER BY o.created_at DESC LIMIT 10
    """, (chat_id,))
    debts = cursor.fetchall()
    cursor.close()
    conn.close()

    if not debts:
        text = "هیچ بدهی‌ای ثبت نشده است."
    else:
        lines = ["📋 *بدهی سفارش‌ها:*\n"]
        for d in debts:
            remaining = int(d['total_amount']) - int(d['paid_amount'])
            lines.append(
                f"• سفارش #{d['order_id']} | {str(d['created_at'])[:10]}\n"
                f"  کل: {int(d['total_amount']):,} | پرداخت: {int(d['paid_amount']):,} | مانده: {remaining:,} تومان"
            )
        text = "\n".join(lines)

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="finance"))
    bot.edit_message_text(text, chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)
    bot.answer_callback_query(call.id)

def finance_history_activities(call):
    chat_id = call.message.chat.id
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.id, p.amount, p.status, p.submitted_at, p.note
        FROM payments p JOIN users u ON p.user_id = u.id
        WHERE u.chat_id = %s
        ORDER BY p.submitted_at DESC LIMIT 10
    """, (chat_id,))
    payments = cursor.fetchall()
    cursor.close()
    conn.close()

    status_fa = {'pending': '🕐 در انتظار', 'approved': '✅ تأیید', 'rejected': '❌ رد'}
    if not payments:
        text = "هیچ پرداختی ثبت نشده است."
    else:
        lines = ["📜 *تاریخچه پرداخت‌ها:*\n"]
        for p in payments:
            note = f"\n  دلیل: {p['note']}" if p['note'] else ""
            lines.append(
                f"• #{p['id']} | {int(p['amount']):,} تومان | "
                f"{status_fa.get(p['status'], p['status'])} | "
                f"{str(p['submitted_at'])[:10]}{note}"
            )
        text = "\n".join(lines)

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="finance"))
    bot.edit_message_text(text, chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)
    bot.answer_callback_query(call.id)

def admin_models_list(chat_id, message_id=None, edit=False):
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name FROM models ORDER BY id")
    models = cur.fetchall()
    cur.close(); conn.close()

    text = "🗂️ *مدیریت آیتم‌ها*\nیک مدل را انتخاب کنید:"
    markup = InlineKeyboardMarkup()
    for m in models:
        markup.add(InlineKeyboardButton(m['name'], callback_data=f"admin_items_model_{m['id']}"))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel_back"))

    if edit and message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

def admin_items_list(chat_id, model_id, message_id=None, edit=False):
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT name FROM models WHERE id=%s", (model_id,))
    model = cur.fetchone()
    cur.execute("SELECT id, name, price, side_type FROM model_items WHERE model_id=%s ORDER BY id", (model_id,))
    items = cur.fetchall()
    cur.close(); conn.close()

    side_label = {'none': '—', 'both': 'دو طرف', 'single': 'تک طرف'}
    text = f"📦 آیتم‌های مدل *{model['name']}*:\n\n"
    for it in items:
        price_str = f"{int(it['price']):,}" if it['price'] else "—"
        text += f"• {it['name']} | {price_str} تومان | {side_label[it['side_type']]}\n"
    if not items:
        text += "_هیچ آیتمی وجود ندارد._"

    markup = InlineKeyboardMarkup(row_width=2)
    for it in items:
        markup.row(
            InlineKeyboardButton(f"✏️ {it['name']}", callback_data=f"admin_item_edit_{it['id']}"),
            InlineKeyboardButton("🗑️", callback_data=f"admin_item_delete_{it['id']}")
        )
    markup.row(
        InlineKeyboardButton("➕ افزودن آیتم", callback_data=f"admin_item_add_{model_id}"),
        InlineKeyboardButton("🔙 بازگشت", callback_data="admin_items_back")
    )
    markup.add(InlineKeyboardButton("🏗️ مدیریت مدل‌ها (دسته‌بندی‌ها)", callback_data="admin_models_list"))
    if edit and message_id:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

def order_detail_activities(call):
    chat_id = call.message.chat.id
    order_id = int(call.data.replace("order_detail_", ""))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT o.id, o.status, o.notes, o.created_at
        FROM orders o JOIN users u ON o.user_id = u.id
        WHERE o.id = %s AND u.chat_id = %s""", (order_id, chat_id))
    order = cursor.fetchone()

    if not order:
        bot.answer_callback_query(call.id, "سفارش یافت نشد.", show_alert=True)
        conn.close()
        return

    cursor.execute("""
        SELECT mi.name, oi.quantity, oi.unit_price, oi.hand_side
        FROM order_items oi JOIN model_items mi ON oi.model_item_id = mi.id
        WHERE oi.order_id = %s
    """, (order_id,))
    items = cursor.fetchall()
    cursor.close()
    conn.close()

    status_fa = {
        'pending': '🕐 در انتظار', 'confirmed': '✅ تأیید شده',
        'in_progress': '🔧 در حال انجام', 'delivered': '📦 تحویل داده شده',
        'cancelled': '❌ لغو شده',
    }
    hand_fa = {'left': 'چپ', 'right': 'راست', 'none': '—'}
    show_price = is_superuser(chat_id)

    lines = [
        f"📦 *جزئیات سفارش #{order_id}*",
        f"وضعیت: {status_fa.get(order['status'], order['status'])}",
        f"تاریخ: {str(order['created_at'])[:10]}",
    ]
    if order['notes']:
        lines.append(f"توضیحات: {order['notes']}")

    if items:
        lines.append("\n🧾 *اقلام سفارش:*")
        total = 0
        for it in items:
            subtotal = it['quantity'] * int(it['unit_price'])
            total += subtotal
            side = f" | طرف: {hand_fa[it['hand_side']]}" if it['hand_side'] != 'none' else ""
            if show_price:
                lines.append(
                    f"• {it['name']} × {it['quantity']}"
                    f" | {int(it['unit_price']):,} تومان{side}"
                    f"\n  جمع: {subtotal:,} تومان"
                )
            else:
                lines.append(f"• {it['name']} × {it['quantity']}{side}")
        if show_price:
            lines.append(f"\n💰 *مجموع: {total:,} تومان*")
    else:
        lines.append("\n_(آیتمی ثبت نشده)_")

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data=f"orders_filter_{order['status']}"))
    bot.edit_message_text("\n".join(lines), chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)
    bot.answer_callback_query(call.id)

def _edit_user_finalize(message):
    cid = message.chat.id
    state = admin_edit_user_state.pop(cid, None)
    if not state:
        return

    field = state["field"]
    user_id = state["user_id"]
    new_value = message.text.strip()

    col = "name" if field == "name" else "phone"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {col}=%s WHERE id=%s", (new_value, user_id))
    conn.commit()
    cursor.close()
    conn.close()

    bot.send_message(cid, f"✅ اطلاعات کاربر با موفقیت به‌روز شد.")
    admin_users_list(cid)

def _add_user_get_name(message):
    cid = message.chat.id
    if cid not in admin_add_user_state:
        return
    admin_add_user_state[cid]["data"]["name"] = message.text.strip()
    msg = bot.send_message(cid, "📱 شماره تلفن کاربر را وارد کنید:")
    bot.register_next_step_handler(msg, _add_user_get_phone)

def _add_user_get_phone(message):
    cid = message.chat.id
    if cid not in admin_add_user_state:
        return
    admin_add_user_state[cid]["data"]["phone"] = message.text.strip()
    msg = bot.send_message(cid, "🆔 Chat ID کاربر را وارد کنید:")
    bot.register_next_step_handler(msg, _add_user_finalize)

def _add_user_finalize(message):
    cid = message.chat.id
    if cid not in admin_add_user_state:
        return

    data = admin_add_user_state.pop(cid)["data"]

    try:
        chat_id_new = int(message.text.strip())
    except ValueError:
        bot.send_message(cid, "❌ Chat ID باید عدد باشد. عملیات لغو شد.")
        return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (chat_id, name, phone) VALUES (%s, %s, %s)",
            (chat_id_new, data["name"], data["phone"])
        )
        conn.commit()
        bot.send_message(cid, f"✅ کاربر «{data['name']}» با موفقیت اضافه شد.")
    except Exception as e:
        bot.send_message(cid, f"❌ خطا در ثبت کاربر:\n{e}")
    finally:
        cursor.close()
        conn.close()

    admin_users_list(cid)

def admin_users_list(chat_id, message_id=None, edit=False):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, phone, chat_id FROM users ORDER BY id DESC LIMIT 50")
    users = cursor.fetchall()
    cursor.close()
    conn.close()

    if not users:
        text = "هیچ کاربری ثبت نشده است."
    else:
        lines = [f"👥 *لیست کاربران* ({len(users)} نفر):\n"]
        for u in users:
            lines.append(
                f"• `{u['id']}` | {u['name'] or '—'} | {u['phone'] or '—'} | `{u['chat_id']}`"
            )
        text = "\n".join(lines)

    markup = InlineKeyboardMarkup()
    for u in users:
        markup.row(
            InlineKeyboardButton(f"✏️ {u['name'] or u['id']}", callback_data=f"admin_user_edit_{u['id']}"),
            InlineKeyboardButton("🗑", callback_data=f"admin_user_delete_{u['id']}"),
        )
    markup.add(InlineKeyboardButton("➕ اضافه کردن کاربر", callback_data="admin_user_add"))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users_menu"))

    if edit:
        bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

def _item_edit_step(message):
    cid = message.chat.id
    state = admin_item_state.pop(cid, {})
    field = state["step"].replace("edit_", "")
    item_id = state["item_id"]
    value = message.text.strip()

    if field == "price":
        try:
            value = int(value.replace(",", ""))
        except ValueError:
            bot.send_message(cid, "⚠️ قیمت باید عدد باشد.")
            return

    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(f"UPDATE model_items SET {field}=%s WHERE id=%s", (value, item_id))
    conn.commit()
    cur.execute("SELECT model_id FROM model_items WHERE id=%s", (item_id,))
    row = cur.fetchone(); cur.close(); conn.close()

    bot.send_message(cid, "✅ ویرایش انجام شد.")
    admin_items_list(cid, row["model_id"])

def _item_add_step(message):
    cid = message.chat.id
    state = admin_item_state.get(cid, {})
    step = state.get("step")

    if step == "add_name":
        state["name"] = message.text.strip()
        state["step"] = "add_price"
        admin_item_state[cid] = state
        bot.register_next_step_handler(
            bot.send_message(cid, "💰 قیمت را وارد کنید (یا /skip برای خالی گذاشتن):"),
            _item_add_step
        )

    elif step == "add_price":
        if message.text.strip() == "/skip":
            state["price"] = None
        else:
            try:
                state["price"] = int(message.text.strip().replace(",", ""))
            except ValueError:
                bot.register_next_step_handler(
                    bot.send_message(cid, "⚠️ قیمت باید عدد باشد. دوباره وارد کنید:"),
                    _item_add_step
                )
                return
        state["step"] = "add_side"
        admin_item_state[cid] = state
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("بدون طرف", callback_data="admin_item_side_none"),
            InlineKeyboardButton("دو طرف", callback_data="admin_item_side_both"),
            InlineKeyboardButton("تک طرف", callback_data="admin_item_side_single"),
        )
        bot.send_message(cid, "🔄 نوع طرف را انتخاب کنید:", reply_markup=markup)




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

def more_menu(cid):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(texts["ORDER_HISTORY"], callback_data="orders"))
    markup.add(InlineKeyboardButton(texts["HELP"], callback_data="help"))
    markup.add(InlineKeyboardButton(texts["ABOAT_US"], callback_data="aboat_us"))
    markup.add(InlineKeyboardButton(texts["SUPORT"], callback_data="suport"))
    if is_superuser(cid):
        markup.add(InlineKeyboardButton(texts["FINANCE"], callback_data="finance"))



    return markup

def finance_menu():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("💳 پرداخت جدید",       callback_data="finance_pay"))
    markup.add(InlineKeyboardButton("📜 تاریخچه پرداخت‌ها", callback_data="finance_history"))
    markup.add(InlineKeyboardButton("📋 بدهی سفارش‌ها",     callback_data="finance_debts"))
    markup.add(InlineKeyboardButton("🔙 بازگشت",            callback_data="back_more"))
    return markup

def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        KeyboardButton("📦 مدیریت سفارشات"),
        KeyboardButton("👥 مدیریت کاربران")
    )
    markup.add(
        KeyboardButton("🛠 مدیریت آیتم‌ها"),
        KeyboardButton("مدیریت مدل‌ها 🏗️")
    )
    markup.add(
        KeyboardButton("📊 گزارش و آمار")
    )
    markup.add(
        KeyboardButton("🔙 خروج از پنل ادمین")
    )
    return markup

def admin_users_menu():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📋 لیست کاربران", callback_data="admin_users_list"))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel_back"))
    return markup

# ---------------------------------------- comands handlers ----------------------------------------

@bot.message_handler(commands=["start"])
def start(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id
    if is_admin(cid):
        bot.send_message(cid, "👨‍💼 پنل مدیریت:", reply_markup=admin_menu())
    else:
        bot.send_message(cid, texts["WELCOME"], reply_markup=main_menu())

# ---------------------------------------- text handlers ----------------------------------------

@bot.message_handler(func=lambda message: message.text == texts["ORDER_REGISTRATION"])
def handle_order_registration(message):
    if not is_registered(message.chat.id):
        return
    order_registration(message)

@bot.message_handler(func=lambda message: message.text == texts["SAVE_MODEL"])
def handle_save_model(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id
    save_model_state[cid] = {"step": "model_name", "data": {}}
    bot.send_message(cid, "نام مدل را وارد کنید:")

@bot.message_handler(func=lambda message: message.text == texts["MORE"])
def handle_more(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id

    bot.send_message(cid, texts["MORE_TEXT"], reply_markup=more_menu(cid))

@bot.message_handler(func=lambda m: m.text == "👥 مدیریت کاربران" and is_admin(m.chat.id))
def handle_admin_users(message):
    bot.send_message(message.chat.id, "👥 مدیریت کاربران:", reply_markup=admin_users_menu())

# ------------------------------------------------------------------------------------------------

@bot.message_handler(func=lambda m: m.chat.id in save_model_state)
def save_model_steps(message):
    if not is_registered(message.chat.id):
        return
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
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("بدون طرف", callback_data=f"st_none_{cid}"),
            InlineKeyboardButton("چپ و راست", callback_data=f"st_both_{cid}"),
            InlineKeyboardButton("تک‌طرفه", callback_data=f"st_single_{cid}"),
        )
        bot.send_message(cid, f"نوع آیتم '{message.text}':", reply_markup=markup)
        state["step"] = "item_side"

    elif step == "done":
        pass  # در callback هندل می‌شه

@bot.message_handler(func=lambda m: order_reg_state.get(m.chat.id, {}).get("step") == "enter_qty")
def ord_enter_qty(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id
    if not message.text.isdigit() or int(message.text) < 1:
        bot.send_message(cid, "عدد معتبر وارد کنید:")
        return
    state = order_reg_state[cid]
    iid = state["data"]["qty_queue"].pop(0)
    state["data"]["quantities"][iid] = int(message.text)
    _ask_qty(cid)

@bot.message_handler(func=lambda m: order_reg_state.get(m.chat.id, {}).get("step") == "enter_notes")
def ord_enter_notes(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id
    order_reg_state[cid]["data"]["notes"] = message.text
    _finalize_order(cid)
# ─── Admin Items Management ───────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda c: c.data == "admin_items_back")
def handle_admin_items_back(call):
    if not is_admin(call.message.chat.id):
        return
    admin_models_list(call.message.chat.id, call.message.message_id, edit=True)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_items_model_"))
def handle_admin_items_model(call):
    if not is_admin(call.message.chat.id):
        return
    model_id = int(call.data.split("_")[-1])
    admin_items_list(call.message.chat.id, model_id, call.message.message_id, edit=True)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_item_add_"))
def handle_admin_item_add(call):
    if not is_admin(call.message.chat.id):
        return
    model_id = int(call.data.split("_")[-1])
    cid = call.message.chat.id
    admin_item_state[cid] = {"step": "add_name", "model_id": model_id}
    bot.send_message(cid, "📝 نام آیتم جدید را وارد کنید:")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_item_side_"))
def handle_admin_item_side(call):
    cid = call.message.chat.id
    state = admin_item_state.get(cid, {})
    if state.get("step") != "add_side":
        bot.answer_callback_query(call.id)
        return

    side = call.data.split("_")[-1]  # none / both / single
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO model_items (model_id, name, price, side_type) VALUES (%s,%s,%s,%s)",
        (state["model_id"], state["name"], state.get("price"), side)
    )
    conn.commit(); cur.close(); conn.close()
    admin_item_state.pop(cid, None)

    bot.answer_callback_query(call.id, "✅ آیتم افزوده شد")
    admin_items_list(cid, state["model_id"], call.message.message_id, edit=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_item_edit_"))
def handle_admin_item_edit(call):
    if not is_admin(call.message.chat.id):
        return
    item_id = int(call.data.split("_")[-1])
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM model_items WHERE id=%s", (item_id,))
    item = cur.fetchone(); cur.close(); conn.close()

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✏️ نام", callback_data=f"admin_iedit_name_{item_id}"),
        InlineKeyboardButton("💰 قیمت", callback_data=f"admin_iedit_price_{item_id}"),
        InlineKeyboardButton("🔄 طرف", callback_data=f"admin_iedit_side_{item_id}"),
    )
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data=f"admin_items_model_{item['model_id']}"))

    price_str = f"{int(item['price']):,}" if item['price'] else "—"
    bot.edit_message_text(
        f"✏️ ویرایش آیتم: *{item['name']}*\nقیمت: {price_str} | طرف: {item['side_type']}",
        call.message.chat.id, call.message.message_id,
        reply_markup=markup, parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_iedit_"))
def handle_admin_iedit_field(call):
    cid = call.message.chat.id
    if not is_admin(cid):
        return
    parts = call.data.split("_")  # ['admin','iedit','field','item_id']
    field = parts[2]
    item_id = int(parts[3])

    if field == "side":
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("بدون طرف", callback_data=f"admin_ieside_none_{item_id}"),
            InlineKeyboardButton("دو طرف",   callback_data=f"admin_ieside_both_{item_id}"),
            InlineKeyboardButton("تک طرف",   callback_data=f"admin_ieside_single_{item_id}"),
        )
        bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
        return

    admin_item_state[cid] = {"step": f"edit_{field}", "item_id": item_id,"message_id": call.message.message_id}
    prompt = "نام جدید را وارد کنید:" if field == "name" else "قیمت جدید را وارد کنید:"
    bot.register_next_step_handler(bot.send_message(cid, prompt), _item_edit_step)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_ieside_"))
def handle_admin_ieside(call):
    cid = call.message.chat.id
    parts = call.data.split("_")  # ['admin','ieside','side','item_id']
    side = parts[2]
    item_id = int(parts[3])

    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("UPDATE model_items SET side_type=%s WHERE id=%s", (side, item_id))
    conn.commit()
    cur.execute("SELECT model_id FROM model_items WHERE id=%s", (item_id,))
    row = cur.fetchone(); cur.close(); conn.close()

    bot.answer_callback_query(call.id, "✅ طرف به‌روز شد")
    admin_items_list(cid, row["model_id"], call.message.message_id, edit=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_item_delete_"))
def handle_admin_item_delete(call):
    if not is_admin(call.message.chat.id):
        return
    item_id = int(call.data.split("_")[-1])
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT name FROM model_items WHERE id=%s", (item_id,))
    item = cur.fetchone(); cur.close(); conn.close()

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"admin_item_del_confirm_{item_id}"),
        InlineKeyboardButton("❌ انصراف",        callback_data="admin_items_back")
    )
    bot.edit_message_text(
        f"⚠️ آیا از حذف آیتم *{item['name']}* مطمئنید؟",
        call.message.chat.id, call.message.message_id,
        reply_markup=markup, parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_item_del_confirm_"))
def handle_admin_item_del_confirm(call):
    cid = call.message.chat.id
    if not is_admin(cid):
        return
    item_id = int(call.data.split("_")[-1])

    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT model_id FROM model_items WHERE id=%s", (item_id,))
    row = cur.fetchone()
    try:
        cur.execute("DELETE FROM model_items WHERE id=%s", (item_id,))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ آیتم حذف شد")
    except Exception as e:
        conn.rollback()
        bot.answer_callback_query(call.id, f"❌ خطا: {e}", show_alert=True)
    finally:
        cur.close(); conn.close()

    admin_items_list(cid, row["model_id"], call.message.message_id, edit=True)

@bot.message_handler(func=lambda m: m.text == "🛠 مدیریت آیتم‌ها")
def admin_items_menu(message):
    if not is_admin(message.chat.id):
        return
    
    # نمایش لیست مدل‌ها برای شروع مدیریت
    admin_models_list(message.chat.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_item_add_"))
def handle_admin_item_add_start(call):
    if not is_admin(call.message.chat.id): return
    
    model_id = int(call.data.split("_")[-1])
    admin_item_state[call.message.chat.id] = {
        'model_id': model_id,
        'step': 'wait_name',
        'data': {}
    }
    
    bot.edit_message_text(
        "📝 لطفا **نام آیتم** جدید را وارد کنید:",
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown"
    )
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda m: m.chat.id in admin_item_state)
def process_admin_item_steps(message):
    cid = message.chat.id
    state = admin_item_state[cid]
    step = state['step']
    text = message.text

    if text == "❌ انصراف":
        del admin_item_state[cid]
        bot.send_message(cid, "عملیات لغو شد.", reply_markup=main_menu(cid))
        return

    if step == 'wait_name':
        state['data']['name'] = text
        state['step'] = 'wait_price'
        bot.send_message(cid, f"آیتم: *{text}*\n\n💰 حالا **قیمت** را به عدد وارد کنید (مثلاً 500000):", parse_mode="Markdown")

    elif step == 'wait_price':
        if not text.isdigit():
            bot.send_message(cid, "⚠️ لطفا فقط عدد وارد کنید:")
            return
        
        state['data']['price'] = int(text)
        state['step'] = 'wait_side'
        
        # انتخاب نوع جهت (Side Type)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("بدون جهت", callback_data="admin_item_side_none"))
        markup.add(InlineKeyboardButton("چپ / راست", callback_data="admin_item_side_both"))
        markup.add(InlineKeyboardButton("تک جهت (فقط چپ یا راست)", callback_data="admin_item_side_single"))
        
        bot.send_message(cid, "⚙️ نوع جهت‌دهی این آیتم را انتخاب کنید:", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_item_side_"))
def handle_admin_item_side_final(call):
    cid = call.message.chat.id
    if cid not in admin_item_state: return

    side_type = call.data.replace("admin_item_side_", "")
    state = admin_item_state[cid]
    model_id = state['model_id']
    data = state['data']

    try:
        conn = get_connection()
        cur = conn.cursor()
        query = """
            INSERT INTO model_items (model_id, name, price, side_type)
            VALUES (%s, %s, %s, %s)
        """
        cur.execute(query, (model_id, data['name'], data['price'], side_type))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ آیتم با موفقیت اضافه شد")
        
        # پاکسازی State و بازگشت به لیست آیتم‌ها
        del admin_item_state[cid]
        bot.delete_message(cid, call.message.message_id)
        admin_items_list(cid, model_id) # فراخوانی تابع لیست برای نمایش تغییرات
        
    except Exception as e:
        bot.send_message(cid, f"❌ خطای دیتابیس: {e}")
    finally:
        cur.close(); conn.close()

# --- تأیید نهایی حذف ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_user_delete_confirm_"))
def handle_admin_user_delete_confirm(call): 

    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    user_id = int(call.data.split("_")[-1])
    cid = call.message.chat.id

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM admins WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        bot.send_message(cid, "🗑 کاربر با موفقیت حذف شد.")
    except Exception as e:
        bot.send_message(cid, f"❌ خطا در حذف: {e}")

    admin_users_list(cid)


@bot.callback_query_handler(func=lambda c: c.data == "admin_users_list")
def handle_admin_users_list(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    admin_users_list(call.message.chat.id, call.message.message_id, edit=True)

@bot.callback_query_handler(func=lambda c: c.data == "admin_users_menu")
def handle_admin_users_menu(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    bot.edit_message_text("👥 مدیریت کاربران:", call.message.chat.id,
                          call.message.message_id, reply_markup=admin_users_menu())

@bot.callback_query_handler(func=lambda c: c.data == "admin_panel_back")
def handle_admin_panel_back(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "👨‍💼 پنل مدیریت:", reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda c: c.data == "admin_user_add")
def handle_admin_user_add(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    admin_add_user_state[call.message.chat.id] = {"step": "get_name", "data": {}}
    msg = bot.send_message(call.message.chat.id, "👤 نام کاربر را وارد کنید:")
    bot.register_next_step_handler(msg, _add_user_get_name)


# --- منوی ویرایش: وقتی روی «ویرایش» کنار یک کاربر کلیک می‌شه ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_user_edit_"))
def handle_admin_user_edit(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    user_id = int(call.data.split("_")[-1])
    admin_edit_user_state[call.message.chat.id] = {"user_id": user_id}
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✏️ نام", callback_data=f"admin_edit_field_name_{user_id}"),
        InlineKeyboardButton("📱 تلفن", callback_data=f"admin_edit_field_phone_{user_id}"),)
    markup.add(
        InlineKeyboardButton("👑 تغییر سطح دسترسی", callback_data=f"admin_edit_field_su_{user_id}"),
        InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users_list"),
    )
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

# --- انتخاب فیلد برای ویرایش ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_edit_field_"))
def handle_admin_edit_field(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    parts = call.data.split("_")  # ["admin","edit","field","name","123"]
    field = parts[3]
    user_id = int(parts[4])
    cid = call.message.chat.id

    if field == "su":
        # toggle مستقیم بدون نیاز به مرحله بعدی
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_superuser FROM users WHERE id=%s", (user_id,))
        row = cursor.fetchone()
        new_val = 0 if row[0] else 1
        cursor.execute("UPDATE users SET is_superuser=%s WHERE id=%s", (new_val, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        status = "سوپر یوزر ✅" if new_val else "کاربر عادی"
        bot.send_message(cid, f"✅ سطح دسترسی به «{status}» تغییر کرد.")
        admin_users_list(cid)
        return

    admin_edit_user_state[cid] = {"user_id": user_id, "field": field}
    label = "نام" if field == "name" else "شماره تلفن"
    msg = bot.send_message(cid, f"✏️ {label} جدید را وارد کنید:")
    bot.register_next_step_handler(msg, _edit_user_finalize)

# --- کلیک روی «حذف کاربر» از لیست ---

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_user_delete_"))
def handle_admin_user_delete(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    user_id = int(call.data.split("_")[-1])

    # تأییدیه قبل از حذف
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"admin_user_delete_confirm_{user_id}"),
        InlineKeyboardButton("❌ انصراف", callback_data="admin_users_list"),
    )
    bot.edit_message_text(
        "⚠️ آیا مطمئن هستید؟ این کاربر حذف خواهد شد.",
        call.message.chat.id, call.message.message_id,
        reply_markup=markup
    )


# ---------------------------------------- user callback handlers ----------------------------------------

@bot.callback_query_handler(func=lambda call: call.data == "orders")
def handle_orders(call):
    if not is_registered(call.message.chat.id):
        return
    orders_activities(call)
    
@bot.callback_query_handler(func=lambda call: call.data.startswith("orders_filter_"))
def handle_orders_filter(call):
    if not is_registered(call.message.chat.id):
        return
    orders_filter_activities(call)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_order_menu")
def handle_cancel_order_menu(call):
    if not is_registered(call.message.chat.id):
        return
    cancel_order_menu_activities(call)

@bot.callback_query_handler(func=lambda call: call.data.startswith("do_cancel_"))
def handle_do_cancel(call):
    if not is_registered(call.message.chat.id):
        return
    
    do_cancel_activities(call)

@bot.callback_query_handler(func=lambda call: call.data == "new_order")
def handle_new_order(call):
    if not is_registered(call.message.chat.id):
        return
    bot.delete_message(call.message.chat.id, call.message.message_id)
    order_registration(call.message)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "finence")
def handle_finence(call):
    if not is_registered(call.message.chat.id):
        return
    if is_superuser(call.message.chat.id):

        finance_activities()
        bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "help")
def handle_help(call):
    if not is_registered(call.message.chat.id):
        return
    bot.send_message(call.message.chat.id, texts["help_message"])
    bot.answer_callback_query(call.id)
    def send_back():
        bot.send_message(
            chat_id=call.message.chat.id,
            text=texts["MORE_TEXT"],
            reply_markup=more_menu(cid=call.message.chat.id)
        )

    threading.Timer(3, send_back).start()

@bot.callback_query_handler(func=lambda call: call.data == "aboat_us")
def handle_aboat_us(call):
    if not is_registered(call.message.chat.id):
        return
    bot.send_message(call.message.chat.id, texts["aboatus_message"])
    bot.answer_callback_query(call.id)
    
    def send_back():
        bot.send_message(
            chat_id=call.message.chat.id,
            text=texts["MORE_TEXT"],
            reply_markup=more_menu(cid=call.message.chat.id)
        )

    threading.Timer(3, send_back).start() 
    
@bot.callback_query_handler(func=lambda call: call.data == "suport")
def handle_suport(call):
    if not is_registered(call.message.chat.id):
        return

    bot.send_message(call.message.chat.id, texts["suport_message"])
    bot.answer_callback_query(call.id)

    def send_back():
        bot.send_message(
            chat_id=call.message.chat.id,
            text=texts["MORE_TEXT"],
            reply_markup=more_menu(cid=call.message.chat.id)
        )

    threading.Timer(3, send_back).start()
    
@bot.callback_query_handler(func=lambda call: call.data == "back_more")
def handle_suport(call):
    if not is_registered(call.message.chat.id):
        return
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    

    bot.edit_message_text(
    chat_id=chat_id,
    message_id=message_id,
    text=texts["MORE_TEXT"],
    reply_markup=more_menu(cid=call.message.chat.id)
)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ord_side_"))
def ord_select_side(call):
    if not is_registered(call.message.chat.id):
        return
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

@bot.callback_query_handler(func=lambda c: c.data.startswith("st_"))
def save_model_side_type(call):
    if not is_registered(call.message.chat.id):
        return
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

@bot.callback_query_handler(func=lambda c: c.data.startswith("ord_model_"))
def ord_select_model(call):
    if not is_registered(call.message.chat.id):
        return
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

    markup = InlineKeyboardMarkup()
    for iid, iname in items:
        markup.add(InlineKeyboardButton(f"➕ {iname}", callback_data=f"ord_item_{iid}"))
    markup.add(InlineKeyboardButton("✅ تأیید انتخاب‌ها", callback_data="ord_items_done"))
    bot.edit_message_text("آیتم‌های مورد نظر را انتخاب کنید:", cid, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ord_item_"))
def ord_toggle_item(call):
    if not is_registered(call.message.chat.id):
        return
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
    markup = InlineKeyboardMarkup()
    for item_id, item_name in items.items():
        prefix = "✅" if item_id in selected else "➕"
        markup.add(InlineKeyboardButton(f"{prefix} {item_name}", callback_data=f"ord_item_{item_id}"))
    markup.add(InlineKeyboardButton("✅ تأیید انتخاب‌ها", callback_data="ord_items_done"))
    bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "ord_items_done")
def ord_items_done(call):
    if not is_registered(call.message.chat.id):
        return
    cid = call.message.chat.id
    state = order_reg_state.get(cid)
    if not state or not state["data"]["selected_items"]:
        bot.answer_callback_query(call.id, "حداقل یک آیتم انتخاب کنید.")
        return
    bot.delete_message(cid, call.message.message_id)
    state["data"]["qty_queue"] = list(state["data"]["selected_items"])
    state["data"]["quantities"] = {}
    state["step"] = "enter_qty"
    bot.answer_callback_query(call.id)
    _ask_qty(cid)

@bot.callback_query_handler(func=lambda c: c.data == "ord_skip_notes")
def ord_skip_notes(call):
    if not is_registered(call.message.chat.id):
        return
    cid = call.message.chat.id
    order_reg_state[cid]["data"]["notes"] = None
    bot.answer_callback_query(call.id)
    bot.delete_message(cid, call.message.message_id)
    _finalize_order(cid)

@bot.callback_query_handler(func=lambda c: c.data.startswith("order_detail_"))
def handle_order_detail(call):
    if not is_registered(call.message.chat.id): return
    order_detail_activities(call)

@bot.callback_query_handler(func=lambda c: c.data == "finance")
def handle_finance(call):
    if not is_registered(call.message.chat.id) or not is_superuser(call.message.chat.id): return
    finance_activities(call)

@bot.callback_query_handler(func=lambda c: c.data == "finance_debts")
def handle_finance_debts(call):
    if not is_registered(call.message.chat.id) or not is_superuser(call.message.chat.id): return
    finance_debts_activities(call)

@bot.callback_query_handler(func=lambda c: c.data == "finance_history")
def handle_finance_history(call):
    if not is_registered(call.message.chat.id) or not is_superuser(call.message.chat.id): return
    finance_history_activities(call)

@bot.callback_query_handler(func=lambda c: c.data == "finance_pay")
def handle_finance_pay(call):
    bot.answer_callback_query(call.id, "این بخش به زودی اضافه می‌شود.", show_alert=True)

# -------------------- Admin: مدیریت سفارشات --------------------

@bot.message_handler(func=lambda m: m.text == "📦 مدیریت سفارشات" and is_admin(m.chat.id))
def handle_admin_orders(message):
    admin_orders_list(message.chat.id, None, status="pending", edit=False)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_orders_"))
def handle_admin_orders_filter(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    status = call.data.replace("admin_orders_", "")
    admin_orders_list(call.message.chat.id, call.message.message_id, status=status, edit=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_order_detail_"))
def handle_admin_order_detail(call):
    if not is_admin(call.message.chat.id):
        return
    order_id = int(call.data.replace("admin_order_detail_", ""))
    chat_id = call.message.chat.id

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # اطلاعات سفارش + کاربر
    cursor.execute("""
        SELECT o.id, o.status, o.notes, o.created_at,
               u.name, u.phone, u.chat_id AS user_chat_id
        FROM orders o JOIN users u ON o.user_id = u.id
        WHERE o.id = %s
    """, (order_id,))
    order = cursor.fetchone()

    # آیتم‌ها
    cursor.execute("""
        SELECT mi.name, oi.quantity, oi.unit_price, oi.hand_side
        FROM order_items oi JOIN model_items mi ON oi.model_item_id = mi.id
        WHERE oi.order_id = %s
    """, (order_id,))
    items = cursor.fetchall()

    # فایل‌های ضمیمه
    cursor.execute("SELECT file_id FROM order_files WHERE order_id = %s", (order_id,))
    files = cursor.fetchall()

    cursor.close()
    conn.close()

    if not order:
        bot.answer_callback_query(call.id, "سفارش یافت نشد.", show_alert=True)
        return

    status_fa = {
        'pending': '🕐 در انتظار', 'confirmed': '✅ تأیید شده',
        'in_progress': '🔧 در حال انجام', 'delivered': '📦 تحویل داده شده',
        'cancelled': '❌ لغو شده',
    }
    hand_fa = {'left': 'چپ', 'right': 'راست', 'none': '—'}

    lines = [
        f"📦 *جزئیات سفارش #{order_id}*",
        f"وضعیت: {status_fa.get(order['status'], order['status'])}",
        f"تاریخ: {str(order['created_at'])[:16]}",
        f"\n👤 *کاربر:* {order['name']} | {order['phone']}",
        f"chat_id: `{order['user_chat_id']}`",
    ]

    if order['notes']:
        lines.append(f"\n📝 یادداشت: {order['notes']}")

    if items:
        lines.append("\n🧾 *اقلام:*")
        total = 0
        for it in items:
            subtotal = it['quantity'] * int(it['unit_price'])
            total += subtotal
            side = f" | طرف: {hand_fa[it['hand_side']]}" if it['hand_side'] != 'none' else ""
            lines.append(
                f"• {it['name']} × {it['quantity']}"
                f" | {int(it['unit_price']):,} تومان{side}"
                f"\n  جمع: {subtotal:,} تومان"
            )
            lines.append(f"\n💰 *مجموع: {total:,} تومان*")

    if files:
        lines.append(f"\n📎 فایل‌های ضمیمه: {len(files)} عدد")

    # دکمه‌های تغییر وضعیت
    markup = InlineKeyboardMarkup(row_width=2)
    next_statuses = {
        'pending':     [('✅ تأیید', 'confirmed'), ('❌ لغو', 'cancelled')],
        'confirmed':   [('🔧 شروع', 'in_progress'), ('❌ لغو', 'cancelled')],
        'in_progress': [('📦 تحویل', 'delivered')],
        'delivered':   [],
        'cancelled':   [],
    }
    for label, new_status in next_statuses.get(order['status'], []):
        markup.add(InlineKeyboardButton(
            label, callback_data=f"admin_set_status_{order_id}_{new_status}"
        ))
    markup.add(InlineKeyboardButton(
        "🔙 بازگشت", callback_data=f"admin_orders_{order['status']}"
    ))

    bot.edit_message_text("\n".join(lines), chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)

    # ارسال فایل‌ها به صورت جداگانه
    for f in files:
        try:
            bot.send_document(chat_id, f['file_id'])
        except:
            pass

    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admin_set_status_"))
def handle_admin_set_status(call):
    if not is_admin(call.message.chat.id):
        return

    # فرمت: admin_set_status_{order_id}_{new_status}
    parts = call.data.split("_", 4)  # ['admin', 'set', 'status', order_id, new_status]
    order_id = int(parts[3])
    new_status = parts[4]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status=%s WHERE id=%s", (new_status, order_id))
    conn.commit()

    cursor.execute("""
        SELECT u.chat_id, u.name FROM orders o JOIN users u ON o.user_id = u.id
        WHERE o.id = %s
    """, (order_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    status_fa = {
        'confirmed': '✅ تأیید شده', 'in_progress': '🔧 در حال انجام',
        'delivered': '📦 تحویل داده شده', 'cancelled': '❌ لغو شده',
    }

    if row:
        user_chat_id, uname = row
        bot.send_message(
            user_chat_id,
            f"📬 *وضعیت سفارش #{order_id} تغییر کرد*\n"
            f"وضعیت جدید: {status_fa.get(new_status, new_status)}",
            parse_mode="Markdown"
        )

    bot.answer_callback_query(call.id, f"وضعیت به '{status_fa.get(new_status)}' تغییر کرد.", show_alert=True)

    # رفرش جزئیات سفارش
    admin_orders_list(call.message.chat.id, call.message.message_id, status=new_status, edit=True)

# -----------------------------------------------------------------------------------------------------

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

print ("robot is running")
bot.infinity_polling()