import telebot
from telebot import types
import random
from random import shuffle
import asyncio
import logging
import time
import threading


notification_timers = {}


logging.basicConfig(level=logging.INFO)

bot = telebot.TeleBot("7191998889:AAHk1HXznlL0-xI7DDanbPdiYvQLI8zb_Qs")

# Словарь со всеми чатами и игроками в этих чатах
chat_list = {}
game_tasks = {}
registration_timers = {}
game_start_timers = {}
# Словарь для хранения времени последнего нажатия кнопки каждым игроком
vote_timestamps = {}

is_night = False

class Game:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = {}
        self.dead_last_words = {}  # Инициализация словаря для последних слов убитых игроков
        self.dead = None
        self.sheriff_check = None
        self.sheriff_shoot = None
        self.sheriff_id = None
        self.sergeant_id = None
        self.doc_target = None
        self.vote_counts = {}
        self.confirm_votes = {'yes': 0, 'no': 0, 'voted': {}}
        self.game_running = False
        self.button_id = None
        self.dList_id = None
        self.shList_id = None
        self.docList_id = None
        self.mafia_votes = {}
        self.mafia_voting_message_id = None
        self.don_id = None
        self.lucky_id = None
        self.vote_message_id = None
        self.hobo_id = None  # ID Бомжа
        self.hobo_target = None  # Цель Бомжа
        self.hobo_visitors = []  # Посетители цели Бомжа
        self.suicide_bomber_id = None  # ID Смертника
        self.suicide_hanged = False  # Переменная для отслеживания повешенного самоубийцы
        self.all_dead_players = []
        self.lover_id = None
        self.lover_target_id = None
        self.previous_lover_target_id = None
        self.last_sheriff_menu_id = None
        self.lawyer_id = None
        self.lawyer_target = None

    def update_player_list(self):
        players_list = ", ".join([player['name'] for player in self.players.values()])
        return players_list

    def remove_player(chat, player_id, killed_by=None):
     if player_id in chat.players:
        dead_player = chat.players.pop(player_id)  # Удаляем игрока из текущего списка игроков
        
        # Сохраняем информацию об убитом игроке в список убитых
        chat.all_dead_players.append(f"{dead_player['name']} - {dead_player['role']}")

        # Если игрок был убит ночью (мафией или шерифом), отправляем сообщение
        if killed_by == 'night':
            bot.send_message(player_id, "Тебя убили :( Можешь написать здесь своё последнее сообщение.")
            chat.dead_last_words[player_id] = dead_player['name']  # Сохраняем имя игрока для последнего сообщения

def change_role(player_id, player_dict, new_role, text, game):
    player_dict[player_id]['role'] = new_role
    player_dict[player_id]['action_taken'] = False
    player_dict[player_id]['skipped_actions'] = 0
    try:
        bot.send_message(player_id, text)
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение игроку {player_id}: {e}")
    if new_role == '🤵🏻‍♂️ Дон':
        player_dict[player_id]['don'] = True
    else:
        player_dict[player_id]['don'] = False
    if new_role == '💣 Смертник':
        game.suicide_bomber_id = player_id
    logging.info(f"Игрок {player_dict[player_id]['name']} назначен на роль {new_role}")

def list_btn(player_dict, user_id, player_role, text, action_type, message_id=None):
    players_btn = types.InlineKeyboardMarkup()
    
    for key, val in player_dict.items():
        logging.info(f"Обработка игрока: {val['name']} (ID: {key}) - Роль: {val['role']}")

        # Условие для доктора, чтобы не лечить себя дважды
        if player_role == 'доктор' and key == user_id:
            logging.info(f"Доктор {val['name']} - self_healed: {val.get('self_healed', False)}")
            if val.get('self_healed', False):
                logging.info(f"Доктор {val['name']} уже лечил себя, не добавляем в список.")
                continue
            else:
                logging.info(f"Доктор {val['name']} еще не лечил себя, добавляем в список.")
                players_btn.add(types.InlineKeyboardButton(val['name'], callback_data=f'{key}_{action_type}'))
                continue

        # Условие для адвоката, чтобы он не выбирал мертвых игроков и самого себя
        if player_role == '👨‍⚖️ Адвокат' and (key == user_id or val['role'] == 'dead'):
            logging.info(f"Адвокат не может выбрать мертвого игрока или самого себя.")
            continue

        # Добавление остальных игроков в список
        if key != user_id and val['role'] != 'dead':
            players_btn.add(types.InlineKeyboardButton(val['name'], callback_data=f'{key}_{action_type}'))

    # Добавление кнопки "Назад" для шерифа
    if player_role == '🕵️‍♂️ Шериф':
        logging.info("Добавляем кнопку 'Назад' для шерифа.")
        players_btn.add(types.InlineKeyboardButton('Назад', callback_data=f'back_{player_role[0]}'))

    logging.info(f"Редактирование сообщения с кнопками для {player_role}.")
    
    if message_id:
        try:
            bot.edit_message_text(chat_id=user_id, message_id=message_id, text=text, reply_markup=players_btn)
        except Exception as e:
            logging.error(f"Ошибка при редактировании сообщения: {e}")
    else:
        try:
            msg = bot.send_message(user_id, text, reply_markup=players_btn)
            logging.info(f"Сообщение с кнопками отправлено, message_id: {msg.message_id}")
            return msg.message_id
        except Exception as e:
            logging.error(f"Ошибка при отправке сообщения с кнопками: {e}")


def registration_message(players):
    if players:
        player_names = [f"[{player['name']}](tg://user?id={player_id})" for player_id, player in players.items()]
        player_list = ', '.join(player_names)
        return f"*Ведётся набор в игру*\n{player_list}\n_{len(player_names)} игроков_"
    else:
        return "*Ведётся набор в игру*\n_Зарегистрированных нет_"

def night_message(players):
    living_players = [f"{i + 1}. [{player['name']}](tg://user?id={player_id})" for i, (player_id, player) in enumerate(players.items()) if player['role'] != 'dead']
    player_list = '\n'.join(living_players)
    return f"*Живые игроки:*\n{player_list}\n\nспать осталось *45* сек.\n"

def day_message(players):
    living_players = [f"{i + 1}. [{player['name']}](tg://user?id={player_id})" for i, (player_id, player) in enumerate(players.items()) if player['role'] != 'dead']
    player_list = '\n'.join(living_players)
    roles = [player['role'] for player in players.values() if player['role'] != 'dead']
    role_counts = {role: roles.count(role) for role in set(roles)}

    roles_text = ', '.join([f"{role} ({count})" if count > 1 else f"{role}" for role, count in role_counts.items()])

    return f"*Живые игроки:*\n{player_list}\n\n*Кто-то из них*:\n{roles_text}\nВсего: *{len(living_players)}* чел.\n\nСейчас самое время обсудить результаты ночи, разобраться в причинах и следствиях…"
    
def players_alive(player_dict, phase):
    if phase == "registration":
        return registration_message(player_dict)
    elif phase == "night":
        return night_message(player_dict)
    elif phase == "day":
        return day_message(player_dict)

def emoji(role):
    emojis = {
        'мафия': '🤵🏻',
        'шериф': '🕵🏼️‍♂️',
        'мирный житель': '👨🏼',
        'доктор': '👨‍⚕️'
    }
    return emojis.get(role, '')

def voice_handler(chat_id):
    global chat_list
    chat = chat_list[chat_id]
    players = chat.players
    votes = []
    for player_id, player in players.items():
        if 'voice' in player:
            votes.append(player['voice'])
            del player['voice']
    if votes:
        dead_id = max(set(votes), key=votes.count)
        dead = players.pop(dead_id)
        return dead

def send_message_to_mafia(chat, message):
    for player_id, player in chat.players.items():
        if player['role'] in ['🤵🏻 Мафия', '🤵🏻‍♂️ Дон']:
            bot.send_message(player_id, message)

def notify_mafia(chat, sender_name, message, sender_id):
    for player_id, player in chat.players.items():
        if player['role'] in ['🤵🏻 Мафия', '🤵🏻‍♂️ Дон'] and player_id != sender_id:
            role = 'Дон' if chat.players[sender_id]['role'] == '🤵🏻‍♂️ Дон' else 'Мафия'
            bot.send_message(player_id, f"{role} {sender_name}:\n{message}")
        if player['role'] == '👨‍⚖️ Адвокат':
            if chat.players[sender_id]['role'] == '🤵🏻‍♂️ Дон':
                bot.send_message(player_id, f"🤵🏻‍♂️ Дон ???:\n{message}")
            else:
                bot.send_message(player_id, f"🤵🏻 Мафия ???:\n{message}")

def notify_mafia_and_don(chat):
    mafia_and_don_list = []
    # Создаем копию списка игроков, чтобы избежать изменения размера словаря во время итерации
    players_copy = list(chat.players.items())
    
    for player_id, player in players_copy:
        if player['role'] == '🤵🏻‍♂️ Дон':
            mafia_and_don_list.append(f"🤵🏻‍♂️ Дон - {player['name']}")
        elif player['role'] == '🤵🏻 Мафия':
            mafia_and_don_list.append(f"🤵🏻 Мафия - {player['name']}")
    
    message = "Запоминай своих союзников:\n" + "\n".join(mafia_and_don_list)
    
    for player_id, player in players_copy:
        if player['role'] in ['🤵🏻 Мафия', '🤵🏻‍♂️ Дон']:
            bot.send_message(player_id, message)

def notify_one_minute_left(chat_id):
    global registration_timers
    if chat_id in registration_timers:
        del registration_timers[chat_id]  # Удаляем таймер из словаря, если он сработал
    if chat_id in chat_list:
        chat = chat_list[chat_id]
        if not chat.game_running and chat.button_id:
            join_btn = types.InlineKeyboardMarkup()
            bot_username = bot.get_me().username
            join_url = f'https://t.me/{bot_username}?start=join_{chat_id}'
            item1 = types.InlineKeyboardButton('🤵🏻 Присоединиться', url=join_url)
            join_btn.add(item1)
            bot.send_message(chat_id, '❗️Регистрация закончится через 59 сек.', reply_markup=join_btn)

def start_game_with_delay(chat_id):
    global notification_timers, game_start_timers

    if chat_id in chat_list:
        chat = chat_list[chat_id]
        if chat.game_running:  # Проверяем, начата ли игра
            # Если игра начата, отменяем таймер уведомления
            if chat_id in notification_timers:
                notification_timers[chat_id].cancel()
                del notification_timers[chat_id]
            # Отменяем таймер старта игры
            if chat_id in game_start_timers:
                game_start_timers[chat_id].cancel()
                del game_start_timers[chat_id]
            return

        if chat.button_id:
            bot.delete_message(chat_id, chat.button_id)
            chat.button_id = None

        # Отменяем таймер уведомления, если он существует
        if chat_id in notification_timers:
            notification_timers[chat_id].cancel()
            del notification_timers[chat_id]

        # Отменяем таймер старта игры, если он существует
        if chat_id in game_start_timers:
            game_start_timers[chat_id].cancel()
            del game_start_timers[chat_id]

        _start_game(chat_id)

def reset_registration(chat_id):
    global notification_timers, game_start_timers
    chat = chat_list.get(chat_id)

    # Удаляем текущее сообщение о регистрации
    if chat and chat.button_id:
        bot.delete_message(chat_id, chat.button_id)
        chat.button_id = None

    # Очищаем список игроков
    if chat:
        chat.players.clear()
        chat.game_running = False  # Обнуляем состояние игры

    # Отменяем таймер уведомления, если он существует
    if chat_id in notification_timers:
        notification_timers[chat_id].cancel()
        del notification_timers[chat_id]

    # Отменяем таймер старта игры, если он существует
    if chat_id in game_start_timers:
        game_start_timers[chat_id].cancel()
        del game_start_timers[chat_id]

def add_player(chat, user_id, user_name):
    chat.players[user_id] = {'name': user_name, 'role': 'ждет', 'skipped_actions': 0, 'status': 'alive'}
    
def confirm_vote(chat_id, player_id, player_name, confirm_votes, player_list):
    confirm_markup = types.InlineKeyboardMarkup(row_width=2)  # Устанавливаем две кнопки в строке
    confirm_markup.add(
        types.InlineKeyboardButton(f"👍 {confirm_votes['yes']}", callback_data=f"confirm_{player_id}_yes"),
        types.InlineKeyboardButton(f"👎 {confirm_votes['no']}", callback_data=f"confirm_{player_id}_no")
    )

    # Создаем кликабельную ссылку на игрока
    player_link = f"[{player_name}](tg://user?id={player_id})"
    
    # Используем кликабельную ссылку в сообщении
    msg = bot.send_message(chat_id, f"Вы точно хотите вешать {player_link}?", reply_markup=confirm_markup, parse_mode="Markdown")
    
    logging.info(f"Сообщение подтверждения голосования отправлено с message_id: {msg.message_id}")
    return msg.message_id, f"Вы точно хотите вешать {player_link}?"
    
def end_day_voting(chat):
    if not chat.vote_counts:  # Если нет голосов
        bot.send_message(chat.chat_id, "Голосование окончено\nМнения жителей разошлись...\nРазошлись и сами жители,\nтак никого и не повесив...")
        reset_voting(chat)  # Сброс голосования
        
        # Сбрасываем блокировку голосования у всех игроков
        for player in chat.players.values():
            player['voting_blocked'] = False
        
        if check_game_end(chat, time.time()):
            return False  # Игра завершена
        return False  # Немедленно продолжаем игру

    max_votes = max(chat.vote_counts.values(), default=0)
    potential_victims = [player_id for player_id, votes in chat.vote_counts.items() if votes == max_votes]

    if len(potential_victims) == 1 and max_votes > 0:
        player_id = potential_victims[0]
        if player_id in chat.players:  # Проверка, что игрок существует
            player_name = chat.players[player_id]['name']
            chat.confirm_votes['player_id'] = player_id  # Сохраняем player_id для подтверждения голосования
            chat.vote_message_id, chat.vote_message_text = confirm_vote(chat.chat_id, player_id, player_name, chat.confirm_votes, chat.players)  # Отправляем подтверждающее голосование
            return True  # Ждем подтверждения голосования
        else:
            logging.error(f"Игрок с id {player_id} не найден в chat.players")
            reset_voting(chat)
            
            # Сбрасываем блокировку голосования у всех игроков
            for player in chat.players.values():
                player['voting_blocked'] = False
                
            return False  # Немедленно продолжаем игру
    else:
        # Если голоса равны или нет результата, выводим сообщение и немедленно продолжаем игру
        bot.send_message(chat.chat_id, "Голосование окончено\nМнения жителей разошлись...\nРазошлись и сами жители,\nтак никого и не повесив...")
        reset_voting(chat)  # Сброс голосования
        
        # Сбрасываем блокировку голосования у всех игроков
        for player in chat.players.values():
            player['voting_blocked'] = False
        
        if check_game_end(chat, time.time()):
            return False  # Игра завершена
        return False  # Продолжаем игру без ожидания

def handle_confirm_vote(chat):
    yes_votes = chat.confirm_votes['yes']
    no_votes = chat.confirm_votes['no']

    # Обрабатываем только если идет подтверждающее голосование
    if yes_votes == no_votes:
        # Если подтверждающее голосование завершилось равными голосами, выводим результат и продолжаем игру
        send_voting_results(chat, yes_votes, no_votes)
        disable_vote_buttons(chat)  # Добавляем вызов удаления кнопок
    elif yes_votes > no_votes:
        # Если больше голосов "за", игрок казнен
        dead_id = chat.confirm_votes['player_id']
        if dead_id in chat.players:
            dead = chat.players[dead_id]
            disable_vote_buttons(chat)
            send_voting_results(chat, yes_votes, no_votes, dead['name'])
            bot.send_message(chat.chat_id, f'{dead["name"]} был {dead["role"]}', parse_mode="Markdown")
            chat.remove_player(dead_id)
            
            # Проверка, был ли этот игрок Доном
            if dead['role'] == '🤵🏻‍♂️ Дон':
                check_and_transfer_don_role(chat)

            # Проверка, был ли этот игрок Шерифом
            if dead['role'] == '🕵️‍♂️ Шериф':
                check_and_transfer_sheriff_role(chat)

        else:
            logging.error(f"Игрок с id {dead_id} не найден в chat.players")
    else:
        # Если больше голосов "против", игрок не казнен
        disable_vote_buttons(chat)
        send_voting_results(chat, yes_votes, no_votes)

    reset_voting(chat)  # Сбрасываем голосование после подтверждения

def disable_vote_buttons(chat):
    try:
        if chat.vote_message_id:
            logging.info(f"Попытка удаления кнопок голосования с message_id: {chat.vote_message_id}")
            # Удаляем кнопки
            updated_text = f"{chat.vote_message_text}\n\nГолосование завершено"
            bot.edit_message_text(chat_id=chat.chat_id, message_id=chat.vote_message_id, text=updated_text, parse_mode="Markdown")
            
            bot.edit_message_reply_markup(chat_id=chat.chat_id, message_id=chat.vote_message_id, reply_markup=None)
        else:
            logging.error("vote_message_id не установлен.")
    except Exception as e:
        logging.error(f"Не удалось заблокировать кнопки для голосования: {e}")

def send_voting_results(chat, yes_votes, no_votes, player_name=None):
    if yes_votes > no_votes:
        result_text = f"Результаты голосования:\n👍 {yes_votes} | 👎 {no_votes}\n\nВешаем {player_name}!"
    else:
        result_text = f"Результаты голосования:\n👍 {yes_votes} | 👎 {no_votes}\n\nЖители передумали вешать, и разошлись по домам!"

    bot.send_message(chat.chat_id, result_text)


def send_sheriff_menu(chat, sheriff_id, message_id=None):
    sheriff_menu = types.InlineKeyboardMarkup()
    sheriff_menu.add(types.InlineKeyboardButton('🔍 Проверять', callback_data=f'{sheriff_id}_check'))
    sheriff_menu.add(types.InlineKeyboardButton('🔫 Стрелять', callback_data=f'{sheriff_id}_shoot'))

    new_text = "Выбери своё действие в эту ночь"

    if message_id:
        # Если message_id передан, редактируем существующее сообщение
        bot.edit_message_text(chat_id=sheriff_id, message_id=message_id, text=new_text, reply_markup=sheriff_menu)
    else:
        # Иначе отправляем новое сообщение
        msg = bot.send_message(sheriff_id, new_text, reply_markup=sheriff_menu)
        chat.last_sheriff_menu_id = msg.message_id  # Сохраняем идентификатор последнего меню

def reset_voting(chat):
    # Очищаем все переменные, связанные с голосованием
    chat.vote_counts.clear()
    chat.confirm_votes = {'yes': 0, 'no': 0, 'voted': {}}
    chat.vote_message_id = None
    
    # Сбрасываем флаг голосования у каждого игрока
    for player in chat.players.values():
        player['has_voted'] = False

def handle_night_action(callback_query, chat, player_role):
    player_id = callback_query.from_user.id
    player = chat.players.get(player_id)

    if not is_night:
        bot.answer_callback_query(callback_query.id, text="Это действие доступно только ночью.")
        return False
    
    # Проверка, совершил ли шериф уже проверку или стрельбу
    if player_role == '🕵️‍♂️ Шериф' and (chat.sheriff_check or chat.sheriff_shoot):
        bot.answer_callback_query(callback_query.id, text="Вы уже сделали свой выбор этой ночью.")
        bot.delete_message(player_id, callback_query.message.message_id)
        return False

    if player.get('action_taken', False):
        bot.answer_callback_query(callback_query.id, text="Вы уже сделали свой выбор этой ночью.")
        bot.delete_message(player_id, callback_query.message.message_id)
        return False

    player['action_taken'] = True  # Отмечаем, что действие совершено
    return True

def check_and_transfer_don_role(chat):
    if chat.don_id not in chat.players or chat.players[chat.don_id]['role'] == 'dead':
        # Дон мертв, проверяем, есть ли еще мафия
        alive_mafia = [player_id for player_id, player in chat.players.items() if player['role'] == '🤵🏻 Мафия']
        if alive_mafia:
            new_don_id = alive_mafia[0]
            change_role(new_don_id, chat.players, '🤵🏻‍♂️ Дон', 'Теперь ты Дон!', chat)
            chat.don_id = new_don_id
            bot.send_message(chat.chat_id, "🤵🏻 Мафия унаследовала роль 🤵🏻‍♂️ Дон")
        else:
            logging.info("Все мафиози мертвы, роль Дона не передана.")

def check_game_end(chat, game_start_time):
    mafia_count = len([p for p in chat.players.values() if p['role'] in ['🤵🏻 Мафия', '🤵🏻‍♂️ Дон'] and p['status'] != 'dead'])
    lawyer_count = len([p for p in chat.players.values() if p['role'] == '👨‍⚖️ Адвокат' and p['status'] != 'dead'])
    non_mafia_count = len([p for p in chat.players.values() if p['role'] not in ['🤵🏻 Мафия', '🤵🏻‍♂️ Дон', '👨‍⚖️ Адвокат'] and p['status'] != 'dead'])

    total_mafia_team = mafia_count + lawyer_count

    # Проверяем условие победы
    if total_mafia_team == 0:
        winning_team = "Мирные жители"
        winners = [f"[{v['name']}](tg://user?id={k}) - {v['role']}" for k, v in chat.players.items() if v['role'] not in ['🤵🏻 Мафия', '🤵🏻‍♂️ Дон', '👨‍⚖️ Адвокат'] and v['status'] != 'dead']
    else:
        if (total_mafia_team == 1 and non_mafia_count == 1) or \
           (total_mafia_team == 2 and non_mafia_count == 1) or \
           (total_mafia_team == 3 and non_mafia_count == 2) or \
           (total_mafia_team == 4 and non_mafia_count == 2) or \
           (total_mafia_team == 5 and non_mafia_count == 3):
            winning_team = "Мафия"
            winners = [f"[{v['name']}](tg://user?id={k}) - {v['role']}" for k, v in chat.players.items() if v['role'] in ['🤵🏻 Мафия', '🤵🏻‍♂️ Дон', '👨‍⚖️ Адвокат'] and v['status'] != 'dead']
        else:
            return False  # Игра продолжается

    # Формируем список всех оставшихся участников, включая вышедших игроков
    winners_ids = [k for k, v in chat.players.items() if f"[{v['name']}](tg://user?id={k}) - {v['role']}" in winners]
    remaining_players = [f"[{v['name']}](tg://user?id={k}) - {v['role']}" for k, v in chat.players.items() if k not in winners_ids and v['status'] not in ['dead', 'left']]

    # Добавляем игроков, которые вышли
    remaining_players.extend([f"[{v['name']}](tg://user?id={k}) - {v['role']}" for k, v in chat.players.items() if v['status'] == 'left'])

    # Добавляем всех убитых игроков за игру
    all_dead_players = [f"[{player.split(' - ')[0]}](tg://user?id={k}) - {player.split(' - ')[1]}" for k, player in enumerate(chat.all_dead_players)]

    # Подсчитываем время игры
    game_duration = time.time() - game_start_time
    minutes = int(game_duration // 60)
    seconds = int(game_duration % 60)

    # Формируем сообщение с результатами
    result_text = (f"*Игра окончена!*\n"
                   f"Победили: *{winning_team}*\n\n"
                   f"*Победители:*\n" + "\n".join(winners) + "\n\n"
                   f"*Остальные участники:*\n" + "\n".join(remaining_players + all_dead_players) + "\n\n"
                   f"Игра длилась: {minutes} мин. {seconds} сек.")

    bot.send_message(chat.chat_id, result_text, parse_mode="Markdown")

    # Отправляем сообщение всем участникам
    for player_id in chat.players:
        try:
            bot.send_message(player_id, "Игра окончена! Спасибо за участие.")
        except Exception as e:
            logging.error(f"Не удалось отправить сообщение игроку {player_id}: {e}")

    # Сброс игры
    reset_game(chat)
    return True  # Игра окончена

def reset_game(chat):
    chat.players.clear()  # Очищаем список игроков
    chat.dead = None
    chat.sheriff_check = None
    chat.sheriff_shoot = None
    chat.sheriff_id = None
    chat.doc_target = None
    chat.vote_counts.clear()
    chat.confirm_votes = {'yes': 0, 'no': 0, 'voted': {}}
    chat.game_running = False
    chat.button_id = None
    chat.dList_id = None
    chat.shList_id = None
    chat.docList_id = None
    chat.mafia_votes.clear()
    chat.mafia_voting_message_id = None
    chat.don_id = None
    chat.lucky_id = None
    chat.vote_message_id = None
    chat.hobo_id = None
    chat.hobo_target = None
    chat.hobo_visitors.clear()
    chat.suicide_bomber_id = None
    chat.suicide_hanged = False
    logging.info(f"Игра сброшена в чате {chat.chat_id}")

def escape_markdown(text):
    escape_chars = r'\*_`['
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

def check_and_transfer_sheriff_role(chat):
    if chat.sheriff_id not in chat.players or chat.players[chat.sheriff_id]['role'] == 'dead':
        # Шериф мертв, проверяем, есть ли сержант
        if chat.sergeant_id and chat.sergeant_id in chat.players and chat.players[chat.sergeant_id]['role'] != 'dead':
            new_sheriff_id = chat.sergeant_id
            change_role(new_sheriff_id, chat.players, '🕵️‍♂️ Шериф', 'Теперь ты Шериф!', chat)
            chat.sheriff_id = new_sheriff_id
            chat.sergeant_id = None  # Теперь сержант становится шерифом, и роль сержанта больше не нужна
            bot.send_message(chat.chat_id, "👮🏼 Сержант унаследовал роль 🕵️‍♂️ Шерифа")
        else:
            logging.info("Нет сержанта для передачи роли шерифа.")

def notify_police(chat):
    police_members = []
    if chat.sheriff_id and chat.sheriff_id in chat.players and chat.players[chat.sheriff_id]['role'] == '🕵️‍♂️ Шериф':
        police_members.append(f"🕵️‍♂️ Шериф - {chat.players[chat.sheriff_id]['name']}")
    if chat.sergeant_id and chat.sergeant_id in chat.players and chat.players[chat.sergeant_id]['role'] == '👮🏼 Сержант':
        police_members.append(f"👮🏼 Сержант - {chat.players[chat.sergeant_id]['name']}")

    message = "🚓 Состав полиции:\n" + "\n".join(police_members)

    for player_id in [chat.sheriff_id, chat.sergeant_id]:
        if player_id in chat.players:
            bot.send_message(player_id, message)

@bot.message_handler(commands=['start'])
def start_message(message):
    # Проверяем, что команда пришла из приватного чата
    if message.chat.type != 'private':
        return

    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text

    # Проверяем, есть ли параметр после команды /start
    if len(text.split()) > 1:
        param = text.split()[1]
        if param.startswith("join_"):
            game_chat_id = int(param.split('_')[1])
            chat = chat_list.get(game_chat_id)
            if chat:
                if chat.game_running:
                    bot.send_message(user_id, "Ошибка: игра уже началась.")
                elif not chat.button_id:
                    bot.send_message(user_id, "Ошибка: регистрация не открыта.")
                elif user_id not in chat.players:
                    user_name = message.from_user.first_name
                    chat.players[user_id] = {'name': user_name, 'role': 'ждет', 'skipped_actions': 0}
                    bot.send_message(user_id, f"Вы присоединились в чате «{bot.get_chat(game_chat_id).title}»")

                    # Добавляем задержку перед обновлением сообщения
                    time.sleep(1.5)

                    # Обновляем сообщение о регистрации игроков
                    new_text = players_alive(chat.players, "registration")
                    new_markup = types.InlineKeyboardMarkup([[types.InlineKeyboardButton('🤵🏻 Присоединиться', url=f'https://t.me/{bot.get_me().username}?start=join_{game_chat_id}')]])

                    try:
                        bot.edit_message_text(chat_id=game_chat_id, message_id=chat.button_id, text=new_text, reply_markup=new_markup, parse_mode="Markdown")
                    except Exception as e:
                        logging.error(f"Ошибка обновления сообщения: {e}")
                else:
                    bot.send_message(user_id, "Вы уже зарегистрированы в этой игре.")
            else:
                bot.send_message(user_id, "Ошибка: игра не найдена.")
            return

    # Создаем клавиатуру для кнопок "🎲 Войти в чат", "📰 Новости" и "🤵🏻 Добавить игру в свой чат"
    keyboard = types.InlineKeyboardMarkup()
    
    # Кнопка "🎲 Войти в чат"
    join_chat_btn = types.InlineKeyboardButton('🎲 Войти в чат', callback_data='join_chat')
    keyboard.add(join_chat_btn)
    
    # Кнопка "📰 Новости"
    news_btn = types.InlineKeyboardButton('📰 Новости', url='https://t.me/RealMafiaNews')
    keyboard.add(news_btn)

    # Формируем ссылку для добавления бота в группу
    bot_username = bot.get_me().username
    add_to_group_url = f'https://t.me/{bot_username}?startgroup=bot_command'
    
    # Кнопка "🤵🏻 Добавить игру в свой чат" (добавление бота в группу)
    add_to_group_btn = types.InlineKeyboardButton('🤵🏻 Добавить игру в свой чат', url=add_to_group_url)
    keyboard.add(add_to_group_btn)

    # Отправляем сообщение с приветствием и клавиатурой
    bot.send_message(chat_id, 'Привет!\nЯ ведущий бот по игре мафия🤵🏻. Начнем играть?', reply_markup=keyboard)
    
@bot.callback_query_handler(func=lambda call: call.data == 'join_chat')
def join_chat_callback(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id


    # Создаем клавиатуру для кнопки "🛠️ Тестовый"
    test_button = types.InlineKeyboardMarkup()
    test_btn = types.InlineKeyboardButton('🛠️ Тестовый', url='https://t.me/+ZAgUMKzgjKRkNTli')
    test_button.add(test_btn)

    # Отправляем сообщение с кнопкой "🛠️ Тестовый"
    bot.send_message(chat_id, 'Выберите чат для общения:', reply_markup=test_button)

@bot.message_handler(commands=['game'])
def create_game(message):
    chat_id = message.chat.id
    if chat_id not in chat_list:
        chat_list[chat_id] = Game(chat_id)

    chat = chat_list[chat_id]

    if chat.game_running or chat.button_id:
        # Игнорируем команду и удаляем сообщение, если игра уже начата или регистрация уже открыта
        bot.delete_message(chat_id, message.message_id)
        return

    join_btn = types.InlineKeyboardMarkup()
    bot_username = bot.get_me().username
    join_url = f'https://t.me/{bot_username}?start=join_{chat_id}'
    item1 = types.InlineKeyboardButton('🤵🏻 Присоединиться', url=join_url)
    join_btn.add(item1)

    # Отправляем начальное сообщение о наборе
    msg_text = registration_message(chat.players)
    msg = bot.send_message(chat_id, msg_text, reply_markup=join_btn, parse_mode="Markdown")
    chat.button_id = msg.message_id

    bot.pin_chat_message(chat_id, msg.message_id)

    # Удаляем сообщение с командой /game
    bot.delete_message(chat_id, message.message_id)

    # Запускаем таймер на 1 минуту для уведомления и на 2 минуты для начала игры
    notification_timers[chat_id] = threading.Timer(60.0, lambda: notify_one_minute_left(chat_id))
    game_start_timers[chat_id] = threading.Timer(120.0, lambda: start_game_with_delay(chat_id))
    
    notification_timers[chat_id].start()
    game_start_timers[chat_id].start()

@bot.message_handler(commands=['start_game'])
def start_game(message):
    chat_id = message.chat.id
    _start_game(chat_id)

def _start_game(chat_id):
    global notification_timers

    if chat_id not in chat_list:
        bot.send_message(chat_id, 'Сначала создайте игру с помощью команды /game.')
        return

    chat = chat_list[chat_id]
    if chat.game_running:
        bot.send_message(chat_id, 'Игра уже начата.')
        return

    if len(chat.players) < 4:
        bot.send_message(chat_id, '*Недостаточно игроков для начала игры*', parse_mode="Markdown")
        reset_registration(chat_id)
        return

    # Удаляем сообщение о регистрации перед началом игры
    if chat.button_id:
        bot.delete_message(chat_id, chat.button_id)
        chat.button_id = None

    # Отменяем таймер уведомления, если он установлен
    if chat_id in notification_timers:
        notification_timers[chat_id].cancel()
        del notification_timers[chat_id]

    # Отменяем таймер старта игры, если он установлен
    if chat_id in game_start_timers:
        game_start_timers[chat_id].cancel()
        del game_start_timers[chat_id]

    # Устанавливаем флаг, что игра запущена
    chat.game_running = True

    # Инициализируем время начала игры
    chat.game_start_time = time.time()

    bot.send_message(chat_id, '*Игра начинается!*', parse_mode="Markdown")

    players_list = list(chat.players.items())
    shuffle(players_list)

    num_players = len(players_list)
    num_mafias = max(1, (num_players // 3))  # Минимум одна мафия
    mafia_assigned = 0

    # Установим статус alive для всех игроков перед началом игры
    for player_id, player_info in chat.players.items():
        player_info['status'] = 'alive'

    # Назначение Дона
    logging.info(f"Назначение Дона: {players_list[0][1]['name']}")
    change_role(players_list[0][0], chat.players, '🤵🏻‍♂️ Дон', 'Ты — 🤵🏻‍♂️ Дон!\n\nТвоя задача управлять мафией и убрать всех мирных жителей.', chat)
    chat.don_id = players_list[0][0]
    mafia_assigned += 1

    # Назначение мафии
    for i in range(1, num_players):
        if mafia_assigned < num_mafias:
            logging.info(f"Назначение Мафии: {players_list[i][1]['name']}")
            change_role(players_list[i][0], chat.players, '🤵🏻 Мафия', 'Ты — 🤵🏻 Мафия!\n\nТвоя задача убрать всех мирных жителей.', chat)
            mafia_assigned += 1

    roles_assigned = mafia_assigned + 1  # Учитывая Дона

    # Назначение доктора при 4 и более игроках
    if roles_assigned < num_players and num_players >= 4:
        logging.info(f"Назначение Доктора: {players_list[roles_assigned][1]['name']}")
        change_role(players_list[roles_assigned][0], chat.players, '👨‍⚕️ Доктор', 'Ты — 👨‍⚕️ Доктор!\n\nТвоя задача спасать жителей от рук мафии.', chat)
        roles_assigned += 1

    # Назначение Самоубийцы при 4 и более игроках
    if roles_assigned < num_players and num_players >= 10:
        logging.info(f"Назначение Самоубийцы: {players_list[roles_assigned][1]['name']}")
        change_role(players_list[roles_assigned][0], chat.players, '🤦‍♂️ Самоубийца', 'Ты — 🤦‍♂️ Самоубийца!\n\nТвоя задача - быть повешенным, чтобы победить.', chat)
        chat.suicide_bomber_id = players_list[roles_assigned][0]
        roles_assigned += 1

    # Назначение бомжа при 5 и более игроках
    if roles_assigned < num_players and num_players >= 5:
        logging.info(f"Назначение Бомжа: {players_list[roles_assigned][1]['name']}")
        change_role(players_list[roles_assigned][0], chat.players, '🧙‍♂️ Бомж', 'Ты — 🧙‍♂️ Бомж!\n\nТы можешь проверить, кто ночью заходил к выбранному игроку.', chat)
        chat.hobo_id = players_list[roles_assigned][0]
        roles_assigned += 1

    # Назначение шерифа при 6 и более игроках
    if roles_assigned < num_players and num_players >= 6:
        logging.info(f"Назначение Шерифа: {players_list[roles_assigned][1]['name']}")
        change_role(players_list[roles_assigned][0], chat.players, '🕵️‍♂️ Шериф', 'Ты — 🕵️‍♂️ Шериф!\n\nТвоя задача вычислить мафию и спасти город.', chat)
        chat.sheriff_id = players_list[roles_assigned][0]
        roles_assigned += 1

    # Назначение счастливчика при 7 и более игроках
    if roles_assigned < num_players and num_players >= 8:
        logging.info(f"Назначение Счастливчика: {players_list[roles_assigned][1]['name']}")
        change_role(players_list[roles_assigned][0], chat.players, '🤞 Счастливчик', 'Ты — 🤞 Счастливчик!\n\nУ тебя есть 50% шанс выжить, если тебя попытаются убить.', chat)
        chat.lucky_id = players_list[roles_assigned][0]
        roles_assigned += 1

    # Назначение смертника при 12 и более игроках
    if roles_assigned < num_players and num_players >= 12:
        logging.info(f"Назначение Смертника: {players_list[roles_assigned][1]['name']}")
        change_role(players_list[roles_assigned][0], chat.players, '💣 Смертник', 'Ты — 💣 Смертник!\n\nЕсли тебя убьют ночью, ты заберешь своего убийцу с собой.', chat)
        chat.suicide_bomber_id = players_list[roles_assigned][0]
        roles_assigned += 1

    # Назначение Любовницы
    if roles_assigned < num_players and num_players >= 7:
        logging.info(f"Назначение Любовницы: {players_list[roles_assigned][1]['name']}")
        change_role(players_list[roles_assigned][0], chat.players, '💃🏼 Любовница', 'Ты — 💃 Любовница!\n\nТы можешь соблазнить одного игрока и блокировать его действия на одну ночь.', chat)
        chat.lover_id = players_list[roles_assigned][0]
        roles_assigned += 1

    if roles_assigned < num_players and num_players >= 16:  # Адвокат появляется при 5 и более игроках
        logging.info(f"Назначение Адвоката: {players_list[roles_assigned][1]['name']}")
        change_role(players_list[roles_assigned][0], chat.players, '👨‍⚖️ Адвокат', 'Ты — 👨‍⚖️ Адвокат!\n\nТвоя задача защищать клиента и обеспечивать его безопасность.', chat)
        roles_assigned += 1

    if roles_assigned < num_players and num_players >= 15:  # Сержант назначается, если игроков 5 и более
        logging.info(f"Назначение Сержанта: {players_list[roles_assigned][1]['name']}")
        change_role(players_list[roles_assigned][0], chat.players, '👮🏼 Сержант', 'Ты — 👮🏼 Сержант! Ты унаследуешь роль шерифа, если он погибнет.', chat)
        chat.sergeant_id = players_list[roles_assigned][0]
        roles_assigned += 1

    # Назначение оставшихся ролей как мирных жителей
    for i in range(roles_assigned, num_players):
        logging.info(f"Назначение Мирного жителя: {players_list[i][1]['name']}")
        change_role(players_list[i][0], chat.players, '👱‍♂️ Мирный житель', 'Ты — 👱‍♂️ Мирный житель!\n\nТвоя задача найти мафию и защитить город.', chat)

    # Проверка, чтобы никто не остался с ролью "ждет"
    for player_id, player_info in chat.players.items():
        if player_info['role'] == 'ждет':
            logging.error(f"Игрок {player_info['name']} остался без роли!")
            change_role(player_id, chat.players, '👱‍♂️ Мирный житель', 'Ты — 👱‍♂️ Мирный житель!\n\nТвоя задача найти мафию и защитить город.', chat)

    # Запуск основного игрового цикла
    asyncio.run(game_cycle(chat_id))

@bot.message_handler(commands=['leave'])
def leave_game(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    chat = chat_list.get(chat_id)

    if not chat:
        bot.send_message(chat_id, "Игра не найдена.")
        return

    if user_id not in chat.players:
        bot.send_message(chat_id, "Вы не зарегистрированы в этой игре.")
        return

    role = chat.players[user_id]['role']
    name = chat.players[user_id]['name']
    
    # Удаляем игрока из списка
    chat.players.pop(user_id)

    if chat.game_running:
        bot.send_message(user_id, "Вы вышли из игры.")
        bot.send_message(chat_id, f"{name} не выдержал гнетущей атмосферы этого города и покинул игру. Он был {emoji(role)} {role}")

        # Проверка, был ли этот игрок Доном
        if role == '🤵🏻‍♂️ Дон':
            check_and_transfer_don_role(chat)
        
        # Проверка, был ли этот игрок Шерифом
        if role == '🕵️‍♂️ Шериф':
            check_and_transfer_sheriff_role(chat)
    else:
        # Обновляем только количество игроков и список участников
        player_count = len(chat.players)

        if player_count == 0:
            updated_message_text = "*Ведётся набор в игру*\n_0 игроков_"
        else:
            updated_message_text = registration_message(chat.players)

        # Обновляем сообщение о регистрации
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=chat.button_id, text=updated_message_text, reply_markup=types.InlineKeyboardMarkup([[types.InlineKeyboardButton('🤵🏻 Присоединиться', url=f'https://t.me/{bot.get_me().username}?start=join_{chat_id}')]]), parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Ошибка при обновлении сообщения регистрации: {e}")

    # Удаление сообщения пользователя из общего чата
    bot.delete_message(chat_id, message.message_id)

@bot.message_handler(commands=['stop'])
def stop_game(message):
    global game_tasks, registration_timers

    chat_id = message.chat.id
    user_id = message.from_user.id

    # Проверяем, что пользователь является администратором
    chat_member = bot.get_chat_member(chat_id, user_id)
    if chat_member.status not in ['administrator', 'creator']:
        bot.send_message(chat_id, "Только администраторы могут останавливать игру.")
        return

    # Остановка таймера регистрации, если он существует
    if chat_id in registration_timers:
        registration_timers[chat_id].cancel()
        del registration_timers[chat_id]

    # Завершение игры, если она началась
    if chat_id in game_tasks:
        game_tasks[chat_id].cancel()  # Останавливаем цикл игры
        del game_tasks[chat_id]

    if chat_id in chat_list:
        chat = chat_list[chat_id]
        if chat.game_running:
            chat.game_running = False
            bot.send_message(chat_id, "🚫 *Игра остановлена\nадминистратором!*", parse_mode="Markdown")
            reset_game(chat)  # Сбрасываем игру
        else:
            reset_registration(chat_id)  # Сбрасываем регистрацию, если игра не началась
            bot.send_message(chat_id, "*🚫 Регистрация отменена\nадминистратором*", parse_mode="Markdown")
    

bot_username = "@nrlv_bot"

# Обновленный код для функции game_cycle
async def game_cycle(chat_id):
    global chat_list, is_night, is_voting_time, game_tasks
    chat = chat_list[chat_id]
    game_start_time = time.time()

    day_count = 1

    try:
        while chat.game_running:  # Основной цикл игры
            if not chat.game_running:
                break
            await asyncio.sleep(5)

            if not chat.game_running:
                break

            # Начало ночи
            is_night = True
            is_voting_time = False  # Убедимся, что голосование неактивно ночью

            # Сохраняем предыдущую цель любовницы перед сбросом
            chat.previous_lover_target_id = chat.lover_target_id  # Перенос текущей цели в предыдущую

            # Сброс всех выборов перед началом ночи
            chat.dead = None
            chat.sheriff_check = None
            chat.sheriff_shoot = None
            chat.doc_target = None
            chat.mafia_votes.clear()
            chat.hobo_target = None
            chat.hobo_visitors.clear()
            chat.lover_target_id = None  # Сброс цели любовницы
            chat.shList_id = None
            chat.lawyer_target = None  # Сброс цели адвоката

            dead_id = None

            # Сбрасываем флаг action_taken у всех игроков перед новой ночью
            for player in chat.players.values():
                player['action_taken'] = False

            if not chat.game_running:
                break

            players_alive_text = players_alive(chat.players, "night")

            # Создание кнопки для личного сообщения бота
            bot_username = bot.get_me().username
            private_message_url = f'https://t.me/{bot_username}'
            private_message_btn = types.InlineKeyboardMarkup()
            private_message_btn.add(types.InlineKeyboardButton('Перейти к боту', url=private_message_url))

            # Отправляем сообщение с кнопкой и списком живых игроков
            bot.send_animation(chat_id, 'https://t.me/Hjoxbednxi/13', caption='🌃 *Наступает ночь*\nНа улицы города выходят лишь самые отважные и бесстрашные.\nУтром попробуем сосчитать их головы...', parse_mode="Markdown", reply_markup=private_message_btn)
            bot.send_message(chat_id=chat_id, text=players_alive_text, parse_mode="Markdown", reply_markup=private_message_btn)

            notify_mafia_and_don(chat)
            
            notify_police(chat)  # Уведомляем полицейских о составе

            if not chat.game_running:
                break

            # Отправляем новые кнопки выбора для ночных ролей
            for player_id, player in chat.players.items():
                if not chat.game_running:
                    break

                if player['role'] in ['🤵🏻 Мафия', '🤵🏻‍♂️ Дон']:
                    list_btn(chat.players, player_id, 'мафия', 'Кого будем устранять?', 'м')

                elif player['role'] == '🕵️‍♂️ Шериф':
                    send_sheriff_menu(chat, player_id)

                elif player['role'] == '👨‍⚕️ Доктор':
                    list_btn(chat.players, player_id, 'доктор', 'Кого будем лечить?', 'д')

                elif player['role'] == '🧙‍♂️ Бомж':
                    list_btn(chat.players, player_id, 'бомж', 'К кому пойдешь за бутылкой?', 'б')

                elif player['role'] == '💃🏼 Любовница':
                    players_btn = types.InlineKeyboardMarkup()
                    for key, val in chat.players.items():
                        if key != player_id and val['role'] != 'dead' and (chat.previous_lover_target_id is None or key != chat.previous_lover_target_id):
                            players_btn.add(types.InlineKeyboardButton(val['name'], callback_data=f'{key}_л'))

                    bot.send_message(player_id, "С кем будешь проводить ночь?", reply_markup=players_btn)

                elif player['role'] == '👨‍⚖️ Адвокат':
                    list_btn(chat.players, player_id, 'адвокат', 'Кого будешь защищать?', 'а')

            await asyncio.sleep(30)
            if not chat.game_running:
                break
            is_night = False

            # Обработка действий любовницы
            don_blocked = False
            if chat.lover_target_id and chat.lover_target_id in chat.players:
                lover_target = chat.players[chat.lover_target_id]
                bot.send_message(chat.lover_target_id, '"Ты со мною забудь обо всём...", - пела 💃🏼 Любовница', parse_mode="Markdown")

                # Устанавливаем флаг блокировки голосования
                lover_target['voting_blocked'] = True

                # Отправляем сообщение игроку, что голосовать он не сможет

                if lover_target['role'] == '🤵🏻‍♂️ Дон':
                    don_blocked = True  # Блокируем убийство мафией
                elif lover_target['role'] == '🕵️‍♂️ Шериф':
                    chat.sheriff_check = None  # Блокируем проверку шерифа
                    chat.sheriff_shoot = None  # Блокируем выстрел шерифа
                elif lover_target['role'] == '👨‍⚕️ Доктор':
                    chat.doc_target = None  # Блокируем лечение доктора
                elif lover_target['role'] == '🧙‍♂️ Бомж':
                    chat.hobo_visitors.clear()  # Блокируем проверку бомжа
                elif lover_target['role'] == '👨‍⚖️ Адвокат':
                    chat.lawyer_target = None  # Блокируем действие адвоката

            # Обработка результата действия адвоката
            lawyer_target = None
            if chat.lawyer_id and chat.lawyer_id in chat.players:
                lawyer_target = chat.players[chat.lawyer_id].get('lawyer_target')

            # Пример обработки действия мафии
            mafia_victim = None
            if chat.mafia_votes and not chat.dead:  # Проверка на блокировку любовницей
                vote_counts = {}
                for victim_id in chat.mafia_votes.values():
                    if victim_id in vote_counts:
                        vote_counts[victim_id] += 1
                    else:
                        vote_counts[victim_id] = 1

                mafia_victim = max(vote_counts, key=vote_counts.get, default=None)

                if mafia_victim and mafia_victim in chat.players:
                    send_message_to_mafia(chat, f"Мафия выбрала жертву: {chat.players[mafia_victim]['name']}")
                    bot.send_message(chat_id, "🤵🏻 Мафия выбрала жертву...")

                    if don_blocked:
                        mafia_victim = None  # Блокируем убийство Доном
                    else:
                        if mafia_victim == chat.lucky_id:
                            if random.random() < 0.5:
                                bot.send_message(chat_id, f'🤞 Кому-то из игроков повезло.')
                                mafia_victim = None
                            else:
                                chat.dead = (mafia_victim, chat.players[mafia_victim])
                        else:
                            chat.dead = (mafia_victim, chat.players[mafia_victim])
                else:
                    send_message_to_mafia(chat, "Голосование завершено.\nСемья не смогла выбрать жертву.")
            else:
                send_message_to_mafia(chat, "Голосование завершено.\nСемья не смогла выбрать жертву.")

            chat.mafia_votes.clear()

            if not chat.game_running:
                break

            # Обработка результатов действий бомжа
            if chat.hobo_id and chat.hobo_target:
                hobo_target = chat.hobo_target
                if hobo_target in chat.players:  # Проверка существования hobo_target
                    hobo_target_name = chat.players[hobo_target]['name']
                    hobo_visitors = []

                    # Если мафия выбрала ту же цель, что и Бомж
                    if chat.dead and chat.dead[0] == hobo_target:
                        don_id = chat.don_id
                        if don_id in chat.players:
                            don_name = chat.players[don_id]['name']
                            hobo_visitors.append(don_name)

                    # Если Шериф выбрал ту же цель для проверки или стрельбы
                    if chat.sheriff_check == hobo_target or chat.sheriff_shoot == hobo_target:
                        sheriff_id = chat.sheriff_id
                        if sheriff_id in chat.players:
                            sheriff_name = chat.players[sheriff_id]['name']
                            hobo_visitors.append(sheriff_name)

                    # Если Доктор выбрал ту же цель для лечения
                    if chat.doc_target == hobo_target:
                        doc_id = next((pid for pid, p in chat.players.items() if p['role'] == '👨‍⚕️ Доктор'), None)
                        if doc_id and doc_id in chat.players:
                            doc_name = chat.players[doc_id]['name']
                            hobo_visitors.append(doc_name)

                    # Формируем сообщение для Бомжа
                    if hobo_visitors:
                        visitors_names = ', '.join(hobo_visitors)
                        bot.send_message(chat.hobo_id, f'Ты спросил бутылку у {hobo_target_name} и увидел: {visitors_names}.')
                    else:
                        bot.send_message(chat.hobo_id, f'Ты спросил бутылку у {hobo_target_name}, но никто не приходил.')
                else:
                    bot.send_message(chat.hobo_id, 'Ты никого не встретил этой ночью.')

            if not chat.game_running:
                break

            # Удаление игроков, пропустивших действия
            to_remove = []
            for player_id, player in chat.players.items():
                if not chat.game_running:
                    break
                if player['role'] != '👱‍♂️ Мирный житель' and not player.get('action_taken', False):
                    player['skipped_actions'] += 1
                    if player['skipped_actions'] >= 2:
                        to_remove.append(player_id)
                else:
                    player['action_taken'] = False

            bot.send_animation(chat_id, 'https://t.me/Hjoxbednxi/14', caption=f'🏙 *День {day_count}*\nСолнце всходит, подсушивая на тротуарах пролитую ночью кровь...', parse_mode="Markdown")

            await asyncio.sleep(4)

            if not chat.game_running:
                break

            # Обработка убийств
            killed_by_mafia = chat.dead  # Жертва мафии
            killed_by_sheriff = None  # Жертва шерифа

            # Проверка действий Шерифа
            if chat.sheriff_shoot and chat.sheriff_shoot in chat.players:
                shooted_player = chat.players[chat.sheriff_shoot]
                if shooted_player['role'] == '🍀 Счастливчик' and random.random() < 0.5:
                    bot.send_message(chat_id, f"🏹 Шериф стрелял в {shooted_player['name']}, но ему повезло.")
                elif chat.doc_target and chat.doc_target == chat.sheriff_shoot:
                    bot.send_message(chat.doc_target, '👨🏼‍⚕️ Доктор вылечил тебя!', parse_mode="Markdown")
                    chat.sheriff_shoot = None  # Доктор спас жертву
                else:
                    killed_by_sheriff = (chat.sheriff_shoot, chat.players[chat.sheriff_shoot])
                    chat.remove_player(chat.sheriff_shoot, killed_by='night')  # Убит ночью
                chat.sheriff_shoot = None

            if not chat.game_running:
                break

            # Проверка убийства мафией и шерифом одного и того же игрока
            if killed_by_mafia and killed_by_sheriff and killed_by_mafia[0] == killed_by_sheriff[0]:
                dead_id, dead = killed_by_mafia
                if chat.doc_target and chat.doc_target == dead_id:
                    bot.send_message(chat.doc_target, '👨🏼‍⚕️ Доктор вылечил тебя!', parse_mode="Markdown")
                    chat.dead = None  # Доктор спас жертву
                    chat.sheriff_shoot = None  # Отменяем убийство Шерифа
                else:
                    dead_player_link = f"[{dead['name']}](tg://user?id={dead_id})"
                    bot.send_message(chat_id, f'Сегодня жестоко убит *{dead["role"]}* {dead_player_link}...\nВ гостях был 🤵🏻‍♂️ *Дон* и 🕵️‍♂️ *Шериф*', parse_mode="Markdown")
                    chat.remove_player(dead_id, killed_by='night')
                    chat.dead = None
                    chat.sheriff_shoot = None
            else:
                if killed_by_mafia:
                    dead_id, dead = killed_by_mafia
                    if chat.doc_target and chat.doc_target == dead_id:
                        bot.send_message(chat.doc_target, '👨🏼‍⚕️ Доктор вылечил тебя!', parse_mode="Markdown")
                        chat.dead = None  # Доктор спас жертву
                    else:
                        dead_player_link = f"[{dead['name']}](tg://user?id={dead_id})"
                        bot.send_message(chat_id, f'Сегодня жестоко убит *{dead["role"]}* {dead_player_link}...\nГоворят, у него в гостях был 🤵🏻‍♂️ *Дон*', parse_mode="Markdown")
                        chat.remove_player(dead_id, killed_by='night')
                        chat.dead = None
                    # Если жертва мафии - Шериф, передаем его роль сержанту
                    if dead['role'] == '🕵️‍♂️ Шериф':
                        check_and_transfer_sheriff_role(chat)

                        # Если жертва мафии - смертник, он забирает с собой убийцу (Дона)
                        if dead['role'] == '💣 Смертник':
                            don_id = chat.don_id
                            if don_id and don_id in chat.players:
                                if chat.doc_target and chat.doc_target == don_id:
                                    bot.send_message(chat.doc_target, '👨🏼‍⚕️ Доктор вылечил тебя!', parse_mode="Markdown")
                                else:
                                    don_player_link = f"[{chat.players[don_id]['name']}](tg://user?id={don_id})"
                                    bot.send_message(chat_id, f'Сегодня жестоко убит *🤵🏻‍♂️ Дон* {don_player_link}...\nГоворят в гостях был 💣 *Смертник*', parse_mode="Markdown")
                                    chat.remove_player(don_id, killed_by='night')
                                    check_and_transfer_don_role(chat)

                if killed_by_sheriff:
                    dead_id, dead = killed_by_sheriff
                    if dead:
                        if chat.doc_target and chat.doc_target == dead_id:
                            bot.send_message(chat.doc_target, '👨🏼‍⚕️ Доктор вылечил тебя!', parse_mode="Markdown")
                        else:
                            dead_player_link = f"[{dead['name']}](tg://user?id={dead_id})"
                            bot.send_message(chat_id, f"Сегодня жестоко убит *{dead['role']}* {dead_player_link}...\nГоворят, у него в гостях был 🕵️‍♂️ *Шериф*", parse_mode="Markdown")
                            chat.remove_player(dead_id, killed_by='night')

                        if dead['role'] == '🤵🏻‍♂️ Дон':
                            check_and_transfer_don_role(chat)

                        # Если жертва шерифа - смертник, он забирает с собой шерифа
                        if dead['role'] == '💣 Смертник':
                            sheriff_id = chat.sheriff_id
                            if sheriff_id and sheriff_id in chat.players:
                                if chat.doc_target and chat.doc_target == sheriff_id:
                                    bot.send_message(chat.doc_target, '👨🏼‍⚕️ Доктор вылечил тебя!', parse_mode="Markdown")
                                else:
                                    sheriff_player_link = f"[{chat.players[sheriff_id]['name']}](tg://user?id={sheriff_id})"
                                    bot.send_message(chat_id, f'Сегодня жестоко убит *🕵️‍♂️ Шериф* {sheriff_player_link}...\nГоворят в гостях был 💣 *Смертник*', parse_mode="Markdown")
                                    chat.remove_player(sheriff_id, killed_by='night')
                                    check_and_transfer_sheriff_role(chat)

            # Если доктор просто посетил игрока, но не спас его
            if chat.doc_target and chat.doc_target != dead_id:
                bot.send_message(chat.doc_target, '👨🏼‍⚕️ Доктор приходил к тебе в гости!', parse_mode="Markdown")

            if not chat.game_running:
                break

            # Проверка, убит ли кто-то ночью
            if chat.sheriff_shoot is None and chat.dead is None and not killed_by_mafia and not killed_by_sheriff:
                bot.send_message(chat_id, '🌞 Удивительно! Но сегодня все живы!🤷')

            logging.info(f"Цель шерифа: {chat.sheriff_check}, Цель адвоката: {chat.lawyer_target}")

            # Проверка, показывается ли шерифу "мирный житель"
            if chat.lawyer_target and chat.sheriff_check and chat.lawyer_target == chat.sheriff_check:
                checked_player = chat.players[chat.sheriff_check]
                bot.send_message(chat.sheriff_id, f"🕵️‍♂️ Шериф выяснил, что {checked_player['name']} - 👱‍♂️ Мирный житель.")
                if chat.sergeant_id and chat.sergeant_id in chat.players:
                   sergeant_message = f"Шериф проверил {checked_player['name']}, его роль - 👱‍♂️ Мирный житель."
                   bot.send_message(chat.sergeant_id, sergeant_message)
            else:
                if chat.sheriff_check and chat.sheriff_check in chat.players:
                    checked_player = chat.players[chat.sheriff_check]
                    bot.send_message(chat.sheriff_id, f"🕵️‍♂️ Шериф выяснил, что {checked_player['name']} - {checked_player['role']}.")
                    if chat.sergeant_id and chat.sergeant_id in chat.players:
                        sergeant_message = f"Шериф проверил {checked_player['name']}, его роль - {checked_player['role']}."
                        bot.send_message(chat.sergeant_id, sergeant_message)
                else:
                    logging.error(f"Player with ID {chat.sheriff_check} not found in chat.players")

            if check_game_end(chat, game_start_time):
                break  # Если игра закончена, выходим из цикла

            players_alive_text = players_alive(chat.players, "day")
            msg = bot.send_message(chat_id=chat_id, text=players_alive_text, parse_mode="Markdown")
            chat.button_id = msg.message_id

            chat.dead = None
            chat.sheriff_check = None

            await asyncio.sleep(40)

            if not chat.game_running:
                break

            # Начало голосования днем
            is_voting_time = True  # Включаем время голосования
            chat.vote_counts.clear()  # Сброс голосов перед началом нового голосования
            vote_msg = bot.send_message(chat.chat_id, '🌅 Пришло время голосования! Выберите игрока, которого хотите изгнать.', reply_markup=types.InlineKeyboardMarkup([
                [types.InlineKeyboardButton('🗳️ Голосование', url=f'https://t.me/{bot.get_me().username}')]
            ]))
            chat.vote_message_id = vote_msg.message_id

            for player_id in chat.players:
                if not chat.game_running:
                    break
                if player_id != chat.lover_target_id:  # Не отправляем сообщение жертве любовницы
                    try:
                        bot.send_message(player_id, 'Пришло время искать виноватых! Кого ты хочешь повесить?', reply_markup=types.InlineKeyboardMarkup(
                            [[types.InlineKeyboardButton(chat.players[pid]['name'], callback_data=f"{pid}_vote")] for pid in chat.players if pid != player_id]
                        ))
                    except Exception as e:
                        logging.error(f"Не удалось отправить сообщение игроку {player_id}: {e}")

            if not chat.game_running:
                break

            vote_end_time = time.time() + 45
            while time.time() < vote_end_time:
                if not chat.game_running:
                    break
                if all(player.get('has_voted', False) for player in chat.players.values()):
                    break
                await asyncio.sleep(5)

            if not chat.game_running:
                break

            # Обрабатываем результат голосования
            should_continue = end_day_voting(chat)

            # Если игра не должна продолжаться после голосования
            if not should_continue:
                reset_voting(chat)
                day_count += 1
                continue

            is_voting_time = False  # Отключаем время голосования

            if check_game_end(chat, game_start_time):
                break  # Если игра закончена, выходим из цикла

            await asyncio.sleep(30)

            if not chat.game_running:
                break

            # Вызываем обработку подтверждающего голосования
            handle_confirm_vote(chat)

            chat.confirm_votes = {'yes': 0, 'no': 0, 'voted': {}}
            await asyncio.sleep(2)

            chat.vote_counts.clear()
            for player in chat.players.values():
                if not chat.game_running:
                    break
                player['has_voted'] = False

            # Сброс блокировки голосования в конце дня
            for player in chat.players.values():
                player['voting_blocked'] = False  # Разблокируем голосование для всех игроков

            if check_game_end(chat, game_start_time):
                break  # Если игра закончена, выходим из цикла

            day_count += 1

    except asyncio.CancelledError:
        logging.info(f"Игра в чате {chat_id} была принудительно остановлена.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('join_'))
def join_game(call):
    chat_id = int(call.data.split('_')[1])
    chat = chat_list.get(chat_id)
    user_id = call.from_user.id
    user_name = call.from_user.first_name

    if chat and not chat.game_running and chat.button_id:
        if user_id not in chat.players:
            add_player(chat, user_id, user_name)
            bot.answer_callback_query(call.id, text="Вы присоединились к игре!")

            # Обновляем сообщение о наборе
            new_msg_text = registration_message(chat.players)
            bot.edit_message_text(chat_id=chat_id, message_id=chat.button_id, text=new_msg_text, reply_markup=call.message.reply_markup, parse_mode="Markdown")
            
            # Проверяем количество игроков
            if len(chat.players) >= 4:
                _start_game(chat_id)  # Запускаем игру, если зарегистрировалось достаточное количество игроков
        else:
            bot.answer_callback_query(call.id, text="Вы уже зарегистрированы в этой игре.")
    else:
        bot.answer_callback_query(call.id, text="Ошибка: игра уже началась или регистрация не открыта.")


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    global chat_list, is_voting_time, vote_timestamps
    from_id = call.from_user.id
    current_time = time.time()

    chat = None
    for c_id, c in chat_list.items():
        if from_id in c.players:
            chat = c
            chat_id = c_id
            break

    if not chat:
        bot.answer_callback_query(call.id, text="⛔️ ты не в игре.")
        return

    player = chat.players.get(from_id)

    if player['role'] == 'dead':
        bot.answer_callback_query(call.id, text="⛔️ ты мертв!")
        return

    # Проверка блокировки голосования, если игрока выбрала любовница
    if player.get('voting_blocked', False):
        bot.answer_callback_query(call.id, text="💃🏼 Ты со мною забудь обо всём... ")
        return

    # Проверка, нажимал ли игрок кнопку недавно
    if from_id in vote_timestamps:
        last_vote_time = vote_timestamps[from_id]
        if current_time - last_vote_time < 1:
            bot.answer_callback_query(call.id, text="Голос принят!")# Интервал в 3 секунды
            return  # Просто игнорируем нажатие

    # Обновляем время последнего нажатия
    vote_timestamps[from_id] = current_time

    try:
        logging.info(f"Получены данные: {call.data}")
        data_parts = call.data.split('_')

        if len(data_parts) < 2:
            logging.error(f"Недостаточно данных в callback_data: {call.data}")
            return

        action = data_parts[0]
        role = data_parts[1]

        if action in ['yes', 'no']:
            time.sleep(1.5)

        # Обработка действия "Назад"
        if action == 'back':  # Назад к выбору действия шерифа
            if role == '🕵️‍♂️ Шериф' and role.startswith('🕵'):  # Проверяем, содержит ли роль эмодзи шерифа
                chat.players[from_id]['action_taken'] = False  # Сбрасываем флаг action_taken
                send_sheriff_menu(chat, from_id, message_id=call.message.message_id)  # Редактируем текущее сообщение
            return

        # Обработка голосования
        if call.data.startswith('confirm'):
            player_id = int(data_parts[1])
            vote_confirmation = data_parts[2]

            if from_id in chat.confirm_votes['voted']:
                previous_vote = chat.confirm_votes['voted'][from_id]
                if previous_vote == 'yes':
                    chat.confirm_votes['yes'] -= 1
                elif previous_vote == 'no':
                    chat.confirm_votes['no'] -= 1

            chat.confirm_votes['voted'][from_id] = vote_confirmation

            if vote_confirmation == 'yes':
                chat.confirm_votes['yes'] += 1
            elif vote_confirmation == 'no':
                chat.confirm_votes['no'] += 1

            confirm_markup = types.InlineKeyboardMarkup()
            confirm_markup.add(
                types.InlineKeyboardButton(f"👍 {chat.confirm_votes['yes']}", callback_data=f"confirm_{player_id}_yes"),
                types.InlineKeyboardButton(f"👎 {chat.confirm_votes['no']}", callback_data=f"confirm_{player_id}_no")
            )

            # Проверяем, изменилась ли разметка перед обновлением
            current_markup = call.message.reply_markup
            new_markup_data = confirm_markup.to_dict()
            current_markup_data = current_markup.to_dict() if current_markup else None

            if new_markup_data != current_markup_data:
                try:
                    bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=confirm_markup)
                except Exception as e:
                    logging.error(f"Ошибка при обновлении клавиатуры голосования: {e}")
            else:
                logging.info("Клавиатура уже актуальна, обновление не требуется.")

            bot.answer_callback_query(call.id, text="Голос принят!")

            alive_players_count = len([p for p in chat.players.values() if p['role'] != 'dead' and p['status'] == 'alive' and p != chat.confirm_votes['player_id']])
            if chat.confirm_votes['yes'] + chat.confirm_votes['no'] == alive_players_count:
                disable_vote_buttons(chat)
                send_voting_results(chat, chat.players[player_id]['name'], chat.confirm_votes['yes'], chat.confirm_votes['no'])

        else:
            action = data_parts[1]

            # Обработка действий, которые требуют числового значения в первой части данных
            if action in ['ш', 'с', 'м', 'д', 'б', 'л', 'а', 'vote']:
                try:
                    target_id = int(data_parts[0])  # Пробуем преобразовать в число
                except ValueError:
                    logging.error(f"Невозможно преобразовать данные в число: {data_parts[0]}")
                    return

                player_role = chat.players[from_id]['role']

                # Обработка действий для шерифа, мафии, адвоката и других ролей
                if player_role == '🕵️‍♂️ Шериф' and action == 'ш':  # Шериф проверяет игрока
                    chat.sheriff_check = target_id
                    if chat.last_sheriff_menu_id:
                        try:
                            bot.edit_message_text(chat_id=from_id, message_id=chat.last_sheriff_menu_id, text=f"Ты выбрал проверять {chat.players[target_id]['name']}")
                        except Exception as e:
                            logging.error(f"Ошибка при обновлении последнего меню шерифа: {e}")

                    bot.send_message(chat.chat_id, f"🕵️‍♂️ Шериф ушел искать злодеев...")

                    # Уведомляем сержанта
                    if chat.sergeant_id and chat.sergeant_id in chat.players:
                        sergeant_message = f"🕵️‍♂️ Шериф {chat.players[from_id]['name']} отправился проверять {chat.players[target_id]['name']}."
                        bot.send_message(chat.sergeant_id, sergeant_message)

                elif player_role == '🕵️‍♂️ Шериф' and action == 'с':  # Шериф стреляет в игрока
                    chat.sheriff_shoot = target_id
                    if chat.last_sheriff_menu_id:
                        try:
                            bot.edit_message_text(chat_id=from_id, message_id=chat.last_sheriff_menu_id, text=f"Ты выбрал стрелять в {chat.players[target_id]['name']}")
                        except Exception as e:
                            logging.error(f"Ошибка при обновлении последнего меню шерифа: {e}")

                    bot.send_message(chat.chat_id, f"🕵️‍♂️ Шериф зарядил свой пистолет...")

                    # Уведомляем сержанта
                    if chat.sergeant_id and chat.sergeant_id in chat.players:
                        sergeant_message = f"🕵️‍♂️ Шериф {chat.players[from_id]['name']} стреляет в {chat.players[target_id]['name']}."
                        bot.send_message(chat.sergeant_id, sergeant_message)

                elif player_role in ['🤵🏻 Мафия', '🤵🏻‍♂️ Дон'] and action == 'м':  # Мафия или Дон выбирает жертву
                    if not handle_night_action(call, chat, player_role):
                        return

                    if target_id not in chat.players or chat.players[target_id]['role'] == 'dead':
                        bot.answer_callback_query(call.id, "Цель недоступна.")
                        return

                    if from_id not in chat.mafia_votes:
                        chat.mafia_votes[from_id] = target_id
                        victim_name = chat.players[target_id]['name']
                        voter_name = chat.players[from_id]['name']
                        
                        if player_role == '🤵🏻‍♂️ Дон':
                            send_message_to_mafia(chat, f"🤵🏻‍♂️ Дон {voter_name} проголосовал за {victim_name}")
                            for player_id, player in chat.players.items():
                                if player['role'] == '👨‍⚖️ Адвокат':
                                    bot.send_message(player_id, f"🤵🏻‍♂️ Дон ??? проголосовал за {victim_name}")
                        else:
                            send_message_to_mafia(chat, f"🤵🏻 Мафия {voter_name} проголосовал(а) за {victim_name}")
                            for player_id, player in chat.players.items():
                                if player['role'] == '👨‍⚖️ Адвокат':
                                    bot.send_message(player_id, f"🤵🏻 Мафия ??? проголосовал за {victim_name}")

                        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"Ты выбрал(а) {victim_name}")

                        bot.answer_callback_query(call.id, f"Вы проголосовали за {victim_name}")
                    else:
                        bot.answer_callback_query(call.id, "Вы уже проголосовали.")

                elif player_role == '👨‍⚕️ Доктор' and action == 'д':  # Доктор выбирает цель для лечения
                    if not handle_night_action(call, chat, player_role):
                        return
                    
                    if target_id == from_id:
                        if player.get('self_healed', False):  
                            bot.answer_callback_query(call.id, text="Вы уже лечили себя, выберите другого игрока.")
                            return
                        else:
                            player['self_healed'] = True  
                    
                    chat.doc_target = target_id
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"Вы выбрали лечить {chat.players[chat.doc_target]['name']}")
                    bot.send_message(chat.chat_id, "👨‍⚕️ Доктор выбрал цель для лечения...")

                elif player_role == '🧙‍♂️ Бомж' and action == 'б':  # Бомж выбирает цель
                    if not handle_night_action(call, chat, player_role):
                        return
                    chat.hobo_target = target_id
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"Ты ушел за бутылкой к {chat.players[chat.hobo_target]['name']}")
                    bot.send_message(chat.chat_id, f"🧙‍♂️ Бомж пошел к кому-то за бутылкой…")

                elif player_role == '💃🏼 Любовница' and action == 'л':
                    if not handle_night_action(call, chat, player_role):
                        return
                    chat.previous_lover_target_id = chat.lover_target_id
                    chat.lover_target_id = target_id
                    logging.info(f"Предыдущая цель любовницы обновлена: {chat.previous_lover_target_id}")
                    logging.info(f"Текущая цель любовницы: {chat.lover_target_id}")
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"Ты выбрал(а) провести ночь с {chat.players[chat.lover_target_id]['name']}")
                    bot.send_message(chat.chat_id, "💃🏼 Любовница уже ждёт кого-то в гости...")

                elif player_role == '👨‍⚖️ Адвокат' and action == 'а':  # Адвокат выбирает цель
                    if not handle_night_action(call, chat, player_role):
                        return
                    chat.lawyer_target = target_id
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"Ты выбрал защищать {chat.players[chat.lawyer_target]['name']}")
                    bot.send_message(chat.chat_id, "👨‍⚖️ Адвокат выбрал клиента для защиты...")

                elif action == 'vote':  # Голосование
                    if not is_voting_time:  
                        bot.answer_callback_query(call.id, text="Голосование сейчас недоступно.")
                        return

                    if 'vote_counts' not in chat.__dict__:
                        chat.vote_counts = {}

                    if not chat.players[from_id].get('has_voted', False):
                        chat.vote_counts[target_id] = chat.vote_counts.get(target_id, 0) + 1
                        chat.players[from_id]['has_voted'] = True
                        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"Ты выбрал(а) {chat.players[target_id]['name']}")
                        voter_link = f"[{chat.players[from_id]['name']}](tg://user?id={from_id})"
                        target_link = f"[{chat.players[target_id]['name']}](tg://user?id={target_id})"

                        bot.send_message(chat_id, f"{voter_link} проголосовал(а) за {target_link}", parse_mode="Markdown")

                    if all(player.get('has_voted', False) for player in chat.players.values()):
                        end_day_voting(chat)

            # Обработка действий "Проверять" и "Стрелять" для шерифа
            elif action == 'check':  # Шериф выбирает проверку
                list_btn(chat.players, from_id, '🕵️‍♂️ Шериф', 'Кого будем проверять?', 'ш', message_id=chat.last_sheriff_menu_id)

            elif action == 'shoot':  # Шериф выбирает стрельбу
                list_btn(chat.players, from_id, '🕵️‍♂️ Шериф', 'Кого будем стрелять?', 'с', message_id=chat.last_sheriff_menu_id)

    except Exception as e:
        logging.error(f"Ошибка в callback_handler: {e}")

@bot.message_handler(func=lambda message: message.chat.type == 'private')
def handle_private_message(message):
    user_id = message.from_user.id
    chat = next((chat for chat in chat_list.values() if user_id in chat.players or user_id in chat.dead_last_words), None)

    if chat:
        if not chat.game_running:
            logging.info(f"Игра завершена, игнорируем сообщение от {user_id}")
            return

        # Если игрок мертв и может отправить последние слова
        if user_id in chat.dead_last_words:
            player_name = chat.dead_last_words.pop(user_id)
            last_words = message.text
            if last_words:
                player_link = f"[{player_name}](tg://user?id={user_id})"
                bot.send_message(chat.chat_id, f"Кто-то из жителей слышал, как {player_link} кричал перед смертью:\n_{last_words}_", parse_mode="Markdown")
                bot.send_message(user_id, "Сообщение принято и отправлено в чат.")
            return

        # Пересылка сообщений между Шерифом и Сержантом только ночью
        if is_night:
            if user_id == chat.sheriff_id and chat.sergeant_id in chat.players:
                bot.send_message(chat.sergeant_id, f"🕵️‍♂️ Шериф {chat.players[user_id]['name']}:\n{message.text}")
            elif user_id == chat.sergeant_id and chat.sheriff_id in chat.players:
                bot.send_message(chat.sheriff_id, f"👮🏼 Сержант {chat.players[user_id]['name']}:\n{message.text}")
            # Пересылка сообщений между мафией и Доном только ночью
            elif chat.players[user_id]['role'] in ['🤵🏻‍♂️ Дон', '🤵🏻 Мафия']:
                notify_mafia(chat, chat.players[user_id]['name'], message.text, user_id)

@bot.message_handler(func=lambda message: message.chat.type != 'private')
def handle_message(message):
    global is_night
    chat_id = message.chat.id
    user_id = message.from_user.id

    chat = chat_list.get(chat_id)
    if chat:
        if chat.game_running:
            chat_member = bot.get_chat_member(chat_id, user_id)
            is_admin = chat_member.status in ['administrator', 'creator']

            if is_night:
                # Ночью удаляем сообщения всех, кроме сообщений администраторов, начинающихся с '!'
                if not (is_admin and message.text.startswith('!')):
                    logging.info(f"Удаление сообщения ночью от {user_id}: {message.text}")
                    bot.delete_message(chat_id, message.message_id)
                else:
                    logging.info(f"Сообщение ночью сохранено от {user_id} (админ с '!'): {message.text}")
            else:
                # Днем удаляем сообщения от убитых и незарегистрированных игроков, кроме сообщений администраторов, начинающихся с '!'
                if (user_id not in chat.players or chat.players[user_id]['role'] == 'dead') and not (is_admin and message.text.startswith('!')):
                    logging.info(f"Удаление сообщения днем от {user_id}: {message.text}")
                    bot.delete_message(chat_id, message.message_id)
                elif user_id == chat.lover_target_id:
                    # Если игрок был целью любовницы прошлой ночью, удаляем его сообщения
                    logging.info(f"Удаление сообщения от {user_id}, потому что его посетила любовница: {message.text}")
                    bot.delete_message(chat_id, message.message_id)
                else:
                    logging.info(f"Сообщение днем сохранено от {user_id}: {message.text}")

bot.infinity_polling()
