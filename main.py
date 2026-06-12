import telebot
import mysql.connector
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from config import BOT_TOKEN, DB_NAME, database_config
from Texts import texts 
import threading
import datetime

telebot.apihelper.API_URL="http://tapi.bale.ai/bot{0}/{1}"

bot = telebot.TeleBot(BOT_TOKEN)

save_model_step = {}   
admin_add_user_step = {}  
admin_edit_user_step = {}  
admin_item_step = {} 
admin_model_step = {}
order_reg_step = {}
                   
                                                                                    
def _get_user_id_by_chat(chat_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE chat_id = %s", (chat_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row[0] if row else None


def _ask_qty(cid):
    step = order_reg_step[cid]
    queue = step["data"]["qty_queue"]
    if not queue:
        _start_side_phase(cid)
        return
    item_id = queue[0]
    item_name = step["data"]["selected_items"][item_id]["name"]
    bot.send_message(
        cid,
        texts["ASK_QTY"].format(item_name=item_name),
        parse_mode="Markdown"
    )
    step["step"] = "enter_qty"


def _start_side_phase(cid):
    step = order_reg_step[cid]
    single_ids = [
        iid for iid, info in step["data"]["selected_items"].items()
        if info["side_type"] == "single"
    ]
    step["data"]["side_queue"] = single_ids
    step["data"]["sides"] = {}
    _ask_side(cid)


def _ask_side(cid):
    step = order_reg_step[cid]
    queue = step["data"]["side_queue"]
    if not queue:
        step["step"] = "invoice_number"
        _ask_invoice(cid)
        return
    item_id = queue[0]
    item_name = step["data"]["selected_items"][item_id]["name"]
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(texts["SIDE_LEFT"],  callback_data=f"ord_side_left_{item_id}"),
        InlineKeyboardButton(texts["SIDE_RIGHT"], callback_data=f"ord_side_right_{item_id}"),
    )
    bot.send_message(
        cid,
        texts["ASK_SIDE"].format(item_name=item_name),
        parse_mode="Markdown",
        reply_markup=markup
    )
    step["step"] = "ask_side"


def _ask_invoice(cid):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(texts["SKIP_BTN"], callback_data="ord_skip_invoice"))
    bot.send_message(
        cid,
        texts["ASK_INVOICE"],
        parse_mode="Markdown",
        reply_markup=markup
    )
    order_reg_step[cid]["step"] = "invoice_number"


def _ask_customer(cid):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(texts["SKIP_BTN"], callback_data="ord_skip_customer"))
    bot.send_message(
        cid,
        texts["ASK_CUSTOMER"],
        parse_mode="Markdown",
        reply_markup=markup
    )
    order_reg_step[cid]["step"] = "customer_name"


def _ask_delivery(cid):
    bot.send_message(
        cid,
        texts["ASK_DELIVERY"],
        parse_mode="Markdown"
    )
    order_reg_step[cid]["step"] = "delivery_date"


def _ask_fabric_name(cid):
    bot.send_message(
        cid,
        texts["ASK_FABRIC"],
        parse_mode="Markdown"
    )
    order_reg_step[cid]["step"] = "fabric_name"


def _ask_notes(cid):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(texts["SKIP_BTN"], callback_data="ord_skip_notes"))
    bot.send_message(
        cid,
        texts["ASK_NOTES"],
        parse_mode="Markdown",
        reply_markup=markup
    )
    order_reg_step[cid]["step"] = "notes"


def _show_confirm(cid):
    step = order_reg_step[cid]
    d = step["data"]
    hand_fa = {"left": texts["HAND_LEFT"], "right": texts["HAND_RIGHT"], "none": "—"}

    lines = [texts["CONFIRM_HEADER"]]
    lines.append(texts["CONFIRM_MODEL"].format(model_name=d['model_name']))

    total = 0
    lines.append(texts["CONFIRM_ITEMS_HEADER"])
    for iid, info in d["selected_items"].items():
        qty = d["quantities"].get(iid, 1)
        price = info["price"] or 0
        subtotal = qty * price
        total += subtotal

        side_type = info["side_type"]
        if side_type == "single":
            hand = hand_fa.get(d["sides"].get(iid, "none"), "—")
            side_str = texts["CONFIRM_SIDE_SINGLE"].format(hand=hand)
        elif side_type == "both":
            side_str = texts["CONFIRM_SIDE_BOTH"]
        else:
            side_str = ""

        price_str = texts["CONFIRM_PRICE"].format(price=price) if price else ""
        lines.append(f"• {info['name']} × {qty}{price_str}{side_str}")
        if price:
            lines.append(texts["CONFIRM_SUBTOTAL"].format(subtotal=subtotal))

    if total:
        lines.append(texts["CONFIRM_TOTAL"].format(total=total))

    lines.append(texts["CONFIRM_INVOICE"].format(val=d['invoice_number'] or '—'))
    lines.append(texts["CONFIRM_CUSTOMER"].format(val=d['customer_name'] or '—'))
    lines.append(texts["CONFIRM_DELIVERY"].format(val=d['delivery_date'] or '—'))
    lines.append(texts["CONFIRM_FABRIC"].format(val=d['fabric_name'] or '—'))
    lines.append(texts["CONFIRM_NOTES"].format(val=d['notes'] or '—'))

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(texts["CONFIRM_YES_BTN"], callback_data="ord_confirm"),
        InlineKeyboardButton(texts["CONFIRM_NO_BTN"],  callback_data="ord_cancel"),
    )

    bot.send_message(cid, "\n".join(lines), parse_mode="Markdown", reply_markup=markup)
    order_reg_step[cid]["step"] = "confirm"


def _finalize_order(cid):
    step = order_reg_step.pop(cid, None)
    if not step:
        return
    d = step["data"]

    user_id = _get_user_id_by_chat(cid)
    if not user_id:
        bot.send_message(cid, texts["ERR_USER_NOT_FOUND"], reply_markup=main_menu())
        return

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO orders
              (user_id, invoice_number, customer_name, delivery_date, fabric_name, notes, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
        """, (
            user_id,
            d.get("invoice_number"),
            d.get("customer_name"),
            d.get("delivery_date"),
            d.get("fabric_name"),
            d.get("notes"),
        ))
        order_id = cur.lastrowid

        total_price = 0
        for iid, info in d["selected_items"].items():
            qty        = d["quantities"].get(iid, 1)
            unit_price = info["price"] or 0
            side_type  = info["side_type"]

            if side_type == "single":
                hand_side = d["sides"].get(iid, "none")
                cur.execute("""
                    INSERT INTO order_items
                      (order_id, model_item_id, quantity, unit_price, hand_side)
                    VALUES (%s, %s, %s, %s, %s)
                """, (order_id, iid, qty, unit_price, hand_side))
                total_price += qty * unit_price

            elif side_type == "both":
                for hand in ("left", "right"):
                    cur.execute("""
                        INSERT INTO order_items
                          (order_id, model_item_id, quantity, unit_price, hand_side)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (order_id, iid, qty, unit_price, hand))
                total_price += qty * unit_price * 2

            else:        
                cur.execute("""
                    INSERT INTO order_items
                      (order_id, model_item_id, quantity, unit_price, hand_side)
                    VALUES (%s, %s, %s, %s, 'none')
                """, (order_id, iid, qty, unit_price))
                total_price += qty * unit_price

        cur.execute("""
            INSERT INTO debts (order_id, user_id, total_amount)
            VALUES (%s, %s, %s)
        """, (order_id, user_id, total_price))

        conn.commit()

        bot.send_message(
            cid,
            texts["ORDER_SAVED"].format(order_id=order_id),
            parse_mode="Markdown",
            reply_markup=main_menu()
        )

        admin_text = texts["ADMIN_NEW_ORDER"].format(
            order_id=order_id,
            cid=cid,
            model_name=d['model_name'],
            customer_name=d.get('customer_name') or '—',
            fabric_name=d.get('fabric_name') or '—',
            delivery_date=d.get('delivery_date') or '—',
            total_price=total_price,
        )
        notify_admins(admin_text)

    except Exception as e:
        conn.rollback()
        bot.send_message(cid, texts["ERR_ORDER_SAVE"].format(e=e), reply_markup=main_menu())
    finally:
        cur.close(); conn.close()


                                                                                            

def get_connection():
    return mysql.connector.connect(
        database=DB_NAME,
        **database_config
    )

def db_get_models_with_count():
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT models.id, models.name, COUNT(model_items.id) AS item_count
        FROM models
        LEFT JOIN model_items ON model_items.model_id = models.id
        GROUP BY models.id, models.name
        ORDER BY models.id
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def db_add_model(name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO models (name) VALUES (%s)", (name,))
    conn.commit()
    model_id = cur.lastrowid
    cur.close()
    conn.close()
    return model_id

def db_update_model_name(model_id, new_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE models SET name=%s WHERE id=%s", (new_name, model_id))
    conn.commit()
    cur.close()
    conn.close()

def db_count_model_items(model_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM model_items WHERE model_id=%s", (model_id,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count

def db_delete_model(model_id):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM model_items WHERE model_id=%s", (model_id,))
        cur.execute("DELETE FROM models WHERE id=%s", (model_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()

                                             

def notify_admins(text, order_id=None, markup=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT users.chat_id FROM admins JOIN users ON admins.user_id = users.id
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
        SELECT orders.id, orders.created_at, orders.notes,
               orders.fabric_name, orders.customer_name, orders.delivery_date,
               users.name, users.phone
        FROM orders JOIN users ON orders.user_id = users.id
        WHERE orders.status = %s
        ORDER BY orders.created_at DESC LIMIT 20
    """, (status,))
    orders = cursor.fetchall()
    cursor.close()
    conn.close()

    status_fa = {
        'pending':     texts["STATUS_PENDING"],
        'confirmed':   texts["STATUS_CONFIRMED"],
        'in_progress': texts["STATUS_IN_PROGRESS"],
        'delivered':   texts["STATUS_DELIVERED"],
        'cancelled':   texts["STATUS_CANCELLED"],
    }

    if not orders:
        text = texts["NO_ORDERS_STATUS"].format(status=status_fa[status])
    else:
        lines = [texts["ORDERS_LIST_HEADER"].format(status=status_fa[status], count=len(orders))]
        for o in orders:
            lines.append(
                f"• #{o['id']} | {o['name']} | {str(o['created_at'])[:10]}\n"
                f"  🧵 {o['fabric_name']} | 👥 {o['customer_name']} | 📅 {o['delivery_date']}"
            )
        text = "\n".join(lines)

    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton(texts["STATUS_PENDING"],     callback_data="admin_orders_pending"),
        InlineKeyboardButton(texts["STATUS_CONFIRMED"],   callback_data="admin_orders_confirmed"),
        InlineKeyboardButton(texts["STATUS_IN_PROGRESS"], callback_data="admin_orders_in_progress"),
        InlineKeyboardButton(texts["STATUS_DELIVERED"],   callback_data="admin_orders_delivered"),
        InlineKeyboardButton(texts["STATUS_CANCELLED"],   callback_data="admin_orders_cancelled"),
    )
    for o in orders:
        markup.add(InlineKeyboardButton(
            f"🔍 #{o['id']} — {o['fabric_name']} | {o['customer_name']}",
            callback_data=f"admin_order_detail_{o['id']}"
        ))

    if edit:
        bot.edit_message_text(text, chat_id, message_id,
                              parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

                                                                                             

def is_admin(chat_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 1 FROM admins
            JOIN users ON admins.user_id = users.id
            WHERE users.chat_id = %s
        """, (chat_id,))
        result = cursor.fetchone()
        return bool(result)
    finally:
        cursor.close()
        conn.close()

def is_registered(chat_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT 1 FROM users WHERE chat_id = %s", (chat_id,))
        result = cursor.fetchone()
        return bool(result)
    finally:
        cursor.close()
        conn.close()

def is_superuser(chat_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT is_superuser FROM users WHERE chat_id = %s", (chat_id,))
        result = cursor.fetchone()
        return bool(result and result[0])
    finally:
        cursor.close()
        conn.close()

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
    conn.close()
    
    stats = {r['status']: r['cnt'] for r in rows}
    total = sum(stats.values())
    
    status_fa = {
        'pending':     texts["STATUS_PENDING"],
        'confirmed':   texts["STATUS_CONFIRMED"],
        'in_progress': texts["STATUS_IN_PROGRESS"],
        'delivered':   texts["STATUS_DELIVERED"],
        'cancelled':   texts["STATUS_CANCELLED"],
    }
    
    if total == 0:
        text = texts["NO_ORDERS"]
    else:
        lines = [texts["ORDERS_SUMMARY_HEADER"]]
        for status, fa in status_fa.items():
            if status in stats:
                lines.append(f"{fa}: {stats[status]} عدد")
        text = "\n".join(lines)
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton(texts["STATUS_PENDING"],     callback_data="orders_filter_pending"),
        InlineKeyboardButton(texts["STATUS_CONFIRMED"],   callback_data="orders_filter_confirmed"),
        InlineKeyboardButton(texts["STATUS_IN_PROGRESS"], callback_data="orders_filter_in_progress"),
        InlineKeyboardButton(texts["STATUS_DELIVERED"],   callback_data="orders_filter_delivered"),
        InlineKeyboardButton(texts["STATUS_CANCELLED"],   callback_data="orders_filter_cancelled"),
    )
    markup.add(
        InlineKeyboardButton(texts["NEW_ORDER_BTN"],    callback_data="new_order"),
        InlineKeyboardButton(texts["CANCEL_ORDER_BTN"], callback_data="cancel_order_menu"),
    )
    markup.add(
        InlineKeyboardButton(texts["BACK_BTN"], callback_data="back_more"),
    )
    
    bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)

def orders_filter_activities(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    status = call.data.replace("orders_filter_", "")

    conn = mysql.connector.connect(**database_config, database=DB_NAME)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT orders.id, orders.created_at, orders.notes, orders.fabric_name, orders.customer_name, orders.delivery_date
        FROM orders
        JOIN users ON orders.user_id = users.id
        WHERE users.chat_id = %s AND orders.status = %s
        ORDER BY orders.created_at DESC LIMIT 10
    """, (chat_id, status))
    orders = cursor.fetchall()
    cursor.close()
    conn.close()

    status_fa = {
        'pending':     texts["STATUS_PENDING"],
        'confirmed':   texts["STATUS_CONFIRMED"],
        'in_progress': texts["STATUS_IN_PROGRESS"],
        'delivered':   texts["STATUS_DELIVERED"],
        'cancelled':   texts["STATUS_CANCELLED"],
    }

    if not orders:
        text = texts["NO_ORDERS_STATUS"].format(status=status_fa[status])
    else:
        lines = [texts["ORDERS_FILTER_HEADER"].format(status=status_fa[status])]
        for o in orders:
            notes = f" | {o['notes']}" if o['notes'] else ""
            lines.append(
                f"• سفارش #{o['id']} | {str(o['created_at'])[:10]}\n"
                f"  🧵 {o['fabric_name']} | 👥 {o['customer_name']} | 📅 {o['delivery_date']}{notes}"
            )
        text = "\n".join(lines)

    markup = InlineKeyboardMarkup()
    for o in orders:
        markup.add(InlineKeyboardButton(
            f"🔍 #{o['id']} — {o['fabric_name']} | {o['customer_name']}",
            callback_data=f"order_detail_{o['id']}"
        ))
    markup.add(InlineKeyboardButton(texts["BACK_TO_ORDERS_BTN"], callback_data="orders"))

    bot.edit_message_text(text, chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)

def cancel_order_menu_activities(call):
    chat_id = call.message.chat.id
    
    conn = mysql.connector.connect(**database_config, database=DB_NAME)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT orders.id, orders.status, orders.created_at
        FROM orders
        JOIN users ON orders.user_id = users.id
        WHERE users.chat_id = %s AND orders.status IN ('pending', 'confirmed')
        ORDER BY orders.created_at DESC""", (chat_id,))
    orders = cursor.fetchall()
    cursor.close()
    
    if not orders:
        bot.answer_callback_query(call.id, texts["NO_CANCELLABLE_ORDERS"], show_alert=True)
        return
    
    markup = InlineKeyboardMarkup()
    for o in orders:
        markup.add(InlineKeyboardButton(
            texts["CANCEL_ORDER_BTN_ITEM"].format(order_id=o['id'], date=str(o['created_at'])[:10]),
            callback_data=f"do_cancel_{o['id']}"
        ))
    markup.add(InlineKeyboardButton(texts["BACK_BTN"], callback_data="orders"))
    
    bot.edit_message_text(texts["CANCEL_ORDER_PROMPT"],
                          chat_id, call.message.message_id, reply_markup=markup)
    bot.answer_callback_query(call.id)

def do_cancel_activities(call):
    chat_id = call.message.chat.id
    order_id = int(call.data.replace("do_cancel_", ""))
    
    conn = get_connection()

    cursor = conn.cursor()
    cursor.execute("""
        UPDATE orders
        JOIN users ON orders.user_id = users.id
        SET orders.status = 'cancelled'
        WHERE orders.id = %s AND users.chat_id = %s AND orders.status IN ('pending', 'confirmed')
    """, (order_id, chat_id))
    conn.commit()              
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    
    if affected:
        bot.answer_callback_query(call.id, texts["ORDER_CANCELLED_OK"].format(order_id=order_id), show_alert=True)
    else:
        bot.answer_callback_query(call.id, texts["ORDER_CANCEL_FAIL"], show_alert=True)
    bot.delete_message(chat_id, call.message.message_id)

    handle_orders(call)

def finance_activities(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT COALESCE(SUM(debts.total_amount), 0) AS total,
               COALESCE(SUM(debts.paid_amount), 0)  AS paid
        FROM users
        LEFT JOIN debts ON debts.user_id = users.id
        WHERE users.chat_id = %s
    """, (chat_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    total = int(row['total'])
    paid  = int(row['paid'])
    text = texts["FINANCE_SUMMARY"].format(total=total, paid=paid, remaining=total - paid)
    bot.edit_message_text(text, chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=finance_menu())

def finance_debts_activities(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT debts.order_id, debts.total_amount, debts.paid_amount, orders.created_at
        FROM debts
        JOIN orders ON debts.order_id = orders.id
        JOIN users ON debts.user_id = users.id
        WHERE users.chat_id = %s ORDER BY orders.created_at DESC LIMIT 10
    """, (chat_id,))
    debts = cursor.fetchall()
    cursor.close()
    conn.close()

    if not debts:
        text = texts["NO_DEBTS"]
    else:
        lines = [texts["DEBTS_LIST_HEADER"]]
        for d in debts:
            remaining = int(d['total_amount']) - int(d['paid_amount'])
            lines.append(
                f"• سفارش #{d['order_id']} | {str(d['created_at'])[:10]}\n"
                f"  کل: {int(d['total_amount']):,} | پرداخت: {int(d['paid_amount']):,} | مانده: {remaining:,} تومان"
            )
        text = "\n".join(lines)

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(texts["BACK_BTN"], callback_data="finance"))
    bot.edit_message_text(text, chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)

def finance_history_activities(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT payments.id, payments.amount, payments.status, payments.submitted_at, payments.note
        FROM payments JOIN users ON payments.user_id = users.id
        WHERE users.chat_id = %s
        ORDER BY payments.submitted_at DESC LIMIT 10
    """, (chat_id,))
    payments = cursor.fetchall()
    cursor.close()
    conn.close()

    status_fa = {
        'pending':  texts["PAY_STATUS_PENDING"],
        'approved': texts["PAY_STATUS_APPROVED"],
        'rejected': texts["PAY_STATUS_REJECTED"],
    }
    if not payments:
        text = texts["NO_PAYMENTS"]
    else:
        lines = [texts["PAYMENTS_HISTORY_HEADER"]]
        for p in payments:
            note = f"\n  دلیل: {p['note']}" if p['note'] else ""
            lines.append(
                f"• #{p['id']} | {int(p['amount']):,} تومان | "
                f"{status_fa.get(p['status'], p['status'])} | "
                f"{str(p['submitted_at'])[:10]}{note}"
            )
        text = "\n".join(lines)

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(texts["BACK_BTN"], callback_data="finance"))
    bot.edit_message_text(text, chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)

def admin_items_list(chat_id, model_id, message_id=None, edit=False):
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT name FROM models WHERE id=%s", (model_id,))
    model = cur.fetchone()
    cur.execute("SELECT id, name, price, side_type FROM model_items WHERE model_id=%s ORDER BY id", (model_id,))
    items = cur.fetchall()
    cur.close(); conn.close()

    side_label = {
        'none':   texts["SIDE_TYPE_NONE"],
        'both':   texts["SIDE_TYPE_BOTH"],
        'single': texts["SIDE_TYPE_SINGLE"],
    }
    text = texts["ADMIN_ITEMS_HEADER"].format(model_name=model['name'])
    for it in items:
        price_str = f"{int(it['price']):,}" if it['price'] else "—"
        text += f"• {it['name']} | {price_str} تومان | {side_label[it['side_type']]}\n"
    if not items:
        text += texts["NO_ITEMS"]

    markup = InlineKeyboardMarkup(row_width=2)
    for it in items:
        markup.row(
            InlineKeyboardButton(f"✏️ {it['name']}", callback_data=f"admin_item_edit_{it['id']}"),
            InlineKeyboardButton("🗑️", callback_data=f"admin_item_delete_{it['id']}")
        )
    markup.row(
        InlineKeyboardButton(texts["ADD_ITEM_BTN"],  callback_data=f"admin_item_add_{model_id}"),
        InlineKeyboardButton(texts["BACK_BTN"],      callback_data="admin_items_back")
    )

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
        SELECT orders.id, orders.status, orders.notes, orders.created_at,
        orders.fabric_name, orders.customer_name, orders.delivery_date, orders.invoice_number
        FROM orders JOIN users ON orders.user_id = users.id
        WHERE orders.id = %s AND users.chat_id = %s
    """, (order_id, chat_id))
    order = cursor.fetchone()

    if not order:
        bot.answer_callback_query(call.id, texts["ORDER_NOT_FOUND"], show_alert=True)
        conn.close()
        return

    cursor.execute("""
        SELECT model_items.name, order_items.quantity, order_items.unit_price, order_items.hand_side
        FROM order_items JOIN model_items ON order_items.model_item_id = model_items.id
        WHERE order_items.order_id = %s
    """, (order_id,))
    items = cursor.fetchall()
    cursor.close()
    conn.close()

    status_fa = {
        'pending':     texts["STATUS_PENDING"],
        'confirmed':   texts["STATUS_CONFIRMED"],
        'in_progress': texts["STATUS_IN_PROGRESS"],
        'delivered':   texts["STATUS_DELIVERED"],
        'cancelled':   texts["STATUS_CANCELLED"],
    }
    hand_fa = {
        'left':  texts["HAND_LEFT_PLAIN"],
        'right': texts["HAND_RIGHT_PLAIN"],
        'none':  "—",
    }
    show_price = is_superuser(chat_id)

    lines = [
        texts["ORDER_DETAIL_HEADER"].format(order_id=order_id),
        texts["ORDER_DETAIL_STATUS"].format(status=status_fa.get(order['status'], order['status'])),
        texts["ORDER_DETAIL_FABRIC"].format(val=order['fabric_name']),
        texts["ORDER_DETAIL_CUSTOMER"].format(val=order['customer_name']),
        texts["ORDER_DETAIL_DELIVERY"].format(val=order['delivery_date']),
        texts["ORDER_DETAIL_DATE"].format(val=str(order['created_at'])[:10]),
    ]
    if order['invoice_number']:
        lines.append(texts["ORDER_DETAIL_INVOICE"].format(val=order['invoice_number']))
    if order['notes']:
        lines.append(texts["ORDER_DETAIL_NOTES"].format(val=order['notes']))

    if items:
        lines.append(texts["ORDER_DETAIL_ITEMS_HEADER"])
        total = 0
        for it in items:
            subtotal = it['quantity'] * int(it['unit_price'])
            total += subtotal
            side = texts["ORDER_DETAIL_SIDE"].format(hand=hand_fa[it['hand_side']]) if it['hand_side'] != 'none' else ""
            if show_price:
                lines.append(
                    f"• {it['name']} × {it['quantity']}"
                    f" | {int(it['unit_price']):,} تومان{side}"
                    f"\n  جمع: {subtotal:,} تومان"
                )
            else:
                lines.append(f"• {it['name']} × {it['quantity']}{side}")
        if show_price:
            lines.append(texts["ORDER_DETAIL_TOTAL"].format(total=total))
    else:
        lines.append(texts["NO_ITEMS_REGISTERED"])

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(texts["BACK_BTN"],
                                    callback_data=f"orders_filter_{order['status']}"))
    bot.edit_message_text("\n".join(lines), chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)
    bot.answer_callback_query(call.id)

def _edit_user_finalize(message):
    cid = message.chat.id
    step = admin_edit_user_step.pop(cid, None)
    if not step:
        return

    field = step["field"]
    user_id = step["user_id"]
    new_value = message.text.strip()

    col = "name" if field == "name" else "phone"
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {col}=%s WHERE id=%s", (new_value, user_id))
    conn.commit()
    cursor.close()
    conn.close()

    bot.send_message(cid, texts["USER_UPDATED_OK"])
    admin_users_list(cid)

def _add_user_get_name(message):
    cid = message.chat.id
    if cid not in admin_add_user_step:
        return
    admin_add_user_step[cid]["data"]["name"] = message.text.strip()
    msg = bot.send_message(cid, texts["ASK_USER_PHONE"])
    bot.register_next_step_handler(msg, _add_user_get_phone)

def _add_user_get_phone(message):
    cid = message.chat.id
    if cid not in admin_add_user_step:
        return
    admin_add_user_step[cid]["data"]["phone"] = message.text.strip()
    msg = bot.send_message(cid, texts["ASK_USER_CHATID"])
    bot.register_next_step_handler(msg, _add_user_finalize)

def _add_user_finalize(message):
    cid = message.chat.id
    if cid not in admin_add_user_step:
        return

    data = admin_add_user_step.pop(cid)["data"]

    try:
        chat_id_new = int(message.text.strip())
    except ValueError:
        bot.send_message(cid, texts["ERR_CHATID_NOT_NUMBER"])
        return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (chat_id, name, phone) VALUES (%s, %s, %s)",
            (chat_id_new, data["name"], data["phone"])
        )
        conn.commit()
        bot.send_message(cid, texts["USER_ADDED_OK"].format(name=data['name']))
    except Exception as e:
        bot.send_message(cid, texts["ERR_USER_SAVE"].format(e=e))
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
        text = texts["NO_USERS"]
    else:
        lines = [texts["USERS_LIST_HEADER"].format(count=len(users))]
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
    markup.add(InlineKeyboardButton(texts["ADD_USER_BTN"],  callback_data="admin_user_add"))
    markup.add(InlineKeyboardButton(texts["BACK_BTN"],      callback_data="admin_users_menu"))

    if edit:
        bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

def _item_edit_step(message):
    cid = message.chat.id
    step = admin_item_step.pop(cid, {})
    field = step["step"].replace("edit_", "")
    item_id = step["item_id"]
    value = message.text.strip()

    if field == "price":
        try:
            value = int(value.replace(",", ""))
        except ValueError:
            bot.send_message(cid, texts["ERR_PRICE_NOT_NUMBER"])
            return

    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(f"UPDATE model_items SET {field}=%s WHERE id=%s", (value, item_id))
    conn.commit()
    cur.execute("SELECT model_id FROM model_items WHERE id=%s", (item_id,))
    row = cur.fetchone(); cur.close(); conn.close()

    bot.send_message(cid, texts["EDIT_DONE"])
    admin_items_list(cid, row["model_id"])

def admin_models_list(chat_id, message_id=None, edit=False):
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT models.id, models.name, COUNT(model_items.id) AS item_count
        FROM models
        LEFT JOIN model_items ON model_items.model_id = models.id
        GROUP BY models.id, models.name
        ORDER BY models.id
    """)
    models = cur.fetchall()
    cur.close()
    conn.close()

    if models:
        lines = [texts["ADMIN_ITEMS_MANAGE_HEADER"]]
        for m in models:
            lines.append(f"• *{m['name']}* — {m['item_count']} آیتم")
        text = "\n".join(lines)
    else:
        text = texts["ADMIN_ITEMS_MANAGE_EMPTY"]

    markup = InlineKeyboardMarkup()
    for m in models:
        markup.add(InlineKeyboardButton(
            f"📦 {m['name']}  ({m['item_count']})",
            callback_data=f"admin_items_model_{m['id']}"
        ))
    markup.add(InlineKeyboardButton(texts["BACK_BTN"], callback_data="admin_panel_back"))

    if edit and message_id:
        bot.edit_message_text(text, chat_id, message_id,
                              parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, text,
                         parse_mode="Markdown", reply_markup=markup)

                                                               

def show_models_list(chat_id, message_id=None, edit=False):
    models = db_get_models_with_count()

    if models:
        lines = [texts["MODELS_MANAGE_HEADER"]]
        for m in models:
            lines.append(f"• *{m['name']}* — {m['item_count']} آیتم")
        text = "\n".join(lines)
    else:
        text = texts["MODELS_MANAGE_EMPTY"]

    markup = InlineKeyboardMarkup()
    for m in models:
        markup.row(
            InlineKeyboardButton(f"📁 {m['name']}  ({m['item_count']})",
                                 callback_data=f"mdl_items_{m['id']}"),
            InlineKeyboardButton("✏️", callback_data=f"mdl_edit_{m['id']}"),
            InlineKeyboardButton("🗑️", callback_data=f"mdl_delete_{m['id']}"),
        )
    markup.add(InlineKeyboardButton(texts["ADD_MODEL_BTN"],  callback_data="mdl_add"))
    markup.add(InlineKeyboardButton(texts["BACK_TO_PANEL_BTN"], callback_data="admin_panel_back"))

    if edit and message_id:
        bot.edit_message_text(text, chat_id, message_id,
                              parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

                                                                                              

def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        KeyboardButton(texts["ORDER_REGISTRATION"]),
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
    markup.add(InlineKeyboardButton(texts["FINANCE_NEW_PAYMENT"],     callback_data="finance_pay"))
    markup.add(InlineKeyboardButton(texts["FINANCE_PAYMENT_HISTORY"], callback_data="finance_history"))
    markup.add(InlineKeyboardButton(texts["FINANCE_DEBTS"],           callback_data="finance_debts"))
    markup.add(InlineKeyboardButton(texts["BACK_BTN"],                callback_data="back_more"))
    return markup

def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        KeyboardButton(texts["ADMIN_ORDERS_BTN"]),
        KeyboardButton(texts["ADMIN_USERS_BTN"])
    )
    markup.add(
        KeyboardButton(texts["ADMIN_ITEMS_BTN"]),
        KeyboardButton(texts["ADMIN_MODELS_BTN"])
    )
    markup.add(
        KeyboardButton(texts["ADMIN_STATS_BTN"])
    )
    return markup

def admin_users_menu():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(texts["USERS_LIST_BTN"], callback_data="admin_users_list"))
    markup.add(InlineKeyboardButton(texts["BACK_BTN"],       callback_data="admin_panel_back"))
    return markup

                                                                                                    

@bot.message_handler(commands=["cancel"])
def handle_cancel(message):
    cid = message.chat.id
    cancelled = False

    if cid in order_reg_step:
        del order_reg_step[cid]
        cancelled = True

    if cid in admin_item_step:
        del admin_item_step[cid]
        cancelled = True

    if cid in admin_model_step:
        del admin_model_step[cid]
        cancelled = True

    if cid in admin_add_user_step:
        del admin_add_user_step[cid]
        cancelled = True

    if cid in admin_edit_user_step:
        del admin_edit_user_step[cid]
        cancelled = True

    if cancelled:
        if is_admin(cid):
            bot.send_message(cid, texts["OPERATION_CANCELLED"], reply_markup=admin_menu())
        else:
            bot.send_message(cid, texts["OPERATION_CANCELLED"], reply_markup=main_menu())
    else:
        if is_admin(cid):
            bot.send_message(cid, texts["NO_ACTIVE_OPERATION"], reply_markup=admin_menu())
        else:
            bot.send_message(cid, texts["NO_ACTIVE_OPERATION"], reply_markup=main_menu())

@bot.message_handler(commands=["start"])
def start(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id
    if is_admin(cid):
        bot.send_message(cid, texts["ADMIN_PANEL_HEADER"], reply_markup=admin_menu())
    else:
        bot.send_message(cid, texts["WELCOME"], reply_markup=main_menu())

                                                                                                 

@bot.message_handler(func=lambda message: message.text == texts["MORE"])
def handle_more(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id
    bot.send_message(cid, texts["MORE_TEXT"], reply_markup=more_menu(cid))

@bot.message_handler(func=lambda message: message.text == texts["ADMIN_USERS_BTN"] and is_admin(message.chat.id))
def handle_admin_users(message):
    bot.send_message(message.chat.id, texts["ADMIN_USERS_HEADER"], reply_markup=admin_users_menu())

@bot.message_handler(func=lambda message: message.text == texts["ADMIN_MODELS_BTN"] and is_admin(message.chat.id))
def handle_admin_models_btn(message):
    show_models_list(message.chat.id)

                                                                                    
          
                                                                                    

@bot.message_handler(func=lambda message: message.text == texts["ORDER_REGISTRATION"])
def handle_order_registration_btn(message):
    if not is_registered(message.chat.id):
        return
    _start_order(message.chat.id)


@bot.callback_query_handler(func=lambda call: call.data == "new_order")
def handle_new_order_callback(call):
    if not is_registered(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    _start_order(call.message.chat.id)


def _start_order(cid):
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT models.id, models.name, COUNT(model_items.id) AS item_count
        FROM models
        LEFT JOIN model_items ON model_items.model_id = models.id
        GROUP BY models.id, models.name
        ORDER BY models.id
    """)
    models = cur.fetchall()
    cur.close(); conn.close()

    if not models:
        bot.send_message(cid, texts["NO_MODELS_DEFINED"])
        return

    markup = InlineKeyboardMarkup()
    for m in models:
        markup.add(InlineKeyboardButton(
            texts["MODEL_BTN"].format(model_name=m['name'], item_count=m['item_count']),
            callback_data=f"ord_model_{m['id']}"
        ))
    markup.add(InlineKeyboardButton(texts["CANCEL_BTN"], callback_data="ord_cancel"))

    order_reg_step[cid] = {
        "step": "select_model",
        "data": {
            "model_id": None,
            "model_name": None,
            "selected_items": {},
            "qty_queue": [],
            "quantities": {},
            "side_queue": [],
            "sides": {},
            "invoice_number": None,
            "customer_name": None,
            "delivery_date": None,
            "fabric_name": None,
            "notes": None,
        }
    }

    bot.send_message(
        cid,
        texts["SELECT_MODEL_PROMPT"],
        parse_mode="Markdown",
        reply_markup=markup
    )


                                                                                   

@bot.callback_query_handler(func=lambda call: call.data.startswith("ord_model_"))
def handle_ord_model(call):
    if not is_registered(call.message.chat.id):
        return
    cid = call.message.chat.id
    step = order_reg_step.get(cid)
    if not step:
        bot.answer_callback_query(call.id)
        return

    model_id = int(call.data.split("_")[-1])

    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, name FROM models WHERE id=%s", (model_id,))
    model = cur.fetchone()
    cur.execute(
        "SELECT id, name, price, side_type FROM model_items WHERE model_id=%s ORDER BY id",
        (model_id,)
    )
    items = cur.fetchall()
    cur.close(); conn.close()

    if not model or not items:
        bot.answer_callback_query(call.id, texts["MODEL_NO_ITEMS"], show_alert=True)
        return

    bot.answer_callback_query(call.id)
    step["data"]["model_id"]   = model_id
    step["data"]["model_name"] = model["name"]
    step["step"] = "select_items"

    _show_items_keyboard(cid, items, call.message.message_id, edit=True)


def _show_items_keyboard(cid, items=None, message_id=None, edit=False):
    step = order_reg_step[cid]
    model_id = step["data"]["model_id"]
    selected = step["data"]["selected_items"]

    if items is None:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id, name, price, side_type FROM model_items WHERE model_id=%s ORDER BY id",
            (model_id,)
        )
        items = cur.fetchall()
        cur.close(); conn.close()

    markup = InlineKeyboardMarkup()
    for it in items:
        iid = it["id"]
        checked = "✅" if iid in selected else "⬜"
        price_str = f" — {int(it['price']):,}" if it['price'] else ""
        markup.add(InlineKeyboardButton(
            f"{checked} {it['name']}{price_str}",
            callback_data=f"ord_item_toggle_{iid}"
        ))

    done_label = texts["CONFIRM_SELECTION_BTN"].format(count=len(selected)) if selected else texts["CONFIRM_SELECTION_BTN_EMPTY"]
    markup.add(InlineKeyboardButton(done_label, callback_data="ord_items_done"))
    markup.add(InlineKeyboardButton(texts["CANCEL_BTN"], callback_data="ord_cancel"))

    text = texts["SELECT_ITEMS_PROMPT"].format(model_name=step['data']['model_name'])

    if edit and message_id:
        try:
            bot.edit_message_text(
                text, cid, message_id,
                parse_mode="Markdown", reply_markup=markup
            )
        except Exception:
            bot.send_message(cid, text, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(cid, text, parse_mode="Markdown", reply_markup=markup)


                                                                                   

@bot.callback_query_handler(func=lambda call: call.data.startswith("ord_item_toggle_"))
def handle_ord_item_toggle(call):
    if not is_registered(call.message.chat.id):
        return
    cid = call.message.chat.id
    step = order_reg_step.get(cid)
    if not step or step["step"] != "select_items":
        bot.answer_callback_query(call.id)
        return

    item_id = int(call.data.split("_")[-1])
    selected = step["data"]["selected_items"]

    if item_id in selected:
        del selected[item_id]
        bot.answer_callback_query(call.id, texts["ITEM_REMOVED"])
    else:
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, name, price, side_type FROM model_items WHERE id=%s", (item_id,))
        item = cur.fetchone()
        cur.close(); conn.close()

        if item:
            selected[item_id] = {
                "name":      item["name"],
                "price":     int(item["price"]) if item["price"] else 0,
                "side_type": item["side_type"],
            }
            bot.answer_callback_query(call.id, texts["ITEM_SELECTED"])
        else:
            bot.answer_callback_query(call.id, texts["ERR_GENERIC"])
            return

    _show_items_keyboard(cid, message_id=call.message.message_id, edit=True)


                                                                                 

@bot.callback_query_handler(func=lambda call: call.data == "ord_items_done")
def ord_items_done(call):
    if not is_registered(call.message.chat.id):
        return
    cid = call.message.chat.id
    step = order_reg_step.get(cid)

    if not step or not step["data"]["selected_items"]:
        bot.answer_callback_query(call.id, texts["ERR_SELECT_MIN_ONE"], show_alert=True)
        return

    bot.answer_callback_query(call.id)
    bot.delete_message(cid, call.message.message_id)

    step["data"]["qty_queue"] = sorted(step["data"]["selected_items"].keys())
    step["data"]["quantities"] = {}
    step["step"] = "enter_qty"
    _ask_qty(cid)


                                                                                   

@bot.message_handler(func=lambda message: order_reg_step.get(message.chat.id, {}).get("step") == "enter_qty")
def handle_ord_qty(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id
    step = order_reg_step[cid]
    text = message.text.strip()

    if not text.isdigit() or int(text) < 1:
        bot.send_message(cid, texts["ERR_QTY_INVALID"])
        return

    queue = step["data"]["qty_queue"]
    item_id = queue.pop(0)
    step["data"]["quantities"][item_id] = int(text)

    if queue:
        _ask_qty(cid)
    else:
        _start_side_phase(cid)


                                                                                   

@bot.callback_query_handler(func=lambda call: call.data.startswith("ord_side_"))
def handle_ord_side(call):
    if not is_registered(call.message.chat.id):
        return
    cid = call.message.chat.id
    step = order_reg_step.get(cid)
    if not step or step["step"] != "ask_side":
        bot.answer_callback_query(call.id)
        return

    parts  = call.data.split("_")                                
    hand   = parts[2]                                  
    item_id = int(parts[3])

    queue = step["data"]["side_queue"]
    if not queue or queue[0] != item_id:
        bot.answer_callback_query(call.id)
        return

    queue.pop(0)
    step["data"]["sides"][item_id] = hand
    bot.answer_callback_query(call.id)
    bot.delete_message(cid, call.message.message_id)

    _ask_side(cid)


                                                                                   

@bot.callback_query_handler(func=lambda call: call.data == "ord_skip_invoice")
def ord_skip_invoice(call):
    if not is_registered(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    cid = call.message.chat.id
    order_reg_step[cid]["data"]["invoice_number"] = None
    bot.delete_message(cid, call.message.message_id)
    _ask_customer(cid)


@bot.message_handler(func=lambda message: order_reg_step.get(message.chat.id, {}).get("step") == "invoice_number")
def handle_ord_invoice(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id
    text = message.text.strip()

    if text == "/skip":
        order_reg_step[cid]["data"]["invoice_number"] = None
    else:
        order_reg_step[cid]["data"]["invoice_number"] = text

    _ask_customer(cid)


                                                                                   

@bot.callback_query_handler(func=lambda call: call.data == "ord_skip_customer")
def ord_skip_customer(call):
    if not is_registered(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    cid = call.message.chat.id
    order_reg_step[cid]["data"]["customer_name"] = None
    bot.delete_message(cid, call.message.message_id)
    _ask_delivery(cid)


@bot.message_handler(func=lambda message: order_reg_step.get(message.chat.id, {}).get("step") == "customer_name")
def handle_ord_customer(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id
    text = message.text.strip()

    if text == "/skip":
        order_reg_step[cid]["data"]["customer_name"] = None
    else:
        order_reg_step[cid]["data"]["customer_name"] = text

    _ask_delivery(cid)


                                                                                   

@bot.message_handler(func=lambda message: order_reg_step.get(message.chat.id, {}).get("step") == "delivery_date")
def handle_ord_delivery(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id
    text = message.text.strip()

    import re
    if not re.match(r"^\d{4}/\d{2}/\d{2}$", text):
        bot.send_message(
            cid,
            texts["ERR_DATE_FORMAT"],
            parse_mode="Markdown"
        )
        return

    order_reg_step[cid]["data"]["delivery_date"] = text
    _ask_fabric_name(cid)


                                                                                   

@bot.message_handler(func=lambda message: order_reg_step.get(message.chat.id, {}).get("step") == "fabric_name")
def handle_ord_fabric_name(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id
    text = message.text.strip()

    if not text:
        bot.send_message(cid, texts["ERR_FABRIC_EMPTY"])
        return

    order_reg_step[cid]["data"]["fabric_name"] = text
    _ask_notes(cid)


                                                                                   

@bot.callback_query_handler(func=lambda call: call.data == "ord_skip_notes")
def ord_skip_notes(call):
    if not is_registered(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    cid = call.message.chat.id
    order_reg_step[cid]["data"]["notes"] = None
    bot.delete_message(cid, call.message.message_id)
    _show_confirm(cid)


@bot.message_handler(func=lambda message: order_reg_step.get(message.chat.id, {}).get("step") == "notes")
def handle_ord_notes(message):
    if not is_registered(message.chat.id):
        return
    cid = message.chat.id
    text = message.text.strip()

    if text == "/skip":
        order_reg_step[cid]["data"]["notes"] = None
    else:
        order_reg_step[cid]["data"]["notes"] = text

    _show_confirm(cid)


                                                                                   

@bot.callback_query_handler(func=lambda call: call.data == "ord_confirm")
def handle_ord_confirm(call):
    if not is_registered(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    cid = call.message.chat.id
    bot.delete_message(cid, call.message.message_id)
    _finalize_order(cid)


                                                                                   

@bot.callback_query_handler(func=lambda call: call.data == "ord_cancel")
def handle_ord_cancel(call):
    if not is_registered(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    cid = call.message.chat.id
    order_reg_step.pop(cid, None)
    bot.delete_message(cid, call.message.message_id)
    bot.send_message(cid, texts["ORDER_REG_CANCELLED"], reply_markup=main_menu())


@bot.callback_query_handler(func=lambda call: call.data.startswith("nmdl_side_"))
def handle_new_model_item_side(call):
    if not is_admin(call.message.chat.id):
        return
    cid = call.message.chat.id
    step = admin_model_step.get(cid)

    if not step or step.get("step") != "new_item_side":
        bot.answer_callback_query(call.id)
        return

    side = call.data.replace("nmdl_side_", "")                         
    data = step["data"]
    data["items"][-1]["side_type"] = side
    data["current_item"] += 1

    bot.answer_callback_query(call.id)
    bot.delete_message(cid, call.message.message_id)

    if data["current_item"] < data["item_count"]:
        step["step"] = "new_item_name"
        admin_model_step[cid] = step
        bot.send_message(cid, texts["ASK_ITEM_NAME_N"].format(n=data['current_item'] + 1))

    else:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO models (name) VALUES (%s)", (data["name"],))
        model_id = cursor.lastrowid
        for item in data["items"]:
            cursor.execute(
                "INSERT INTO model_items (model_id, name, side_type) VALUES (%s, %s, %s)",
                (model_id, item["name"], item["side_type"])
            )
        conn.commit()
        cursor.close()
        conn.close()

        admin_model_step.pop(cid, None)
        bot.send_message(
            cid,
            texts["MODEL_SAVED_WITH_ITEMS"].format(model_name=data['name'], item_count=data['item_count']),
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        show_models_list(cid)

@bot.message_handler(func=lambda message: admin_model_step.get(message.chat.id, {}).get("step") in ("new_item_count", "new_item_name"))
def handle_new_model_item_steps(message):
    if not is_admin(message.chat.id):
        return
    cid = message.chat.id
    step = admin_model_step[cid]
    current_step = step["step"]
    data = step["data"]
    text = message.text.strip()

    if current_step == "new_item_count":
        if not text.isdigit() or int(text) < 1:
            bot.send_message(cid, texts["ERR_NUMBER_INVALID"])
            return
        data["item_count"] = int(text)
        data["current_item"] = 0
        step ["step"] = "new_item_name"
        admin_model_step[cid] = step
        bot.send_message(cid, texts["ASK_ITEM_NAME_FIRST"])

    elif current_step == "new_item_name":
        if not text:
            bot.send_message(cid, texts["ERR_NAME_EMPTY"])
            return
        data["items"].append({"name": text, "side_type": None})
        step["step"] = "new_item_side"
        admin_model_step[cid] = step

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton(texts["SIDE_TYPE_NONE"],   callback_data="nmdl_side_none"),
            InlineKeyboardButton(texts["SIDE_TYPE_BOTH"],   callback_data="nmdl_side_both"),
            InlineKeyboardButton(texts["SIDE_TYPE_SINGLE"], callback_data="nmdl_side_single"),
        )
        bot.send_message(
            cid,
            texts["ASK_ITEM_SIDE_TYPE"].format(item_name=text),
            parse_mode="Markdown",
            reply_markup=markup
        )


                                                                                

@bot.callback_query_handler(func=lambda call: call.data == "admin_items_back")
def handle_admin_items_back(call):
    bot.answer_callback_query(call.id)
    if not is_admin(call.message.chat.id):
        return
    admin_models_list(call.message.chat.id, call.message.message_id, edit=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_items_model_"))
def handle_admin_items_model(call):
    bot.answer_callback_query(call.id)
    if not is_admin(call.message.chat.id):
        return
    model_id = int(call.data.split("_")[-1])
    admin_items_list(call.message.chat.id, model_id, call.message.message_id, edit=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_item_add_"))
def handle_admin_item_add_start(call):
    bot.answer_callback_query(call.id)
    if not is_admin(call.message.chat.id): return
    
    model_id = int(call.data.split("_")[-1])
    admin_item_step[call.message.chat.id] = {
        'model_id': model_id,
        'step': 'wait_name',
        'data': {}
    }
    
    bot.edit_message_text(
        texts["ASK_NEW_ITEM_NAME"],
        call.message.chat.id, call.message.message_id,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_item_edit_"))
def handle_admin_item_edit(call):
    bot.answer_callback_query(call.id)
    if not is_admin(call.message.chat.id):
        return
    item_id = int(call.data.split("_")[-1])
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM model_items WHERE id=%s", (item_id,))
    item = cur.fetchone(); cur.close(); conn.close()

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(texts["EDIT_NAME_BTN"],  callback_data=f"admin_iedit_name_{item_id}"),
        InlineKeyboardButton(texts["EDIT_PRICE_BTN"], callback_data=f"admin_iedit_price_{item_id}"),
        InlineKeyboardButton(texts["EDIT_SIDE_BTN"],  callback_data=f"admin_iedit_side_{item_id}"),
    )
    markup.add(InlineKeyboardButton(texts["BACK_BTN"], callback_data=f"admin_items_model_{item['model_id']}"))

    price_str = f"{int(item['price']):,}" if item['price'] else "—"
    bot.edit_message_text(
        texts["ITEM_EDIT_HEADER"].format(item_name=item['name'], price=price_str, side=item['side_type']),
        call.message.chat.id, call.message.message_id,
        reply_markup=markup, parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_iedit_"))
def handle_admin_iedit_field(call):
    cid = call.message.chat.id
    if not is_admin(cid):
        return
    parts = call.data.split("_")                                       
    field = parts[2]
    item_id = int(parts[3])

    if field == "side":
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton(texts["SIDE_TYPE_NONE"],   callback_data=f"admin_ieside_none_{item_id}"),
            InlineKeyboardButton(texts["SIDE_TYPE_BOTH"],   callback_data=f"admin_ieside_both_{item_id}"),
            InlineKeyboardButton(texts["SIDE_TYPE_SINGLE"], callback_data=f"admin_ieside_single_{item_id}"),
        )
        bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id)
        return

    admin_item_step[cid] = {"step": f"edit_{field}", "item_id": item_id, "message_id": call.message.message_id}
    prompt = texts["ASK_NEW_NAME"] if field == "name" else texts["ASK_NEW_PRICE"]
    bot.register_next_step_handler(bot.send_message(cid, prompt), _item_edit_step)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_ieside_"))
def handle_admin_ieside(call):
    cid = call.message.chat.id
    parts = call.data.split("_")                                       
    side = parts[2]
    item_id = int(parts[3])

    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("UPDATE model_items SET side_type=%s WHERE id=%s", (side, item_id))
    conn.commit()
    cur.execute("SELECT model_id FROM model_items WHERE id=%s", (item_id,))
    row = cur.fetchone(); cur.close(); conn.close()

    bot.answer_callback_query(call.id, texts["SIDE_UPDATED_OK"])
    admin_items_list(cid, row["model_id"], call.message.message_id, edit=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_item_delete_"))
def handle_admin_item_delete(call):
    bot.answer_callback_query(call.id)
    if not is_admin(call.message.chat.id):
        return
    item_id = int(call.data.split("_")[-1])
    conn = get_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT name FROM model_items WHERE id=%s", (item_id,))
    item = cur.fetchone(); cur.close(); conn.close()

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(texts["CONFIRM_DELETE_BTN"], callback_data=f"admin_item_del_confirm_{item_id}"),
        InlineKeyboardButton(texts["CANCEL_BTN"],         callback_data="admin_items_back")
    )
    bot.edit_message_text(
        texts["CONFIRM_ITEM_DELETE"].format(item_name=item['name']),
        call.message.chat.id, call.message.message_id,
        reply_markup=markup, parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_item_del_confirm_"))
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
        bot.answer_callback_query(call.id, texts["ITEM_DELETED_OK"])
    except Exception as e:
        conn.rollback()
        bot.answer_callback_query(call.id, texts["ERR_DELETE"].format(e=e), show_alert=True)
    finally:
        cur.close(); conn.close()

    admin_items_list(cid, row["model_id"], call.message.message_id, edit=True)

@bot.message_handler(func=lambda message: message.text == texts["ADMIN_ITEMS_BTN"])
def admin_items_menu(message):
    if not is_admin(message.chat.id):
        return
    admin_models_list(message.chat.id)

@bot.message_handler(func=lambda message: message.chat.id in admin_item_step)
def process_admin_item_steps(message):
    cid = message.chat.id
    step_data = admin_item_step[cid]
    step = step_data['step']
    text = message.text

    if text == texts["CANCEL_BTN"]:
        del admin_item_step[cid]
        bot.send_message(cid, texts["OPERATION_CANCELLED"], reply_markup=main_menu())
        return

    if step == 'wait_name':
        step_data['data']['name'] = text
        step_data['step'] = 'wait_price'
        bot.send_message(cid, texts["ASK_ITEM_PRICE"].format(item_name=text), parse_mode="Markdown")

    elif step == 'wait_price':
        if not text.isdigit():
            bot.send_message(cid, texts["ERR_DIGITS_ONLY"])
            return
        
        step_data['data']['price'] = int(text)
        step_data['step'] = 'wait_side'
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(texts["SIDE_TYPE_NONE"],       callback_data="admin_item_side_none"))
        markup.add(InlineKeyboardButton(texts["SIDE_TYPE_BOTH"],       callback_data="admin_item_side_both"))
        markup.add(InlineKeyboardButton(texts["SIDE_TYPE_SINGLE_LONG"],callback_data="admin_item_side_single"))
        
        bot.send_message(cid, texts["ASK_ITEM_SIDE_TYPE_SHORT"], reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_item_side_"))
def handle_admin_item_side_final(call):
    cid = call.message.chat.id
    if cid not in admin_item_step: return

    side_type = call.data.replace("admin_item_side_", "")
    step = admin_item_step[cid]
    model_id = step['model_id']
    data = step['data']

    try:
        conn = get_connection()
        cur = conn.cursor()
        query = """
            INSERT INTO model_items (model_id, name, price, side_type)
            VALUES (%s, %s, %s, %s)
        """
        cur.execute(query, (model_id, data['name'], data['price'], side_type))
        conn.commit()
        bot.answer_callback_query(call.id, texts["ITEM_ADDED_OK"])
        
        del admin_item_step[cid]
        bot.delete_message(cid, call.message.message_id)
        admin_items_list(cid, model_id)
        
    except Exception as e:
        bot.send_message(cid, texts["ERR_DB"].format(e=e))
    finally:
        cur.close(); conn.close()

                         

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_user_delete_confirm_"))
def handle_admin_user_delete_confirm(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    user_id = int(call.data.split("_")[-1])
    cid = call.message.chat.id

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM orders WHERE user_id=%s", (user_id,))
        order_ids = [r[0] for r in cursor.fetchall()]

        for oid in order_ids:
            cursor.execute("DELETE FROM order_items WHERE order_id=%s", (oid,))
            cursor.execute("DELETE FROM order_files WHERE order_id=%s", (oid,))

        cursor.execute("SELECT id FROM debts WHERE user_id=%s", (user_id,))
        debt_ids = [r[0] for r in cursor.fetchall()]

        for did in debt_ids:
            cursor.execute("DELETE FROM payment_debts WHERE debt_id=%s", (did,))

        cursor.execute("DELETE FROM debts WHERE user_id=%s", (user_id,))

        cursor.execute("SELECT id FROM payments WHERE user_id=%s", (user_id,))
        payment_ids = [r[0] for r in cursor.fetchall()]

        for pid in payment_ids:
            cursor.execute("DELETE FROM payment_debts WHERE payment_id=%s", (pid,))

        cursor.execute("DELETE FROM payments WHERE user_id=%s", (user_id,))
        cursor.execute("DELETE FROM orders WHERE user_id=%s", (user_id,))
        cursor.execute("DELETE FROM admins WHERE user_id=%s", (user_id,))
        cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))

        conn.commit()
        bot.send_message(cid, texts["USER_DELETED_OK"])

    except Exception as e:
        conn.rollback()
        bot.send_message(cid, texts["ERR_DELETE"].format(e=e))
    finally:
        cursor.close()
        conn.close()

    admin_users_list(cid)

@bot.callback_query_handler(func=lambda call: call.data == "admin_users_list")
def handle_admin_users_list(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    admin_users_list(call.message.chat.id, call.message.message_id, edit=True)

@bot.callback_query_handler(func=lambda call: call.data == "admin_users_menu")
def handle_admin_users_menu(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    bot.edit_message_text(texts["ADMIN_USERS_HEADER"], call.message.chat.id,
                          call.message.message_id, reply_markup=admin_users_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_panel_back")
def handle_admin_panel_back(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, texts["ADMIN_PANEL_HEADER"], reply_markup=admin_menu())

@bot.callback_query_handler(func=lambda call: call.data == "admin_user_add")
def handle_admin_user_add(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    admin_add_user_step[call.message.chat.id] = {"step": "get_name", "data": {}}
    msg = bot.send_message(call.message.chat.id, texts["ASK_USER_NAME"])
    bot.register_next_step_handler(msg, _add_user_get_name)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_user_edit_"))
def handle_admin_user_edit(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    user_id = int(call.data.split("_")[-1])
    admin_edit_user_step[call.message.chat.id] = {"user_id": user_id}
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton(texts["EDIT_NAME_BTN"],  callback_data=f"admin_edit_field_name_{user_id}"),
        InlineKeyboardButton(texts["EDIT_PHONE_BTN"], callback_data=f"admin_edit_field_phone_{user_id}"),
    )
    markup.add(
        InlineKeyboardButton(texts["EDIT_ACCESS_BTN"], callback_data=f"admin_edit_field_su_{user_id}"),
        InlineKeyboardButton(texts["BACK_BTN"],        callback_data="admin_users_list"),
    )
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_edit_field_"))
def handle_admin_edit_field(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    parts = call.data.split("_")                                         
    field = parts[3]
    user_id = int(parts[4])
    cid = call.message.chat.id

    if field == "su":
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT is_superuser FROM users WHERE id=%s", (user_id,))
        row = cursor.fetchone()
        new_val = 0 if row[0] else 1
        cursor.execute("UPDATE users SET is_superuser=%s WHERE id=%s", (new_val, user_id))
        conn.commit()
        cursor.close()
        conn.close()
        status = texts["SUPERUSER_STATUS"] if new_val else texts["NORMAL_USER_STATUS"]
        bot.send_message(cid, texts["ACCESS_CHANGED"].format(status=status))
        admin_users_list(cid)
        return

    admin_edit_user_step[cid] = {"user_id": user_id, "field": field}
    label = texts["LABEL_NAME"] if field == "name" else texts["LABEL_PHONE"]
    msg = bot.send_message(cid, texts["ASK_NEW_FIELD"].format(label=label))
    bot.register_next_step_handler(msg, _edit_user_finalize)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_user_delete_"))
def handle_admin_user_delete(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    user_id = int(call.data.split("_")[-1])

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton(texts["CONFIRM_DELETE_BTN"], callback_data=f"admin_user_delete_confirm_{user_id}"),
        InlineKeyboardButton(texts["CANCEL_BTN"],         callback_data="admin_users_list"),
    )
    bot.edit_message_text(
        texts["CONFIRM_USER_DELETE"],
        call.message.chat.id, call.message.message_id,
        reply_markup=markup
    )

                                                                                                          

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

@bot.callback_query_handler(func=lambda call: call.data == "finence")
def handle_finence(call):
    if not is_registered(call.message.chat.id):
        return
    if is_superuser(call.message.chat.id):
        bot.answer_callback_query(call.id)
        finance_activities(call)

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
def handle_back_more(call):
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

@bot.callback_query_handler(func=lambda call: call.data.startswith("order_detail_"))
def handle_order_detail(call):
    if not is_registered(call.message.chat.id): return
    order_detail_activities(call)

@bot.callback_query_handler(func=lambda call: call.data == "finance")
def handle_finance(call):
    if not is_registered(call.message.chat.id) or not is_superuser(call.message.chat.id): return
    finance_activities(call)

@bot.callback_query_handler(func=lambda call: call.data == "finance_debts")
def handle_finance_debts(call):
    if not is_registered(call.message.chat.id) or not is_superuser(call.message.chat.id): return
    finance_debts_activities(call)

@bot.callback_query_handler(func=lambda call: call.data == "finance_history")
def handle_finance_history(call):
    if not is_registered(call.message.chat.id) or not is_superuser(call.message.chat.id): return
    finance_history_activities(call)

@bot.callback_query_handler(func=lambda call: call.data == "finance_pay")
def handle_finance_pay(call):
    bot.answer_callback_query(call.id, texts["COMING_SOON"], show_alert=True)

                                                               

@bot.callback_query_handler(func=lambda call: call.data == "mdl_list")
def handle_mdl_list(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    show_models_list(call.message.chat.id, call.message.message_id, edit=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mdl_items_"))
def handle_mdl_items(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    model_id = int(call.data.split("_")[-1])
    admin_items_list(call.message.chat.id, model_id,
                     call.message.message_id, edit=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mdl_edit_"))
def handle_mdl_edit(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    model_id = int(call.data.split("_")[-1])
    cid = call.message.chat.id
    admin_model_step[cid] = {
        "step": "edit_name",
        "model_id": model_id,
        "message_id": call.message.message_id,
    }
    bot.send_message(cid, texts["ASK_NEW_MODEL_NAME"])


@bot.message_handler(func=lambda message: admin_model_step.get(message.chat.id, {}).get("step") == "edit_name")
def handle_mdl_edit_name_input(message):
    if not is_admin(message.chat.id):
        return
    cid = message.chat.id
    step = admin_model_step.pop(cid)
    new_name = message.text.strip()

    if not new_name:
        bot.send_message(cid, texts["ERR_NAME_EMPTY"])
        return

    db_update_model_name(step["model_id"], new_name)
    bot.send_message(cid, texts["MODEL_NAME_CHANGED"].format(new_name=new_name), parse_mode="Markdown")
    show_models_list(cid)


@bot.callback_query_handler(func=lambda call: call.data.startswith("mdl_delete_"))
def handle_mdl_delete(call):
    bot.answer_callback_query(call.id)
    if not is_admin(call.message.chat.id):
        return
    model_id = int(call.data.split("_")[-1])
    cid = call.message.chat.id
    item_count = db_count_model_items(model_id)

    markup = InlineKeyboardMarkup()

    if item_count > 0:
        text = texts["CONFIRM_MODEL_DELETE_WITH_ITEMS"].format(item_count=item_count)
        markup.add(InlineKeyboardButton(
            texts["CONFIRM_MODEL_DELETE_BTN"].format(item_count=item_count),
            callback_data=f"mdl_del_confirm_{model_id}"
        ))
    else:
        text = texts["CONFIRM_MODEL_DELETE_EMPTY"]
        markup.add(InlineKeyboardButton(
            texts["CONFIRM_DELETE_BTN"],
            callback_data=f"mdl_del_confirm_{model_id}"
        ))

    markup.add(InlineKeyboardButton(texts["CANCEL_BTN"], callback_data="mdl_list"))
    bot.edit_message_text(text, cid, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("mdl_del_confirm_"))
def handle_mdl_del_confirm(call):
    if not is_admin(call.message.chat.id):
        return
    model_id = int(call.data.split("_")[-1])
    cid = call.message.chat.id

    success = db_delete_model(model_id)
    if success:
        bot.answer_callback_query(call.id, texts["MODEL_DELETED_OK"])
    else:
        bot.answer_callback_query(call.id, texts["ERR_MODEL_DELETE"], show_alert=True)

    show_models_list(cid, call.message.message_id, edit=True)


@bot.callback_query_handler(func=lambda call: call.data == "mdl_add")
def handle_mdl_add(call):
    bot.answer_callback_query(call.id)
    if not is_admin(call.message.chat.id):
        return
    cid = call.message.chat.id
    admin_model_step[cid] = {"step": "add_name", "data": {}}
    bot.send_message(cid, texts["ASK_NEW_MODEL_NAME_INPUT"])


@bot.message_handler(func=lambda message: admin_model_step.get(message.chat.id, {}).get("step") == "add_name")
def handle_mdl_add_name_input(message):
    if not is_admin(message.chat.id):
        return
    cid = message.chat.id
    name = message.text.strip()

    if not name:
        bot.send_message(cid, texts["ERR_NAME_EMPTY"])
        return

    admin_model_step[cid]["data"]["name"] = name
    admin_model_step[cid]["step"] = "add_ask_items"

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(texts["YES_NOW_BTN"], callback_data="mdl_add_items_yes"),
        InlineKeyboardButton(texts["NO_LATER_BTN"], callback_data="mdl_add_items_no"),
    )
    bot.send_message(cid,texts["ASK_ADD_ITEMS_NOW"].format(model_name=name),parse_mode="Markdown",reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "mdl_add_items_no")
def handle_mdl_add_items_no(call):
    if not is_admin(call.message.chat.id):
        return
    cid = call.message.chat.id
    step = admin_model_step.pop(cid, None)
    if not step:
        bot.answer_callback_query(call.id)
        return

    model_id = db_add_model(step["data"]["name"])
    bot.answer_callback_query(call.id)
    bot.delete_message(cid, call.message.message_id)
    bot.send_message(
        cid,
        texts["MODEL_SAVED_NO_ITEMS"].format(model_name=step['data']['name']),
        parse_mode="Markdown"
    )
    show_models_list(cid)


@bot.callback_query_handler(func=lambda call: call.data == "mdl_add_items_yes")
def handle_mdl_add_items_yes(call):
    if not is_admin(call.message.chat.id):
        return
    cid = call.message.chat.id
    step = admin_model_step.get(cid)
    if not step:
        bot.answer_callback_query(call.id)
        return

    step["step"] = "new_item_count"
    step["data"]["items"] = []
    step["data"]["current_item"] = 0
    admin_model_step[cid] = step

    bot.answer_callback_query(call.id)
    bot.delete_message(cid, call.message.message_id)
    bot.send_message(
        cid,
        texts["ASK_MODEL_ITEM_COUNT"].format(model_name=step['data']['name']),
        parse_mode="Markdown"
    )


                                                                 

@bot.message_handler(func=lambda message: message.text == texts["ADMIN_ORDERS_BTN"] and is_admin(message.chat.id))
def handle_admin_orders(message):
    admin_orders_list(message.chat.id, None, status="pending", edit=False)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_orders_"))
def handle_admin_orders_filter(call):
    if not is_admin(call.message.chat.id):
        return
    bot.answer_callback_query(call.id)
    status = call.data.replace("admin_orders_", "")
    admin_orders_list(call.message.chat.id, call.message.message_id, status=status, edit=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_order_detail_"))
def handle_admin_order_detail(call):
    if not is_admin(call.message.chat.id):
        return
    order_id = int(call.data.replace("admin_order_detail_", ""))
    chat_id = call.message.chat.id

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT orders.id, orders.status, orders.notes, orders.created_at,
               orders.fabric_name, orders.customer_name, orders.delivery_date, orders.invoice_number,
               users.name, users.phone, users.chat_id AS user_chat_id
        FROM orders JOIN users ON orders.user_id = users.id
        WHERE orders.id = %s
    """, (order_id,))
    order = cursor.fetchone()

    cursor.execute("""
        SELECT model_items.name, order_items.quantity, order_items.unit_price, order_items.hand_side
        FROM order_items JOIN model_items ON order_items.model_item_id = model_items.id
        WHERE order_items.order_id = %s
    """, (order_id,))
    items = cursor.fetchall()

    cursor.execute("SELECT file_id FROM order_files WHERE order_id = %s", (order_id,))
    files = cursor.fetchall()
    cursor.close()
    conn.close()

    if not order:
        bot.answer_callback_query(call.id, texts["ORDER_NOT_FOUND"], show_alert=True)
        return
    bot.answer_callback_query(call.id)

    status_fa = {
        'pending':     texts["STATUS_PENDING"],
        'confirmed':   texts["STATUS_CONFIRMED"],
        'in_progress': texts["STATUS_IN_PROGRESS"],
        'delivered':   texts["STATUS_DELIVERED"],
        'cancelled':   texts["STATUS_CANCELLED"],
    }
    hand_fa = {
        'left':  texts["HAND_LEFT_PLAIN"],
        'right': texts["HAND_RIGHT_PLAIN"],
        'none':  "—",
    }

    lines = [
        texts["ADMIN_ORDER_DETAIL_HEADER"].format(order_id=order_id),
        texts["ORDER_DETAIL_STATUS"].format(status=status_fa.get(order['status'], order['status'])),
        texts["ADMIN_ORDER_DETAIL_DATE"].format(val=str(order['created_at'])[:16]),
        texts["ADMIN_ORDER_DETAIL_FABRIC"].format(val=order['fabric_name']),
        texts["ADMIN_ORDER_DETAIL_CUSTOMER"].format(val=order['customer_name']),
        texts["ADMIN_ORDER_DETAIL_DELIVERY"].format(val=order['delivery_date']),
        texts["ADMIN_ORDER_DETAIL_USER"].format(name=order['name'], phone=order['phone']),
        f"chat_id: `{order['user_chat_id']}`",
    ]

    if order['invoice_number']:
        lines.append(texts["ORDER_DETAIL_INVOICE"].format(val=order['invoice_number']))

    if order['notes']:
        lines.append(texts["ORDER_DETAIL_NOTES"].format(val=order['notes']))

    if items:
        lines.append(texts["ORDER_DETAIL_ITEMS_HEADER"])
        total = 0
        for it in items:
            subtotal = it['quantity'] * int(it['unit_price'])
            total += subtotal
            side = texts["ORDER_DETAIL_SIDE"].format(hand=hand_fa[it['hand_side']]) if it['hand_side'] != 'none' else ""
            lines.append(
                f"• {it['name']} × {it['quantity']}"
                f" | {int(it['unit_price']):,} تومان{side}"
                f"\n  جمع: {subtotal:,} تومان"
            )
        lines.append(texts["ORDER_DETAIL_TOTAL"].format(total=total))

    if files:
        lines.append(texts["ORDER_FILES_COUNT"].format(count=len(files)))

    next_statuses = {
        'pending':     [(texts["STATUS_ACTION_CONFIRM"], 'confirmed'), (texts["STATUS_ACTION_CANCEL"], 'cancelled')],
        'confirmed':   [(texts["STATUS_ACTION_START"],   'in_progress'), (texts["STATUS_ACTION_CANCEL"], 'cancelled')],
        'in_progress': [(texts["STATUS_ACTION_DELIVER"], 'delivered')],
        'delivered':   [],
        'cancelled':   [],
    }
    markup = InlineKeyboardMarkup(row_width=2)
    for label, new_status in next_statuses.get(order['status'], []):
        markup.add(InlineKeyboardButton(
            label, callback_data=f"admin_set_status_{order_id}_{new_status}"
        ))
    markup.add(InlineKeyboardButton(
        texts["BACK_BTN"], callback_data=f"admin_orders_{order['status']}"
    ))

    bot.edit_message_text("\n".join(lines), chat_id, call.message.message_id,
                          parse_mode="Markdown", reply_markup=markup)

    for f in files:
        try:
            bot.send_document(chat_id, f['file_id'])
        except Exception:
            pass


@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_set_status_"))
def handle_admin_set_status(call):
    if not is_admin(call.message.chat.id):
        return

    parts = call.data.split("_", 4)                                                    
    order_id = int(parts[3])
    new_status = parts[4]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status=%s WHERE id=%s", (new_status, order_id))
    conn.commit()

    cursor.execute("""
        SELECT users.chat_id, users.name FROM orders JOIN users ON orders.user_id = users.id
        WHERE orders.id = %s
    """, (order_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    status_fa = {
        'confirmed':   texts["STATUS_CONFIRMED"],
        'in_progress': texts["STATUS_IN_PROGRESS"],
        'delivered':   texts["STATUS_DELIVERED"],
        'cancelled':   texts["STATUS_CANCELLED"],
    }

    if row:
        user_chat_id, uname = row
        bot.send_message(
            user_chat_id,
            texts["ORDER_STATUS_CHANGED"].format(order_id=order_id, status=status_fa.get(new_status, new_status)),
            parse_mode="Markdown")
    status_fa.get(new_status, new_status)

    bot.answer_callback_query(call.id, texts["STATUS_CHANGED_OK"].format(status=status_fa.get(new_status)), show_alert=True)

    admin_orders_list(call.message.chat.id, call.message.message_id, status=new_status, edit=True)


@bot.message_handler(func=lambda message: message.text == texts["ADMIN_STATS_BTN"] and is_admin(message.chat.id))
def handle_admin_stats(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(texts["STATS_BACK_BTN"], callback_data="admin_panel_back"))
    bot.send_message(
        message.chat.id,
        texts["STATS_COMING_SOON"],
        parse_mode="Markdown",
        reply_markup=markup
    )

                                                                                                       

def info_listener(messages):
    for message in messages:
        user_id = message.chat.id
        username = message.chat.username or "No Username"
        text = message.text or f"[{message.content_type}]"
        
        print(f"\n--- [New Message] ---")
        print(f"👤 User: {username} ({user_id})")
        print(f"💬 Content: {text}")
        print(f"----------------------\n")
bot.set_update_listener(info_listener)

print("robot is running")
bot.infinity_polling()