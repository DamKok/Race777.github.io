import os
import logging
import random
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Загрузка переменных окружения ---
load_dotenv()

# --- Получение конфигурации из .env ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID', '0')

# --- Проверка обязательных переменных ---
if not BOT_TOKEN:
    logging.error("❌ BOT_TOKEN не найден в .env файле!")
    logging.error("Создайте файл .env с содержимым: BOT_TOKEN=ваш_токен")
    exit(1)

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- База данных и игровая логика ---
class RacingGame:
    def __init__(self):
        self.init_db()
        self.cars = {
            1: {"name": "Старый седан 🚗", "price": 0, "speed": 3, "acceleration": 2, "handling": 3},
            2: {"name": "Спортивный хэтчбек 🚙", "price": 5000, "speed": 5, "acceleration": 6, "handling": 5},
            3: {"name": "Гоночная мыльница 🏎️", "price": 15000, "speed": 7, "acceleration": 8, "handling": 6},
            4: {"name": "Суперкар 🔥", "price": 50000, "speed": 9, "acceleration": 9, "handling": 8},
            5: {"name": "Гоночный болид 💀", "price": 150000, "speed": 10, "acceleration": 10, "handling": 9}
        }
        self.active_challenges = {}
        self.ensure_db_schema()

    def ensure_db_schema(self):
        """Проверяем и обновляем схему базы данных"""
        conn = sqlite3.connect('racing.db')
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS players
                    (user_id INTEGER PRIMARY KEY, 
                     username TEXT,
                     balance INTEGER DEFAULT 1000,
                     car_id INTEGER DEFAULT 1,
                     experience INTEGER DEFAULT 0,
                     level INTEGER DEFAULT 1,
                     wins INTEGER DEFAULT 0,
                     races INTEGER DEFAULT 0,
                     pvp_wins INTEGER DEFAULT 0,
                     pvp_races INTEGER DEFAULT 0)''')
        
        conn.commit()
        conn.close()

    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect('racing.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS players
                    (user_id INTEGER PRIMARY KEY, 
                     username TEXT,
                     balance INTEGER DEFAULT 1000,
                     car_id INTEGER DEFAULT 1,
                     experience INTEGER DEFAULT 0,
                     level INTEGER DEFAULT 1,
                     wins INTEGER DEFAULT 0,
                     races INTEGER DEFAULT 0,
                     pvp_wins INTEGER DEFAULT 0,
                     pvp_races INTEGER DEFAULT 0)''')
        conn.commit()
        conn.close()

    def get_player(self, user_id):
        """Безопасное получение данных игрока"""
        conn = sqlite3.connect('racing.db')
        c = conn.cursor()
        
        try:
            c.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
            player = c.fetchone()
            
            if player:
                player_list = list(player)
                while len(player_list) < 10:
                    player_list.append(0)
                player = tuple(player_list)
                
        except Exception as e:
            logger.error(f"Ошибка при получении игрока {user_id}: {e}")
            player = None
        
        conn.close()
        return player

    def register_player(self, user_id, username):
        """Регистрация нового игрока"""
        conn = sqlite3.connect('racing.db')
        c = conn.cursor()
        
        try:
            c.execute("""INSERT OR IGNORE INTO players 
                        (user_id, username, balance, car_id, experience, level, wins, races, pvp_wins, pvp_races) 
                        VALUES (?, ?, 1000, 1, 0, 1, 0, 0, 0, 0)""", 
                     (user_id, username))
            conn.commit()
        except Exception as e:
            logger.error(f"Ошибка при регистрации игрока: {e}")
        
        conn.close()

    def update_balance(self, user_id, amount):
        """Обновление баланса игрока"""
        conn = sqlite3.connect('racing.db')
        c = conn.cursor()
        c.execute("UPDATE players SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()

    def buy_car(self, user_id, car_id):
        """Покупка автомобиля"""
        conn = sqlite3.connect('racing.db')
        c = conn.cursor()
        c.execute("SELECT balance FROM players WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        
        if not result:
            conn.close()
            return False
            
        balance = result[0]
        car_price = self.cars[car_id]["price"]
        
        if balance >= car_price:
            c.execute("UPDATE players SET balance = balance - ?, car_id = ? WHERE user_id = ?", 
                     (car_price, car_id, user_id))
            conn.commit()
            conn.close()
            return True
        
        conn.close()
        return False

    def update_stats_after_race(self, user_id, earnings, exp_gain, is_win=False, is_pvp=False):
        """Обновление статистики после гонки"""
        conn = sqlite3.connect('racing.db')
        c = conn.cursor()
        
        try:
            if is_pvp:
                c.execute('''UPDATE players 
                             SET balance = balance + ?, 
                                 experience = experience + ?,
                                 pvp_races = pvp_races + 1,
                                 pvp_wins = pvp_wins + ?
                             WHERE user_id = ?''', 
                         (earnings, exp_gain, 1 if is_win else 0, user_id))
            else:
                c.execute('''UPDATE players 
                             SET balance = balance + ?, 
                                 experience = experience + ?,
                                 races = races + 1,
                                 wins = wins + ?
                             WHERE user_id = ?''', 
                         (earnings, exp_gain, 1 if is_win else 0, user_id))
            
            c.execute("SELECT experience, level FROM players WHERE user_id = ?", (user_id,))
            result = c.fetchone()
            if result:
                exp, level = result
                new_level = exp // 100 + 1
                if new_level > level:
                    c.execute("UPDATE players SET level = ? WHERE user_id = ?", (new_level, user_id))
                    conn.commit()
                    conn.close()
                    return True
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики: {e}")
        
        conn.close()
        return False

# --- Создаем экземпляр игры ---
game = RacingGame()

# --- Главное меню ---
def get_main_menu():
    """Клавиатура главного меню"""
    keyboard = [
        [InlineKeyboardButton("👤 Профиль", callback_data="menu_profile"),
         InlineKeyboardButton("🏎️ Гараж", callback_data="menu_garage")],
        [InlineKeyboardButton("🏁 Гонка с ИИ", callback_data="menu_race"),
         InlineKeyboardButton("⚔️ Вызов игрока", callback_data="menu_challenge")],
        [InlineKeyboardButton("🏆 Топ игроков", callback_data="menu_top"),
         InlineKeyboardButton("🔄 Обновить", callback_data="menu_refresh")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Команды бота ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    game.register_player(user.id, user.first_name)
    
    welcome_text = (
        f"🏎️ Добро пожаловать в гоночную лигу, {user.first_name}!\n\n"
        "🎯 Управляйте своим автомобилем, участвуйте в гонках и станьте лучшим гонщиком!\n\n"
        "💡 Используйте кнопки ниже для навигации:"
    )
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=get_main_menu())
    else:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=get_main_menu())

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    player_data = game.get_player(user.id)
    
    if not player_data:
        await query.answer("Сначала зарегистрируйтесь через /start", show_alert=True)
        return
    
    # Безопасная распаковка
    try:
        if len(player_data) >= 10:
            user_id, username, balance, car_id, exp, level, wins, races, pvp_wins, pvp_races = player_data
        else:
            user_id, username, balance, car_id, exp, level, wins, races = player_data[:8]
            pvp_wins, pvp_races = 0, 0
    except ValueError as e:
        await query.answer("❌ Ошибка в данных профиля", show_alert=True)
        return
    
    car = game.cars.get(car_id, game.cars[1])
    
    profile_text = (
        f"👤 **Профиль гонщика**\n\n"
        f"🏷️ **Имя:** {username}\n"
        f"⭐ **Уровень:** {level}\n"
        f"📊 **Опыт:** {exp}/{(level * 100)}\n"
        f"💰 **Баланс:** {balance} кредитов\n\n"
        f"🏎️ **Автомобиль:** {car['name']}\n"
        f"🚀 **Скорость:** {car['speed']}/10\n"
        f"⚡ **Ускорение:** {car['acceleration']}/10\n"
        f"🎯 **Управление:** {car['handling']}/10\n\n"
        f"📈 **Статистика:**\n"
        f"🏆 PvE: {wins} из {races} побед\n"
        f"⚔️ PvP: {pvp_wins} из {pvp_races} побед"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="menu_profile"),
         InlineKeyboardButton("🔙 Назад", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(profile_text, reply_markup=reply_markup)

async def show_garage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    player_data = game.get_player(user.id)
    
    if not player_data:
        await query.answer("Сначала зарегистрируйтесь через /start", show_alert=True)
        return
    
    balance = player_data[2]
    current_car_id = player_data[3]
    
    garage_text = f"🏁 **Гараж**\n\n💰 **Ваш баланс:** {balance} кредитов\n\n"
    
    keyboard = []
    for car_id, car in game.cars.items():
        if car_id == current_car_id:
            status = "✅ ВАШ АВТОМОБИЛЬ"
            callback_data = "none"
        elif balance >= car['price']:
            status = f"🛒 Купить за {car['price']} кредитов"
            callback_data = f"buy_{car_id}"
        else:
            status = f"❌ Недостаточно средств ({car['price']})"
            callback_data = "none"
        
        car_info = f"{car['name']}\n🚀{car['speed']} ⚡{car['acceleration']} 🎯{car['handling']} - {status}"
        
        if callback_data != "none":
            keyboard.append([InlineKeyboardButton(car_info, callback_data=callback_data)])
        else:
            keyboard.append([InlineKeyboardButton(car_info, callback_data="none")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="menu_main")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(garage_text, reply_markup=reply_markup)

async def start_race(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    player_data = game.get_player(user.id)
    
    if not player_data:
        await query.answer("Сначала зарегистрируйтесь через /start", show_alert=True)
        return
    
    # Безопасная распаковка
    try:
        if len(player_data) >= 8:
            user_id, username, balance, car_id, exp, level, wins, races = player_data[:8]
        else:
            await query.answer("❌ Ошибка данных", show_alert=True)
            return
    except ValueError as e:
        await query.answer("❌ Ошибка в данных", show_alert=True)
        return
    
    player_car = game.cars.get(car_id, game.cars[1])
    
    # Ищем оппонента (ИИ)
    opponent_car = random.choice(list(game.cars.values()))
    
    # Расчет силы игрока и оппонента
    player_power = (player_car['speed'] * 2 + 
                   player_car['acceleration'] * 1.5 + 
                   player_car['handling'] * 1.2 + 
                   random.randint(1, 10))
    
    opponent_power = (opponent_car['speed'] * 2 + 
                     opponent_car['acceleration'] * 1.5 + 
                     opponent_car['handling'] * 1.2 + 
                     random.randint(1, 10))
    
    # Анимация гонки
    await query.edit_message_text(
        f"🏁 **Начинаем гонку!**\n\n"
        f"🏎️ {player_car['name']} vs {opponent_car['name']}\n\n"
        f"🔧 Подготовка к старту..."
    )
    
    # Определение победителя
    if player_power > opponent_power:
        earnings = 500
        exp_gain = 25
        win_text = "🏆 ПОБЕДА! 🏆"
        is_win = True
    elif player_power < opponent_power:
        earnings = 100
        exp_gain = 10
        win_text = "💔 Поражение"
        is_win = False
    else:
        earnings = 250
        exp_gain = 15
        win_text = "🤝 Ничья"
        is_win = False
    
    # Обновление данных игрока
    level_up = game.update_stats_after_race(user.id, earnings, exp_gain, is_win, False)
    
    level_up_text = f"\n🎉 **Новый уровень!** Теперь у вас {level + 1} уровень!" if level_up else ""
    
    result_text = (
        f"🏁 **Гонка завершена!**\n\n"
        f"🏎️ {player_car['name']} vs {opponent_car['name']}\n\n"
        f"💪 **Ваша сила:** {player_power}\n"
        f"💪 **Сила оппонента:** {opponent_power}\n\n"
        f"**{win_text}**\n"
        f"💰 **Заработано:** {earnings} кредитов\n"
        f"⭐ **Опыт:** +{exp_gain}"
        f"{level_up_text}"
    )
    
    keyboard = [
        [InlineKeyboardButton("🏁 Еще гонку", callback_data="menu_race"),
         InlineKeyboardButton("🔙 В меню", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(result_text, reply_markup=reply_markup)

async def show_challenge_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    
    # Проверяем, что команда вызвана в группе
    if query.message.chat.type not in ['group', 'supergroup']:
        await query.answer(
            "❌ Вызовы работают только в группах!\n\n"
            "Добавьте меня в группу для гонок с друзьями.",
            show_alert=True
        )
        return
    
    player_data = game.get_player(user.id)
    if not player_data:
        await query.answer("Сначала зарегистрируйтесь через /start", show_alert=True)
        return
    
    challenge_text = (
        "⚔️ **Вызов игрока**\n\n"
        "Бросьте вызов другому игроку в этой группе!\n"
        "Победитель получает 1000 кредитов и 50 опыта."
    )
    
    keyboard = [
        [InlineKeyboardButton("🎯 Бросить вызов", callback_data="create_challenge")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(challenge_text, reply_markup=reply_markup)

async def create_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    player_data = game.get_player(user.id)
    
    if not player_data:
        await query.answer("Сначала зарегистрируйтесь через /start", show_alert=True)
        return
    
    # Безопасное получение данных
    car_id = player_data[3] if len(player_data) > 3 else 1
    level = player_data[5] if len(player_data) > 5 else 1
    
    # Создаем уникальный ID для вызова
    challenge_id = f"{user.id}_{int(datetime.now().timestamp())}"
    
    # Сохраняем вызов
    game.active_challenges[challenge_id] = {
        'challenger_id': user.id,
        'challenger_name': user.first_name,
        'challenger_car_id': car_id,
        'chat_id': query.message.chat_id,
        'message_id': query.message.message_id,
        'created_at': datetime.now()
    }
    
    challenge_text = (
        f"🏎️ **{user.first_name} бросает вызов на гонку!**\n\n"
        f"🚗 **Автомобиль:** {game.cars[car_id]['name']}\n"
        f"⭐ **Уровень:** {level}\n\n"
        "Кто готов соревноваться?"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎯 Принять вызов!", callback_data=f"accept_{challenge_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu_challenge")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(challenge_text, reply_markup=reply_markup)

async def show_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    conn = sqlite3.connect('racing.db')
    c = conn.cursor()
    
    try:
        c.execute('''SELECT username, level, wins, races, pvp_wins, pvp_races, balance 
                     FROM players 
                     ORDER BY (wins + pvp_wins * 2) DESC, level DESC 
                     LIMIT 10''')
        leaders = c.fetchall()
    except Exception as e:
        logger.error(f"Ошибка при получении топа: {e}")
        leaders = []
    
    conn.close()
    
    if not leaders:
        top_text = "🏆 **Топ гонщиков**\n\nПока нет данных о игроках."
    else:
        top_text = "🏆 **Топ гонщиков**\n\n"
        for i, leader in enumerate(leaders, 1):
            if len(leader) == 7:  # Новая структура с PvP
                username, level, wins, races, pvp_wins, pvp_races, balance = leader
                total_wins = wins + pvp_wins
                total_races = races + pvp_races
            else:  # Старая структура без PvP
                username, level, wins, races, balance = leader
                total_wins = wins
                total_races = races
            
            win_rate = (total_wins / total_races * 100) if total_races > 0 else 0
            top_text += f"{i}. **{username}** - Ур.{level} 🏆{total_wins} ({win_rate:.1f}%) 💰{balance}\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="menu_top"),
         InlineKeyboardButton("🔙 Назад", callback_data="menu_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(top_text, reply_markup=reply_markup)

# --- Обработчики кнопок ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "menu_main":
        await start(update, context)
    
    elif data == "menu_profile":
        await show_profile(update, context)
    
    elif data == "menu_garage":
        await show_garage(update, context)
    
    elif data == "menu_race":
        await start_race(update, context)
    
    elif data == "menu_challenge":
        await show_challenge_menu(update, context)
    
    elif data == "menu_top":
        await show_top(update, context)
    
    elif data == "menu_refresh":
        await start(update, context)
    
    elif data == "create_challenge":
        await create_challenge(update, context)
    
    elif data.startswith('buy_'):
        car_id = int(data.split('_')[1])
        success = game.buy_car(query.from_user.id, car_id)
        
        if success:
            await query.answer(f"🎉 Вы купили {game.cars[car_id]['name']}!", show_alert=True)
            await show_garage(update, context)
        else:
            await query.answer("❌ Недостаточно средств для покупки!", show_alert=True)
    
    elif data.startswith('accept_'):
        challenge_id = data.replace('accept_', '')
        
        # Проверяем существование вызова
        if challenge_id not in game.active_challenges:
            await query.answer("❌ Вызов устарел или уже принят!", show_alert=True)
            return
        
        challenge_data = game.active_challenges[challenge_id]
        
        # Не позволяем самому себе принимать вызов
        if query.from_user.id == challenge_data['challenger_id']:
            await query.answer("🤔 Вы не можете принять свой же вызов!", show_alert=True)
            return
        
        # Проверяем, что принимающий зарегистрирован
        acceptor_data = game.get_player(query.from_user.id)
        if not acceptor_data:
            await query.answer("❌ Сначала зарегистрируйтесь через /start", show_alert=True)
            return
        
        # Удаляем вызов из активных
        del game.active_challenges[challenge_id]
        
        # Запускаем PvP гонку
        await run_pvp_race(query, challenge_data, acceptor_data)

async def run_pvp_race(query, challenge_data, acceptor_data):
    try:
        challenger_id = challenge_data['challenger_id']
        challenger_name = challenge_data['challenger_name']
        
        acceptor_id = acceptor_data[0]
        acceptor_name = acceptor_data[1]
        
        # Безопасное получение car_id
        challenger_car_id = challenge_data.get('challenger_car_id', 1)
        acceptor_car_id = acceptor_data[3] if len(acceptor_data) > 3 else 1
        
        # Получаем данные об автомобилях
        challenger_car = game.cars.get(challenger_car_id, game.cars[1])
        acceptor_car = game.cars.get(acceptor_car_id, game.cars[1])
        
        # Анимация гонки
        await query.edit_message_text(
            f"⚔️ **PvP Гонка начинается!**\n\n"
            f"🏎️ {challenger_name} vs {acceptor_name}\n\n"
            f"🔧 Подготовка к старту..."
        )
        
        # Расчет силы с случайным фактором
        challenger_power = (challenger_car['speed'] * 2 + 
                           challenger_car['acceleration'] * 1.5 + 
                           challenger_car['handling'] * 1.2 + 
                           random.randint(1, 15))
        
        acceptor_power = (acceptor_car['speed'] * 2 + 
                         acceptor_car['acceleration'] * 1.5 + 
                         acceptor_car['handling'] * 1.2 + 
                         random.randint(1, 15))
        
        # Определяем победителя
        if challenger_power > acceptor_power:
            winner_id = challenger_id
            winner_name = challenger_name
            loser_id = acceptor_id
            earnings = 1000
            exp_gain = 50
        elif acceptor_power > challenger_power:
            winner_id = acceptor_id
            winner_name = acceptor_name
            loser_id = challenger_id
            earnings = 1000
            exp_gain = 50
        else:
            winner_id = None
            earnings = 500
            exp_gain = 30
        
        # Обновляем статистику
        if winner_id:
            game.update_stats_after_race(winner_id, earnings, exp_gain, True, True)
            game.update_stats_after_race(loser_id, 200, 20, False, True)
            
            result_text = (
                f"🏆 **ПОБЕДИТЕЛЬ: {winner_name}!**\n\n"
                f"💪 {challenger_name}: {challenger_power} силы\n"
                f"💪 {acceptor_name}: {acceptor_power} силы\n\n"
                f"🎉 {winner_name} получает {earnings} кредитов и {exp_gain} опыта!\n"
                f"😢 Проигравший получает 200 кредитов и 20 опыта"
            )
        else:
            game.update_stats_after_race(challenger_id, earnings, exp_gain, False, True)
            game.update_stats_after_race(acceptor_id, earnings, exp_gain, False, True)
            
            result_text = (
                f"🤝 **НИЧЬЯ!**\n\n"
                f"💪 {challenger_name}: {challenger_power} силы\n"
                f"💪 {acceptor_name}: {acceptor_power} силы\n\n"
                f"💰 Оба игрока получают {earnings} кредитов и {exp_gain} опыта!"
            )
        
        keyboard = [
            [InlineKeyboardButton("⚔️ Новый вызов", callback_data="menu_challenge"),
             InlineKeyboardButton("🔙 В меню", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🏁 **PvP Гонка завершена!**\n\n{result_text}",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Ошибка в run_pvp_race: {e}")
        await query.edit_message_text("❌ Произошла ошибка при запуске гонки. Попробуйте снова.")

# --- Очистка старых вызовов ---
async def cleanup_challenges(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    expired_challenges = []
    
    for challenge_id, challenge_data in game.active_challenges.items():
        if (now - challenge_data['created_at']).seconds > 1800:  # 30 минут
            expired_challenges.append(challenge_id)
    
    for challenge_id in expired_challenges:
        del game.active_challenges[challenge_id]
    
    if expired_challenges:
        logger.info(f"Очищено {len(expired_challenges)} просроченных вызовов")

# --- Главная функция ---
def main():
    # Используем BOT_TOKEN из .env файла
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    
    # Обработчики кнопок
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Запуск очистки вызовов
    job_queue = application.job_queue
    job_queue.run_repeating(cleanup_challenges, interval=1800, first=10)
    
    # Запуск бота
    print("✅ Конфигурация загружена из .env файла!")
    print("🏎️ Гоночный бот запущен...")
    logger.info("Бот запущен с защищенной конфигурацией")
    
    try:
        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        print("❌ Ошибка при запуске бота. Проверьте BOT_TOKEN в .env файле")

if __name__ == '__main__':
    main()