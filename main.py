import random
import telebot
import sqlalchemy

from sqlalchemy.orm import sessionmaker
from telebot import types, custom_filters, StateMemoryStorage
from telebot.states import StatesGroup, State
from config import *
from db import *

# Инициализация базы данных и бота
DSN = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = sqlalchemy.create_engine(DSN)
Session = sessionmaker(bind=engine)

print('Start telegram bot...')

state_storage = StateMemoryStorage()
bot = telebot.TeleBot(TG_TOKEN, state_storage=state_storage)

known_users = []
userStep = {}
buttons = []


def show_hint(*lines):
    return '\n'.join(lines)


def show_target(data):
    return f"{data['target_word']} -> {data['translate_word']}"


class Command:
    ADD_WORD = 'Добавить слово ➕'
    DELETE_WORD = 'Удалить слово🔙'
    NEXT = 'Дальше ⏭'


class MyStates(StatesGroup):
    target_word = State()
    translate_word = State()
    another_words = State()


def get_user_step(uid):
    if uid not in known_users:
        known_users.add(uid)
        userStep[uid] = 0
        print(f"New user detected: {uid}")
    return userStep.get(uid, 0)


def create_markup(buttons):
    markup = types.ReplyKeyboardMarkup(row_width=2)
    markup.add(*buttons)
    return markup

def initialize_user_session(session, username):
    if not check_user_exist(session, username):
        add_user(session, username)

@bot.message_handler(commands=['cards', 'start'])
def create_cards(message):
    create_table(engine)
    with Session() as session:
        db_init(session)
        initialize_user_session(session, message.from_user.username)

    cid = message.chat.id
    if cid not in known_users:
        known_users.append(cid)
        userStep[cid] = 0
        bot.send_message(cid, f"Hello, {message.from_user.username}, let study English...")

    update_buttons(message)

def update_buttons(message):
    global buttons
    with Session() as session:
        target_word, translate = get_random_word_pair(session, message.from_user.username)
        others = get_random_words(session, target_word, message.from_user.username)

    buttons = [types.KeyboardButton(target_word)]
    buttons.extend([types.KeyboardButton(word) for word in others])
    random.shuffle(buttons)
    buttons.extend([types.KeyboardButton(Command.NEXT),
                    types.KeyboardButton(Command.ADD_WORD),
                    types.KeyboardButton(Command.DELETE_WORD)])

    greeting = f"Выбери перевод слова:\n🇷🇺 {translate}"
    bot.send_message(message.chat.id, greeting, reply_markup=create_markup(buttons))
    bot.set_state(message.from_user.id, MyStates.target_word, message.chat.id)
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['target_word'] = target_word
        data['translate_word'] = translate
        data['other_words'] = others


@bot.message_handler(func=lambda message: message.text == Command.NEXT)
def next_cards(message):
    update_buttons(message)


@bot.message_handler(func=lambda message: message.text == Command.DELETE_WORD)
def handle_delete_word(message):
    bot.send_message(message.chat.id, f'{message.from_user.username}, введите слово которое хотите удалить')
    bot.register_next_step_handler(message, process_delete_word)


def process_delete_word(message):
    word = message.text.lower()
    with Session() as session:
        if session.query(Words).filter_by(target_word=word).first():
            delete_word(session, word, message.chat.username)
            bot.send_message(message.chat.id, f'Слово <{word.capitalize()}> удалено!')
        else:
            bot.send_message(message.chat.id, f'{message.from_user.username}, нет такого слова!!!')
    update_buttons(message)

@bot.message_handler(func=lambda message: message.text == Command.ADD_WORD)
def handle_add_word(message):
    bot.send_message(message.chat.id, f'{message.from_user.username}, введите слово и его перевод')
    bot.register_next_step_handler(message, process_add_word)

def process_add_word(message):
    try:
        word, translate = message.text.lower().split()
        with Session() as session:
            count, status = add_word(session, word, translate, message.from_user.username)
            if status:
                bot.send_message(message.chat.id, f'Слово <{word.capitalize()}> и его перевод <{translate.capitalize()}> добавлены!')
            else:
                bot.send_message(message.chat.id, f'Слово <{word.capitalize()}> уже есть!')
        bot.send_message(message.chat.id, f'Количество изучаемых пользователем слов: {count}')
    except ValueError:
        bot.send_message(message.chat.id, 'Пожалуйста, введите слово и его перевод через пробел.')
    update_buttons(message)


@bot.message_handler(func=lambda message: True, content_types=['text'])
def message_reply(message):
    text = message.text
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        target_word = data['target_word']
        if text == target_word:
            hint = show_target(data)
            hint_text = ["Отлично!❤", hint]
            hint = show_hint(*hint_text)
        else:
            for btn in buttons:
                if btn.text == text:
                    btn.text = text + '❌'
                    break
            hint = show_hint("Допущена ошибка!", f"Попробуй ещё раз вспомнить слово 🇷🇺{data['translate_word']}")
    bot.send_message(message.chat.id, hint, reply_markup=create_markup(buttons))


bot.add_custom_filter(custom_filters.StateFilter(bot))
bot.infinity_polling(skip_pending=True)