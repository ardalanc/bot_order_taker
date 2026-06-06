import telebot
import mysql.connector
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from config import BOT_TOKEN, DB_NAME, database_config
from Texts import texts 

telebot.apihelper.API_URL="http://tapi.bale.ai/bot{0}/{1}"

bot = telebot.TeleBot(BOT_TOKEN)


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
    markup.add(InlineKeyboardButton(texts["ORDER_HISTORY"], callback_data="order_history"))
    markup.add(InlineKeyboardButton(texts["CURRENT_ORDERS"], callback_data="current_orders"))
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


@bot.callback_query_handler(func=lambda call: call.data == "order_history")
def handle_order_history(call):


    bot.send_message(call.message.chat.id, "")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "current_orders")
def handle_current_orders(call):


    
    bot.send_message(call.message.chat.id, "")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "finence")
def handle_finence(call):
    bot.send_message(call.message.chat.id, "")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "help")
def handle_help(call):
    bot.send_message(call.message.chat.id, "")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "aboat_us")
def handle_aboat_us(call):
    bot.send_message(call.message.chat.id, "")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "suport")
def handle_suport(call):
    bot.send_message(call.message.chat.id, "")
    bot.answer_callback_query(call.id)



print ("robot is running")
bot.infinity_polling()