import random
import telebot
import sqlalchemy
import logging

from sqlalchemy.orm import sessionmaker
from sqlalchemy import and_
from telebot import types, custom_filters, StateMemoryStorage
from telebot.states import StatesGroup, State
from config import *
from db import *

# Инициализация базы данных и бота
DSN = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = sqlalchemy.create_engine(DSN)
Session = sessionmaker(bind=engine)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("__BOT__")

logger.info('Start telegram bot...')

state_storage = StateMemoryStorage()
bot = telebot.TeleBot(TG_TOKEN, state_storage=state_storage)

known_users = set()
userStep = {}
buttons = []
word_list = []


def show_hint(*lines):
    """
    Функция для отображения подсказки пользовтелю
    :param lines: Произвольное количество строк, которые будут объединены в одну подсказку.
    :return: Объединненая строка подсказки
    """
    return '\n'.join(lines)


def show_target(data):
    """
    Функция для отображения целевого слова и его перевода.
    :param data: Словарь содержащий целевое слово и его перевод
    :return: Строка с целевым словом и переводом
    """
    return f"{data['target_word']} -> {data['translate_word']}"


class Command:
    """
    Класс, содержащий команды для взаимодействия с пользователем
    """
    ADD_WORD = 'Добавить слово ➕'
    DELETE_WORD = 'Удалить слово🔙'
    NEXT = 'Дальше ⏭'


class MyStates(StatesGroup):
    """
    Класс для упарвления состоянием бота
    """
    target_word = State()
    translate_word = State()
    another_words = State()


def get_user_step(uid):
    """
    Функция для получения текущего шага пользователя.
    :param uid: Уникальный идентификатор пользователя.
    :return: Текущий шаг пользователя
    """
    if uid not in known_users:
        known_users.add(uid)
        userStep[uid] = 0
        logger.info(f"New user detected: {uid}")
    return userStep.get(uid, 0)


def create_markup(buttons):
    """
    Функция для создания клавиатуры с кнопками.
    :param buttons: Список кнопок клавиатуры
    :return:Клавиатура
    """
    markup = types.ReplyKeyboardMarkup(row_width=2)
    markup.add(*buttons)
    return markup


def initialize_user(session, username):
    """
    Функция для добавления нового пользователя в базу данных
    :param session: Сессия базы данных.
    :param username: Имя пользователя.
    """
    if check_user_exist(session, username):
        add_user(session, username)


@bot.message_handler(commands=['cards', 'start'])
def create_cards(message):
    """
    Обработчик команд: /cards или /start
    """
    create_table(engine)
    with Session() as session:
        db_init(session)
        initialize_user(session, message.from_user.username)

    cid = message.chat.id
    if cid not in known_users:
        known_users.add(cid)
        userStep[cid] = 0
        bot.send_message(cid, f"Hello, {message.from_user.username}, let study English...")

    update_buttons(message)

def update_buttons(message):
    """
    Функция для обновления кнопок с новыми словами.
    """
    global buttons
    with Session() as session:
        target_word, translate = get_random_word_pair(session, message.from_user.username, word_list)
        word_list.append(target_word)
        others = get_random_words(session, target_word, message.from_user.username, word_list)

    buttons = [types.KeyboardButton(target_word.capitalize())]
    buttons.extend([types.KeyboardButton(word.capitalize()) for word in others])
    random.shuffle(buttons)
    buttons.extend([types.KeyboardButton(Command.NEXT),
                    types.KeyboardButton(Command.ADD_WORD),
                    types.KeyboardButton(Command.DELETE_WORD)])

    greeting = f"Выбери перевод слова:\n🇷🇺 {translate.capitalize()}"
    bot.send_message(message.chat.id, greeting, reply_markup=create_markup(buttons))
    bot.set_state(message.from_user.id, MyStates.target_word, message.chat.id)
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        data['target_word'] = target_word.capitalize()
        data['translate_word'] = translate.capitalize()
        data['other_words'] = others.capitalize()


@bot.message_handler(func=lambda message: message.text == Command.NEXT)
def next_cards(message):
    """
    Обработчик команды "Дальше ⏭"
    """
    word_list.pop(0) if len(word_list) > 4 else None
    update_buttons(message)


@bot.message_handler(func=lambda message: message.text == Command.DELETE_WORD)
def handle_delete_word(message):
    """
    Обработчик команды "Удалить слово🔙". Запрашивает у пользователя слово которое планируем удалить.
    """
    bot.send_message(message.chat.id, f'{message.from_user.username}, введите слово которое хотите удалить')
    bot.register_next_step_handler(message, process_delete_word)

def process_delete_word(message):
    """
    Функция для обработки удаления слова
    :param message: Сообщение пользователя, содержащее слово для удаления
    """
    try:
        incoming_word = message.text.strip().lower().split()
        if len(incoming_word) != 1:
            raise ValueError
        word = incoming_word[0]
        logger.info(word)
        with Session() as session:
            if session.query(Words).join(UserWord).join(Users).filter(and_(Words.target_word==word,Users.name==message.chat.username)).first():
                delete_word(session, word, message.chat.username)
                bot.send_message(message.chat.id, f'Слово <{word.capitalize()}> удалено!')
            else:
                bot.send_message(message.chat.id, f'{message.from_user.username}, нет такого слова в вашем словаре!!!')
        update_buttons(message)
    except ValueError:
        bot.send_message(message.chat.id,f'Произошла ошибка!\n, Повторите ввод, указав слово которое хотите удалить.')
        bot.register_next_step_handler(message, process_delete_word)


@bot.message_handler(func=lambda message: message.text == Command.ADD_WORD)
def handle_add_word(message):
    """
    Обработчик команды "Добавить слово ➕". Запрашивает у пользователя слово и его перевод.G
    """
    bot.send_message(message.chat.id, f'{message.from_user.username}, введите слово и его перевод')
    bot.register_next_step_handler(message, process_add_word)

def process_add_word(message):
    """
    Функция для обработки добавления пары слово-перевод
    """
    try:
        income_words = message.text.strip().lower().split(' ', 1)
        if len(income_words) != 2:
            raise ValueError
        word, translate= income_words
        with Session() as session:
            count, status = add_word(session, word, translate, message.from_user.username)
            if status:
                bot.send_message(message.chat.id, f'Слово <{word.capitalize()}> и его перевод <{translate.capitalize()}> добавлены!')
                bot.send_message(message.chat.id, f'Количество изучаемых пользователем слов: {count}')
            else:
                bot.send_message(message.chat.id, f'Слово <{word.capitalize()}> уже есть!')
        update_buttons(message)
    except ValueError:
        bot.send_message(message.chat.id, f'Произошла ошибка!\n Повторите ввод, указав слово и его перевод снова через пробел.')
        bot.register_next_step_handler(message, process_add_word)


@bot.message_handler(commands=['help'])
def help_command(message):
    """
    Обработчик команды /help. Выводит справку по работе бота
    """
    help_text = """
        🤖 **Описание программы:**
        Этот бот помогает вам учить английские слова. Вы можете добавлять новые слова, удалять их и тренироваться в запоминании.

        🛠 **Доступные команды:**
        /start или /cards - Начать изучение слов.
        /help - Показать это сообщение с инструкцией.

        🎮 **Как пользоваться:**
        1. Бот покажет вам слово на русском языке и несколько вариантов перевода на английский.
        2. Выберите правильный перевод слова.
        3. Если вы ошиблись, бот подскажет что перевод выбран неверно. Попробуйте еще раз.
        4. Используйте кнопку "Дальше ⏭", чтобы перейти к следующему слову.

        ➕ **Добавление слов:**
        - Нажмите кнопку "Добавить слово ➕".
        - Введите слово и его перевод через пробел (например, "cat кот").

        🔙 **Удаление слов:**
        - Нажмите кнопку "Удалить слово🔙".
        - Введите слово, которое хотите удалить.

        """
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")
    update_buttons(message)


@bot.message_handler(func=lambda message: True, content_types=['text'])
def message_reply(message):
    """
    Обработчик текстовых сообщений от пользователя. Проверяет правильность перевода слова.
    """
    text = message.text
    valid = False
    with bot.retrieve_data(message.from_user.id, message.chat.id) as data:
        target_word = data['target_word']
        if text == target_word:
            hint = show_target(data)
            hint_text = ["Отлично!❤", hint]
            hint = show_hint(*hint_text)
            valid = True
        else:
            for btn in buttons:
                if btn.text == text:
                    btn.text = text + '❌'
                    break
            hint = show_hint("Допущена ошибка!", f"Попробуй ещё раз вспомнить слово 🇷🇺{data['translate_word'].capitalize()}")
    bot.send_message(message.chat.id, hint, reply_markup=create_markup(buttons))
    if valid:
        next_cards(message)



bot.add_custom_filter(custom_filters.StateFilter(bot))
bot.infinity_polling(skip_pending=True)