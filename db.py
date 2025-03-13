import sqlalchemy as sq
from sqlalchemy import func
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import or_


Base = declarative_base()


class UserWord(Base):
    """
    Класс для связи пользователей и слов в базе данных.
    """
    __tablename__ = 'user_words'

    user_id = sq.Column(sq.Integer, sq.ForeignKey('users.id'), primary_key=True)
    word_id = sq.Column(sq.Integer, sq.ForeignKey('words.id'), primary_key=True)


class Users(Base):
    """
    Класс описывающий таблицу пользователей в базе даных
    """
    __tablename__ = 'users'
    id = sq.Column(sq.Integer, autoincrement=True, primary_key=True)
    name = sq.Column(sq.String(50), nullable=False, unique=True)
    Words = relationship('UserWord', backref='users')


class Words(Base):
    """
    Класс описываюший таблицу слов в базе данных
    """
    __tablename__ = 'words'
    id = sq.Column(sq.Integer, primary_key=True, autoincrement=True)
    target_word = sq.Column(sq.String(50), nullable=False, unique=True)
    translate = sq.Column(sq.String(50), nullable=False)
    Users = relationship('UserWord', backref='words')


def create_table(engine):
    """
    Создаем все таблицы в базе данных, если они еще не существуют.
    """
    Base.metadata.create_all(engine)


def check_user_exist(session, username):
    """
    Проверяем, существует ли пользователь с указанным именем.
    :param session: Сессия SQLAlchemy.
    :param username: Имя пользователя.
    :return: True, если пользователь не существует, иначе False.
    """
    return session.query(Users).filter_by(name=username).first() is None


def check_word_exist(session, word):
    """
    Проверяем, существует ли слово в базе данных.
    :param session: Сессия SQLAlchemy.
    :param word: Слово для проверки.
    :return: Объект слова, если оно существует, иначе None.
    """
    return session.query(Words).filter_by(target_word=word).first()


def add_user(session, username):
    """
    Добавляем нового пользователя в базу данных.
    :param session: Сессия SQLAlchemy.
    :param username: Имя пользователя.
    :return: True, если пользователь успешно добавлен, иначе False.
    """
    new_user = Users(name=username)
    session.add(new_user)
    try:
        session.commit()
        return True
    except IntegrityError:
        session.rollback()
        return None

def count_user_word(session, current_user):
    """
    Считает количество слов изучаемых текущим пользователем
    :param session: Сессия SQLAlchemy.
    :param current_user: Текущий пользователь
    :return: Количество слов, изучаемых пользователем
    """
    user = session.query(Users).filter_by(name=current_user).first()
    return (
        session.query(Words)
        .join(UserWord)
        .filter(or_(UserWord.user_id == 1, UserWord.user_id == user.id))
        .count()
    )

def add_word(session, word, translate, current_user):
    """
    Добавляем новое слово и связываем его с пользователем.
    :param session: Сессия SQLAlchemy.
    :param word: Слово для добавления.
    :param translate: Перевод слова.
    :param current_user: Имя пользователя, к которому привязывается слово.
    :return: True, если слово успешно добавлено, иначе False; Количество изучаемых текущим пользователем слов
    """
    current_word = check_word_exist(session, word)
    if not current_word:
        current_word = Words(target_word=word, translate=translate)
        session.add(current_word)
        session.flush()

    user = session.query(Users).filter_by(name=current_user).first()

    if session.query(UserWord).filter_by(user_id=user.id, word_id=current_word.id).first():
        return count_user_word(session, current_user), False

    user_word = UserWord(user_id=user.id, word_id=current_word.id)
    session.add(user_word)

    try:
        session.commit()
        return count_user_word(session, current_user), True
    except IntegrityError:
        session.rollback()
        return None


def delete_word(session, word, current_user):
    """
    Удаляем слово для указанного пользователя.
    :param session: Сессия SQLAlchemy.
    :param word: Слово для удаления.
    :param current_user: Имя пользователя.
    """
    user = session.query(Users).filter_by(name=current_user).first()
    word_to_delete = session.query(Words).filter_by(target_word=word).first()

    if user and word_to_delete:
        user_word_relation = session.query(UserWord).filter_by(user_id=user.id, word_id=word_to_delete.id).first()
        if user_word_relation:
            session.delete(user_word_relation)

        if not session.query(UserWord).filter_by(word_id=word_to_delete.id).first():
            session.delete(word_to_delete)

        session.commit()


def get_random_word_pair(session, current_user):
    """
    Возвращает случайное слово и его перевод из базы данных.
    :param session: Сессия SQLAlchemy.
    :param current_user: Текущий пользовватель
    :return: Кортеж из слова и его перевода. Если слов нет, возвращает (None, None).
    """
    user = session.query(Users).filter_by(name=current_user).first()
    random_word = (
        session.query(Words)
        .join(UserWord)
        .filter(or_(UserWord.user_id == 1, UserWord.user_id == user.id))
        .order_by(func.random())
        .first()
    )
    return (random_word.target_word, random_word.translate) if random_word else (None, None)


def get_random_words(session, target_word, current_user):
    """
    Возвращает список из 4 случайных слов, исключая указанное слово.
    :param session: Сессия SQLAlchemy.
    :param target_word: Текущее целевое слово, которое нужно исключить из выборки.
    :param current_user: Текущий пользовватель
    :return: Список случайных слов входящих привязанных к текущему пользователю и базовых слов
    """
    user = session.query(Users).filter_by(name=current_user).first()
    random_words = (
        session.query(Words.target_word)
        .join(UserWord)
        .filter(Words.target_word != target_word)
        .filter(or_(UserWord.user_id == 1, UserWord.user_id == user.id))
        .order_by(func.random())
        .limit(4)
        .all()
    )
    return [word.target_word for word in random_words]


def db_init(session):
    """
    Инициализирует базу данных начальными данными.
    Создает пользователя 'Initial User' и добавляет список слов с переводами.

    :param session: Сессия SQLAlchemy.
    """
    initial_data = [
        {'target_word': 'red', 'translate': 'красный'},
        {'target_word': 'blue', 'translate': 'синий'},
        {'target_word': 'green', 'translate': 'зеленый'},
        {'target_word': 'I', 'translate': 'я'},
        {'target_word': 'you', 'translate': 'ты'},
        {'target_word': 'they', 'translate': 'они'},
        {'target_word': 'run', 'translate': 'бежать'},
        {'target_word': 'jump', 'translate': 'прыгать'},
        {'target_word': 'eat', 'translate': 'есть'},
        {'target_word': 'cat', 'translate': 'кошка'},
        {'target_word': 'dog', 'translate': 'собака'},
        {'target_word': 'elephant', 'translate': 'слон'},
        {'target_word': 'book', 'translate': 'книга'},
        {'target_word': 'sun', 'translate': 'солнце'},
        {'target_word': 'water', 'translate': 'вода'}
    ]

    if add_user(session, 'Initial User'):
        for word_pare in initial_data:
            word = Words(target_word=word_pare['target_word'], translate=word_pare['translate'])
            session.add(word)
            session.commit()
            user_word = UserWord(user_id=1, word_id=word.id)
            session.add(user_word)
            session.commit()