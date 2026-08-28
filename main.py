# -------------------- CẤU HÌNH & LOGGING --------------------
import os
import logging
import asyncio
import threading
import json
import random
import uuid
from datetime import datetime, timedelta
import discord
from discord.ext import commands
from flask import Flask

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("true-architect")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_IDS = set()
if os.getenv("OWNER_IDS"):
    try:
        OWNER_IDS = set(int(x.strip()) for x in os.getenv("OWNER_IDS").split(",") if x.strip())
    except Exception:
        OWNER_IDS = set()

# -------------------- WEB SERVER KEEPALIVE --------------------
app = Flask(__name__)
@app.route("/")
def home(): 
    return "True Architect đang hoạt động..."

def keep_alive():
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080))), daemon=True).start()

# -------------------- KHỞI TẠO BOT --------------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# -------------------- LƯU TRỮ DỮ LIỆU --------------------
DATA_PATH = "moderation_data.json"
RPG_DATA_PATH = "rpg_data.json"
CLAN_DATA_PATH = "clan_data.json"
CODES_DATA_PATH = "codes_data.json"  # Lưu trữ các code độc quyền và lịch sử nhập

DEFAULT_DATA = {"auto_mod": True, "blacklist": []}

def load_json(path, default):
    if not os.path.exists(path):
        return default.copy()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Không thể load {path}: {e}")
        return default.copy()

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Không thể lưu {path}: {e}")

moderation_data = load_json(DATA_PATH, DEFAULT_DATA)
rpg_data = load_json(RPG_DATA_PATH, {})
clan_data = load_json(CLAN_DATA_PATH, {})
codes_data = load_json(CODES_DATA_PATH, {"valid_codes": {}, "used_records": []})

def get_player(user_id):
    uid = str(user_id)
    if uid not in rpg_data:
        rpg_data[uid] = {
            "level": 1,
            "exp": 0,
            "hp_max": 100,
            "mp_max": 50,
            "atk": 15,
            "yen": 1000,
            "qpoint": 0,
            "sp": 0,
            "skills": [],
            "equipped_skills": [None, None, None],
            "inventory": {},
            "last_daily": None,
            "daily_quest": None,
            "in_battle": False,
            "spin_counter": random.randint(1, 3),
            "owned_styles": [],
            "equipped_style": None
        }
        save_json(RPG_DATA_PATH, rpg_data)
    
    player = rpg_data[uid]
    fields = {
        "qpoint": 0, "sp": 0, "skills": [], "equipped_skills": [None, None, None],
        "inventory": {}, "last_daily": None, "daily_quest": None,
        "in_battle": False, "spin_counter": random.randint(1, 3),
        "owned_styles": [], "equipped_style": None
    }
    for key, def_val in fields.items():
        if key not in player:
            player[key] = def_val
            
    save_json(RPG_DATA_PATH, rpg_data)
    return player

def get_player_clan(user_id):
    uid = str(user_id)
    for clan_name, info in clan_data.items():
        if uid in info["members"]:
            return clan_name, info
    return None, None

def make_bar(current, maximum, length=10, fill="🟩", empty="⬛"):
    if maximum <= 0: return empty * length
    ratio = max(0, min(1, current / maximum))
    filled = int(ratio * length)
    return fill * filled + empty * (length - filled)

def check_level_up(p):
    needed = p["level"] * 300
    leveled_up = False
    while p["exp"] >= needed:
        p["exp"] -= needed
        p["level"] += 1
        p["hp_max"] += 20
        p["atk"] += 5
        leveled_up = True
        needed = p["level"] * 300
    return leveled_up

# -------------------- SKILL TREE & STYLES --------------------
SKILL_TREE = {
    "heal": {"name": "Hồi Xuân", "cost": 2, "type": "active", "mp_cost": 20, "desc": "Hồi 40 HP ngay lập tức."},
    "crossover": {"name": "Tuyệt Kỹ Crossover", "cost": 3, "type": "active", "mp_cost": 15, "desc": "Gây 180%-250% sát thương ATK."},
    "rest": {"name": "Rest (Tĩnh Tâm)", "cost": 2, "type": "active", "mp_cost": 0, "desc": "Hồi 15 MP trong trận."},
    "basic_jab": {"name": "Basic Jab", "cost": 0, "type": "active", "mp_cost": 10, "desc": "Cú đấm cơ bản ổn định."},
    "long_guard_counter": {"name": "Long Guard Counter", "cost": 0, "type": "active", "mp_cost": 15, "desc": "Phòng thủ phản đòn tầm xa."},
    "outbox_swift": {"name": "Swift Footwork", "cost": 0, "type": "active", "mp_cost": 12, "desc": "Di chuyển né tránh và phản công nhanh."},
    "hitman_flicker": {"name": "Flicker Jab", "cost": 0, "type": "active", "mp_cost": 15, "desc": "Đòn Jab lắt léo tầm xa khó đoán."},
    "challenger_rush": {"name": "Challenger Barrage", "cost": 0, "type": "active", "mp_cost": 20, "desc": "Chuỗi đòn liên hoàn dồn ép đối thủ."},
    "smash_heavy": {"name": "Demolishing Smash", "cost": 0, "type": "active", "mp_cost": 25, "desc": "Cú đấm móc trời giáng cực mạnh."},
    "chronos_delay": {"name": "Time-Lag Punch", "cost": 0, "type": "active", "mp_cost": 30, "desc": "Đòn đánh làm lệch nhịp độ đối thủ."},
    "freedom_flash": {"name": "Unpredictable Flash", "cost": 0, "type": "active", "mp_cost": 30, "desc": "Bay nhảy tự do tung đòn bất định."},
    "slugger_power": {"name": "Devastating Slugger Hook", "cost": 0, "type": "active", "mp_cost": 35, "desc": "Cú đấm uy lực hủy diệt phòng thủ."},
    "ippo_dempsey": {"name": "Dempsey Roll", "cost": 0, "type": "active", "mp_cost": 40, "desc": "Vòng xoáy số 8 huyền thoại kết liễu kẻ thù."},
    "tiger_strike": {"name": "Tiger Fang Rush", "cost": 0, "type": "active", "mp_cost": 25, "desc": "Mãnh hổ vồ mồi sát thương chí mạng."},
    "demon_aura": {"name": "Demon Bloodlust", "cost": 0, "type": "active", "mp_cost": 35, "desc": "Sát khí quỷ dạ xoa bộc phát hủy diệt."}
}

STYLES = {
    "basic": {"name": "Basic", "rarity": "common", "base_price": 1000, "atk_mod": 1.0, "hp_mod": 1.0, "skills": ["basic_jab", "heal", "rest"], "desc": "Phong cách cơ bản nhất."},
    "long_guard": {"name": "Long Guard", "rarity": "common", "base_price": 1200, "atk_mod": 1.05, "hp_mod": 1.05, "skills": ["long_guard_counter", "heal", "rest"], "desc": "Tư thế thủ cao."},
    "out_boxer": {"name": "Out-Boxer", "rarity": "rare", "base_price": 2500, "atk_mod": 1.10, "hp_mod": 0.95, "skills": ["outbox_swift", "crossover", "rest"], "desc": "Chuyên gia giữ khoảng cách."},
    "hitman": {"name": "Hitman", "rarity": "rare", "base_price": 3000, "atk_mod": 1.15, "hp_mod": 0.95, "skills": ["hitman_flicker", "crossover", "heal"], "desc": "Góc đánh thấp hiểm hóc."},
    "challenger": {"name": "Challenger", "rarity": "epic", "base_price": 6000, "atk_mod": 1.20, "hp_mod": 1.10, "skills": ["challenger_rush", "crossover", "rest"], "desc": "Ý chí chiến đấu kiên cường."},
    "smash": {"name": "Smash", "rarity": "epic", "base_price": 7500, "atk_mod": 1.25, "hp_mod": 1.05, "skills": ["smash_heavy", "crossover", "heal"], "desc": "Sở hữu cú đấm Smash uy lực."},
    "chronos": {"name": "Chronos", "rarity": "legend", "base_price": 15000, "atk_mod": 1.35, "hp_mod": 1.20, "skills": ["chronos_delay", "crossover", "heal"], "desc": "Kiểm soát nhịp độ trận đấu."},
    "freedom": {"name": "Freedom", "rarity": "legend", "base_price": 18000, "atk_mod": 1.40, "hp_mod": 1.15, "skills": ["freedom_flash", "crossover", "rest"], "desc": "Lối đánh linh hoạt bất định."},
    "slugger": {"name": "Slugger", "rarity": "myth", "base_price": 35000, "atk_mod": 1.50, "hp_mod": 1.30, "skills": ["slugger_power", "crossover", "heal"], "desc": "Sức mạnh tối thượng phá vỡ phòng thủ."},
    "ippo": {"name": "Ippo", "rarity": "myth", "base_price": 50000, "atk_mod": 1.60, "hp_mod": 1.40, "skills": ["ippo_dempsey", "crossover", "heal"], "desc": "Tuyệt kỹ Dempsey Roll huyền thoại."},
    "tiger_fang": {"name": "Tiger Fang", "rarity": "legend", "base_price": 20000, "atk_mod": 1.42, "hp_mod": 1.25, "skills": ["tiger_strike", "crossover", "heal"], "desc": "Phong cách mãnh hổ khát máu."},
    "demon_back": {"name": "Demon Back", "rarity": "myth", "base_price": 65000, "atk_mod": 1.70, "hp_mod": 1.50, "skills": ["demon_aura", "crossover", "heal"], "desc": "Sức mạnh đỉnh cao hóa quỷ."},
}

RARITY_COLORS = {
    "common": "⚪ Common", "rare": "🔵 Rare", "epic": "🟣 Epic", "legend": "🟡 Legend", "myth": "🔴 Myth"
}

BOSSES = [
    {"name": "Superman (DC)", "hp": 950, "atk": 75, "exp": 1200, "yen": 35000},
    {"name": "Sentry (Marvel)", "hp": 1050, "atk": 85, "exp": 1500, "yen": 42000}
]

REGULAR_ENEMIES = [
    {"name": "Quickbullet", "hp": 85, "atk": 11, "exp": 45, "yen": 900},
    {"name": "Gã Trộm Đồ Lặt Vặt Hẻm Nhỏ", "hp": 55, "atk": 6, "exp": 20, "yen": 300},
    {"name": "Sát Thủ Passione", "hp": 100, "atk": 12, "exp": 50, "yen": 1000}
]

def get_scaled_price(base_price, level):
    return int(base_price * (1 + (level - 1) * 0.25))

# -------------------- COMMAND GỘP: !Thelps --------------------
@bot.command(name="Thelps")
async def thelps_command(ctx, category: str = "main"):
    cat = category.lower()

    if cat in ["style", "styles"]:
        p = get_player(ctx.author.id)
        embed = discord.Embed(title="🥊 TRA CỨU DANH SÁCH UBG STYLES", description="Giá mua style tự động tăng theo cấp độ người chơi!", color=discord.Color.gold())
        owned = p.get("owned_styles", [])
        curr = p.get("equipped_style")

        for sid, sinfo in STYLES.items():
            price = get_scaled_price(sinfo["base_price"], p["level"])
            status = "⭐ Đang trang bị" if curr == sid else ("✅ Đã sở hữu" if sid in owned else f"❌ Chưa sở hữu (Giá: ¥{price:,})")
            atk_p = f"+{int((sinfo['atk_mod']-1)*100)}%" if sinfo['atk_mod'] >= 1 else f"{int((sinfo['atk_mod']-1)*100)}%"
            hp_p = f"+{int((sinfo['hp_mod']-1)*100)}%" if sinfo['hp_mod'] >= 1 else f"{int((sinfo['hp_mod']-1)*100)}%"
            
            embed.add_field(
                name=f"[{RARITY_COLORS[sinfo['rarity']]}] {sinfo['name']} (`{sid}`)",
                value=f"Trạng thái: **{status}**\nChỉ số: ATK ({atk_p}) | HP ({hp_p})\n*{sinfo['desc']}*",
                inline=False
            )
        embed.set_footer(text="Dùng lệnh: !Tshop buy_style <mã_style> | !Tstyle unequip")
        return await ctx.send(embed=embed)

    elif cat in ["shop", "store"]:
        p = get_player(ctx.author.id)
        embed = discord.Embed(title="🛒 CỬA HÀNG VẬT PHẨM & STYLES", description="Giá cả thay đổi linh hoạt theo Level hiện tại của bạn.", color=discord.Color.green())
        
        box_price = get_scaled_price(2500, p["level"])
        style_summary = "\n".join([f"`{sid}` - {s['name']} : **¥{get_scaled_price(s['base_price'], p['level']):,}**" for sid, s in list(STYLES.items())[:5]])
        embed.add_field(name="🥊 MỘT SỐ UBG STYLES TIÊU BIỂU", value=style_summary + "\n*(Xem đầy đủ tại !Thelps style)*", inline=False)
        embed.add_field(name="🥤 VẬT PHẨM ĐẶC BIỆT", value=f"`stamina` - Sữa Stamina (¥300)\n`bento` - Hộp Bento (¥800)\n`mystery_box` - 🎁 Hộp Bí Ẩn Yên, EXP & Cơ hội nhận Code Siêu Hiếm (**¥{box_price:,}**)", inline=False)
        embed.set_footer(text="Dùng: !Tshop buy <mã> hoặc !Tshop buy_style <mã> hoặc !Qshop!")
        return await ctx.send(embed=embed)

    else:
        embed = discord.Embed(
            title="🥊 TRUNG TÂM LỆNH SYSTEM (!Thelps)",
            description="Chào bạn! Hệ thống lệnh phân loại đầy đủ tính năng RPG:",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="📂 **TRA CỨU & HỒ SƠ**",
            value=(
                "`!Thelps style` : Xem toàn bộ danh sách Styles & giá mua theo Level.\n"
                "`!Thelps shop` : Xem danh mục Cửa hàng.\n"
                "`!profile` : Thẻ thông tin võ sĩ, chỉ số, Level, Qpoint & Clan.\n"
                "`!Tinventory` : Kiểm tra túi đồ vật phẩm cá nhân."
            ),
            inline=False
        )

        embed.add_field(
            name="🎁 **HÀNG NGÀY, NHIỆM VỤ & CODE**",
            value=(
                "`!daily` : Nhận quà điểm danh hằng ngày.\n"
                "`!daily_quest` : Nhận & hoàn thành nhiệm vụ từ NPC An Nguyễn kiếm Qpoint.\n"
                "`!redeem <code>` : Nhập mã quà tặng đặc biệt (Hộp bí ẩn tỷ lệ 0.02%).\n"
                "`!Qshop` : Mở cửa hàng đổi thưởng bằng điểm Qpoint."
            ),
            inline=False
        )

        embed.add_field(
            name="⚔️ **CHIẾN ĐẤU & MÔ PHỎNG**",
            value=(
                "`!battle` : Đấu đường phố.\n"
                "`!Ttrain` : Vào chế độ tập luyện (Tăng EXP, giảm Yên).\n"
                "`!Tboss` : Khiêu chiến Boss thế giới (Level 5+).\n"
                "`!Tsimulator @user` : Mô phỏng thông số, style & kỹ năng của người chơi khác để chiến đấu (Phần thưởng nhỉnh hơn đấu thường).\n"
                "`!Tpvp @user <số_yen>` : Thách đấu PvP với người chơi khác."
            ),
            inline=False
        )

        embed.set_footer(text="Gõ !Thelps style hoặc !Thelps shop để tra cứu chi tiết!")
        await ctx.send(embed=embed)

# -------------------- COMMAND: REDEEM CODE --------------------
@bot.command(name="redeem")
async def redeem_command(ctx, code_str: str = None):
    if not code_str:
        return await ctx.send("⚠️ Vui lòng nhập mã code! Ví dụ: `!redeem BOX-ABC123`")
    
    code = code_str.strip().upper()
    p = get_player(ctx.author.id)
    uid = str(ctx.author.id)

    valid_dict = codes_data.get("valid_codes", {})
    used_records = codes_data.get("used_records", [])

    # Kiểm tra xem code có tồn tại không
    if code not in valid_dict:
        return await ctx.send("❌ Mã quà tặng không tồn tại hoặc đã hết hạn!")

    # Kiểm tra xem người dùng đã dùng code này chưa
    for record in used_records:
        if record["code"] == code and record["user_id"] == uid:
            return await ctx.send("⚠️ Bạn đã sử dụng mã này rồi! Mỗi code chỉ được nhập một lần duy nhất.")

    # Tiến hành trả thưởng (5M Yên, 25000 EXP)
    reward_yen = 5000000
    reward_exp = 25000

    p["yen"] += reward_yen
    p["exp"] += reward_exp
    leveled = check_level_up(p)

    # Đánh dấu code đã được sử dụng bởi user này
    used_records.append({"code": code, "user_id": uid, "time": datetime.utcnow().isoformat()})
    
    # Xóa code khỏi danh sách valid để nó chỉ nhập được đúng một lần duy nhất toàn hệ thống
    del valid_dict[code]
    save_json(CODES_DATA_PATH, codes_data)
    save_json(RPG_DATA_PATH, rpg_data)

    lvl_up_str = "\n⚡ **BẠN ĐÃ ĐẠT CẤP ĐỘ MỚI!**" if leveled else ""
    await ctx.send(f"🎉 **NHẬP CODE THÀNH CÔNG!**\n🎁 Phần thưởng nhận được:\n- 💰 **+¥5,000,000 Yên**\n- ⚡ **+25,000 EXP**{lvl_up_str}")

# -------------------- DAILY & NPC AN NGUYỄN QUESTS --------------------
@bot.command(name="daily")
async def daily_reward(ctx):
    p = get_player(ctx.author.id)
    now = datetime.utcnow()
    
    if p.get("last_daily"):
        last = datetime.fromisoformat(p["last_daily"])
        if now - last < timedelta(hours=24):
            remaining = timedelta(hours=24) - (now - last)
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            return await ctx.send(f"⏳ Bạn đã nhận quà hôm nay rồi! Hãy quay lại sau **{hours} giờ {minutes} phút**.")

    lvl = p["level"]
    yen_gift = int(2500 * (1 + (lvl - 1) * 0.3))
    exp_gift = int(300 * (1 + (lvl - 1) * 0.2))
    qp_gift = int(10 + lvl * 2)

    p["yen"] += yen_gift
    p["exp"] += exp_gift
    p["qpoint"] += qp_gift
    p["last_daily"] = now.isoformat()
    
    leveled = check_level_up(p)
    save_json(RPG_DATA_PATH, rpg_data)

    lvl_up_str = "\n⚡ **BẠN ĐÃ ĐẠT CẤP ĐỘ MỚI!**" if leveled else ""
    await ctx.send(
        f"🎁 **QUÀ ĐIỂM DANH HẰNG NGÀY (LEVEL {lvl})**\n"
        f"👤 NPC An Nguyễn trao thưởng:\n"
        f"💰 **+¥{yen_gift:,} Yên**\n"
        f"⚡ **+{exp_gift} EXP**\n"
        f"⭐ **+{qp_gift} Qpoint**{lvl_up_str}"
    )

@bot.command(name="daily_quest")
async def daily_quest(ctx, action: str = None):
    p = get_player(ctx.author.id)
    quest = p.get("daily_quest")

    if not action:
        if not quest:
            q_types = [
                {"type": "battle", "target": random.randint(3, 6), "desc": "Đấu thắng các trận đường phố (!battle)", "reward_yen": 2000, "reward_qp": 15, "reward_exp": 300},
                {"type": "train", "target": 1, "desc": "Hoàn thành 1 trận khiêu chiến Boss hoặc dạo phố", "reward_yen": 3500, "reward_qp": 25, "reward_exp": 500}
            ]
            chosen = random.choice(q_types)
            p["daily_quest"] = {"desc": chosen["desc"], "type": chosen["type"], "target": chosen["target"], "progress": 0, "yen": chosen["reward_yen"], "qp": chosen["reward_qp"], "exp": chosen["reward_exp"], "claimed": False}
            save_json(RPG_DATA_PATH, rpg_data)
            quest = p["daily_quest"]

        status = "✅ Đã hoàn thành (Gõ `!daily_quest claim` để nhận quà)" if quest["progress"] >= quest["target"] else f"⏳ Đang thực hiện ({quest['progress']}/{quest['target']})"
        return await ctx.send(
            f"📜 **NHIỆM VỤ TỪ NPC AN NGUYỄN**\n"
            f"🎯 **Nội dung**: {quest['desc']}\n"
            f"📊 **Trạng thái**: {status}\n"
            f"🎁 **Phần thưởng**: ¥{quest['yen']:,} Yên | {quest['exp']} EXP | {quest['qp']} Qpoint"
        )

    if action.lower() == "claim":
        if not quest: return await ctx.send("Bạn chưa nhận nhiệm vụ nào! Gõ `!daily_quest` để nhận.")
        if quest["progress"] < quest["target"]: return await ctx.send("⚠️ Bạn chưa hoàn thành mục tiêu nhiệm vụ!")
        if quest.get("claimed", False): return await ctx.send("⚠️ Bạn đã nhận thưởng nhiệm vụ này rồi!")

        lvl_scale = 1 + (p["level"] - 1) * 0.2
        y_rew = int(quest["yen"] * lvl_scale)
        e_rew = int(quest["exp"] * lvl_scale)
        q_rew = int(quest["qp"] * lvl_scale)

        p["yen"] += y_rew
        p["exp"] += e_rew
        p["qpoint"] += q_rew
        quest["claimed"] = True
        
        check_level_up(p)
        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send(f"🎉 **NHẬN THƯỞNG THÀNH CÔNG!** Nhận ¥{y_rew:,} Yên, {e_rew} EXP và ⭐ {q_rew} Qpoint từ NPC An Nguyễn.")

# -------------------- ADVANCED BATTLE ENGINE (LEVEL SCALING, TRAINING & SIMULATOR) --------------------
async def run_battle_engine(ctx, enemy_data, is_boss=False, is_training=False, custom_skills=None):
    p = get_player(ctx.author.id)

    if p.get("in_battle", False):
        return await ctx.send("⚠️ Bạn đang ở trong trận đấu!")

    p["in_battle"] = True
    save_json(RPG_DATA_PATH, rpg_data)

    try:
        c_name, _ = get_player_clan(ctx.author.id)

        scale = 1 + (p["level"] - 1) * 0.35
        e_name = enemy_data["name"]
        e_hp = int(enemy_data["hp"] * scale)
        e_max_hp = e_hp
        e_atk = int(enemy_data["atk"] * scale)
        
        base_exp = int(enemy_data["exp"] * (1 + (p["level"] - 1) * 0.2))
        base_yen = int(enemy_data["yen"] * (1 + (p["level"] - 1) * 0.25))

        # Điều chỉnh phần thưởng nếu ở chế độ Tập Luyện hoặc Mô Phỏng
        if is_training:
            exp_reward = int(base_exp * 1.5)
            yen_reward = int(base_yen * 0.4)
        elif custom_skills is not None:  # Chế độ mô phỏng (!Tsimulator) thưởng nhỉnh hơn đấu thường khoảng 20%
            exp_reward = int(base_exp * 1.2)
            yen_reward = int(base_yen * 1.2)
        else:
            exp_reward = base_exp
            yen_reward = base_yen

        st_id = p.get("equipped_style")
        st_mod_atk, st_mod_hp = (STYLES[st_id]["atk_mod"], STYLES[st_id]["hp_mod"]) if st_id and st_id in STYLES else (1.0, 1.0)

        p_hp_max = int(p["hp_max"] * st_mod_hp)
        p_hp = p_hp_max
        e_mp_max = 50
        e_mp = 50
        p_mp_max = p["mp_max"]
        p_mp = p_mp_max
        
        clan_bonus = 1.15 if c_name else 1.0
        base_atk = int(p["atk"] * st_mod_atk * clan_bonus)

        eq = STYLES[st_id]["skills"] if st_id and st_id in STYLES else p.get("equipped_skills", [None, None, None])

        active_menu = {"1": "👊 Đánh thường", "2": "🛡️ Phòng thủ"}
        skill_mapping = {}

        opt_idx = 3
        for sid in eq:
            if sid and sid in SKILL_TREE:
                sinfo = SKILL_TREE[sid]
                active_menu[str(opt_idx)] = f"⚡ {sinfo['name']} ({sinfo.get('mp_cost', 0)} MP)"
                skill_mapping[str(opt_idx)] = sid
                opt_idx += 1

        valid_choices = [str(k) for k in active_menu.keys()]

        def check_msg(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content in valid_choices

        def battle_status(log_msg=""):
            style_str = f" [{STYLES[st_id]['name']}]" if st_id else ""
            mode_title = " (🏋️ TẬP LUYỆN)" if is_training else (" (🤖 MÔ PHỎNG TSLATOR)" if custom_skills is not None else "")
            embed = discord.Embed(
                title=f"🥊 {ctx.author.display_name}{style_str} (Lv.{p['level']}){mode_title}  VS  {e_name} (Lv.{p['level']})", 
                color=discord.Color.blue() if is_training else (discord.Color.purple() if custom_skills is not None else discord.Color.orange())
            )

            p_bar_hp = make_bar(p_hp, p_hp_max, 8, "🟩", "⬛")
            p_bar_mp = make_bar(p_mp, p_mp_max, 8, "🟦", "⬛")
            e_bar_hp = make_bar(e_hp, e_max_hp, 8, "🟥", "⬛")

            p_info = f"❤️ **HP**: {p_hp}/{p_hp_max}\n{p_bar_hp}\n🧪 **MP**: {p_mp}/{p_mp_max}\n{p_bar_mp}\n⚔️ **ATK**: `{base_atk}`"
            e_info = f"❤️ **HP**: {e_hp}/{e_max_hp}\n{e_bar_hp}\n\n⚔️ **ATK**: `{e_atk}`"

            embed.add_field(name=f"🔵 {ctx.author.display_name}", value=p_info, inline=True)
            embed.add_field(name=f"🔴 {e_name}", value=e_info, inline=True)
            
            cmd_text = "\n".join([f"`{k}` : {v}" for k, v in active_menu.items()])
            embed.add_field(name="🎮 LỰA CHỌN KỸ NĂNG", value=cmd_text, inline=False)
            if log_msg: embed.add_field(name="📜 DIỄN BIẾN TRẬN ĐẤU", value=f"> {log_msg}", inline=False)
            return embed

        status_msg = await ctx.send(embed=battle_status("Bắt đầu giao tranh!"))

        while p_hp > 0 and e_hp > 0:
            try:
                msg = await bot.wait_for("message", timeout=30.0, check=check_msg)
                action = msg.content
                try: await msg.delete()
                except Exception: pass
                
                p_action_log = ""
                is_defending = False

                if action == "1":
                    dmg = random.randint(base_atk - 3, base_atk + 5)
                    e_hp -= dmg
                    p_action_log = f"Tung đòn đấm thường gây **{dmg}** sát thương!"
                elif action == "2":
                    is_defending = True
                    p_action_log = "🛡️ Giơ giáp Phòng Thủ (Giảm 50% sát thương nhận vào)!"
                else:
                    sid = skill_mapping[action]
                    sinfo = SKILL_TREE[sid]
                    req_mp = sinfo.get("mp_cost", 0)

                    if p_mp < req_mp:
                        p_action_log = f"❌ Không đủ MP! (Cần {req_mp} MP)."
                    else:
                        p_mp -= req_mp
                        dmg = int(base_atk * 2.0)
                        e_hp -= dmg
                        p_action_log = f"💥 Dùng **{sinfo['name']}** gây **{dmg}** sát thương!"

                if e_hp <= 0:
                    e_hp = 0
                    p["exp"] += exp_reward
                    p["yen"] += yen_reward
                    
                    q = p.get("daily_quest")
                    if q and not q.get("claimed", False) and q["type"] in ["battle", "train"]:
                        q["progress"] = min(q["target"], q["progress"] + 1)

                    leveled = check_level_up(p)
                    lvl_up_str = "\n⚡ **BẠN ĐÃ LÊN CẤP ĐỘ MỚI!**" if leveled else ""

                    await status_msg.edit(embed=battle_status(f"🎉 CHIẾN THẮNG! Nhận {exp_reward} EXP và ¥{yen_reward:,}{lvl_up_str}"))
                    break

                # Lượt phản công của Enemy / Mô phỏng
                e_action_desc = ""
                e_dmg = 0
                
                # Nếu là chế độ mô phỏng (!Tsimulator), đối thủ bot có thể thỉnh thoảng dùng skill của style người được mô phỏng
                if custom_skills and len(custom_skills) > 0 and e_mp >= 15 and random.random() < 0.35:
                    e_mp -= 15
                    chosen_skill_id = random.choice(custom_skills)
                    skill_name = SKILL_TREE.get(chosen_skill_id, {}).get("name", "Tuyệt kỹ đặc biệt")
                    e_dmg = int(e_atk * 1.8)
                    if is_defending: e_dmg = int(e_dmg * 0.5)
                    e_action_desc = f"🤖 Bản mô phỏng dùng **{skill_name}**"
                else:
                    e_dmg = random.randint(e_atk - 2, e_atk + 6)
                    if is_defending: e_dmg = int(e_dmg * 0.5)
                    e_action_desc = f"{e_name} đánh trả"

                p_hp -= e_dmg

                if p_hp <= 0:
                    p_hp = 0
                    consolation_exp = max(1, int(exp_reward * 0.15))
                    consolation_yen = max(1, int(yen_reward * 0.15))
                    p["exp"] += consolation_exp
                    p["yen"] += consolation_yen
                    leveled = check_level_up(p)
                    lvl_up_str = "\n⚡ **BẠN ĐÃ LÊN CẤP ĐỘ MỚI!**" if leveled else ""

                    await status_msg.edit(embed=battle_status(f"💀 THẤT BẠI trước {e_name}... Hỗ trợ an ủi: **+{consolation_exp} EXP** và **+¥{consolation_yen:,} Yên** (15%).{lvl_up_str}"))
                    break

                await status_msg.edit(embed=battle_status(f"{p_action_log}\n{e_action_desc} gây **{e_dmg}** sát thương!"))

            except asyncio.TimeoutError:
                await ctx.send("Quá thời gian lựa chọn!")
                break

    finally:
        p["in_battle"] = False
        save_json(RPG_DATA_PATH, rpg_data)

# -------------------- COMMAND: TSIMULATOR --------------------
@bot.command(name="Tsimulator")
async def tsimulator_command(ctx, target_member: discord.Member = None):
    if not target_member:
        return await ctx.send("⚠️ Vui lòng tag người chơi muốn mô phỏng! Ví dụ: `!Tsimulator @user`")
    if target_member.bot:
        return await ctx.send("⚠️ Không thể mô phỏng dữ liệu của Bot!")

    target_p = get_player(target_member.id)
    target_style_id = target_p.get("equipped_style")
    
    # Lấy thông tin style và skill của người mục tiêu
    if target_style_id and target_style_id in STYLES:
        t_style_name = STYLES[target_style_id]["name"]
        t_skills = STYLES[target_style_id]["skills"]
        t_atk_mod = STYLES[target_style_id]["atk_mod"]
        t_hp_mod = STYLES[target_style_id]["hp_mod"]
    else:
        t_style_name = "Basic (Không trang bị Style)"
        t_skills = ["basic_jab", "heal"]
        t_atk_mod = 1.0
        t_hp_mod = 1.0

    simulated_enemy = {
        "name": f"Bản Mô Phỏng ({target_member.display_name})",
        "hp": int(target_p["hp_max"] * t_hp_mod),
        "atk": int(target_p["atk"] * t_atk_mod),
        "exp": 180,
        "yen": 1200
    }

    await ctx.send(
        f"🛡️ **KHỞI TẠO CHẾ ĐỘ MÔ PHỎNG (!TSIMULATOR)**\n"
        f"Đã sao chép thành công thực thể từ **{target_member.display_name}**:\n"
        f"- **Style**: {t_style_name}\n"
        f"- **Kỹ năng chiến đấu**: {', '.join([SKILL_TREE[s]['name'] for s in t_skills if s in SKILL_TREE])}\n"
        f"*Trận đấu mô phỏng chính thức bắt đầu với phần thưởng ưu đãi +20%!*"
    )

    await run_battle_engine(ctx, simulated_enemy, is_boss=False, is_training=False, custom_skills=t_skills)

# -------------------- SHOP, QSHOP & USABLE ITEMS --------------------
@bot.command(name="Tshop")
async def shop_command(ctx, action: str = None, item_code: str = None):
    p = get_player(ctx.author.id)

    if not action:
        return await ctx.send("Vui lòng dùng `!Thelps shop` để xem danh sách mặt hàng, hoặc `!Tshop buy <mã>` / `!Tshop buy_style <mã>`!")

    act = action.lower()
    if act == "buy":
        if not item_code: return await ctx.send("Nhập mã vật phẩm muốn mua! Ví dụ: `!Tshop buy mystery_box`")
        code = item_code.lower()

        mystery_box_price = get_scaled_price(2500, p["level"])
        prices = {
            "stamina": 300,
            "bento": 800,
            "mystery_box": mystery_box_price
        }

        if code not in prices: return await ctx.send("Mã vật phẩm không tồn tại trong cửa hàng Yên!")
        price = prices[code]

        if p["yen"] < price:
            return await ctx.send(f"❌ Không đủ Yên! Cần **¥{price:,} Yên**.")

        p["yen"] -= price
        p["inventory"][code] = p["inventory"].get(code, 0) + 1
        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send(f"🛍️ Mua thành công **1x {code}** với giá ¥{price:,} Yên!")

    elif act == "buy_style":
        if not item_code: return await ctx.send("Nhập mã style muốn mua! Ví dụ: `!Tshop buy_style out_boxer`")
        sid = item_code.lower()
        if sid not in STYLES: return await ctx.send("Mã style không tồn tại!")
        if sid in p.get("owned_styles", []): return await ctx.send("Bạn đã sở hữu style này rồi!")
        
        price = get_scaled_price(STYLES[sid]["base_price"], p["level"])
        if p["yen"] < price:
            return await ctx.send(f"❌ Không đủ Yên! Cần **¥{price:,} Yên** (Giá đã tăng theo Level {p['level']}).")

        p["yen"] -= price
        p["owned_styles"].append(sid)
        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send(f"🎉 Mua thành công style **{STYLES[sid]['name']}**!")

@bot.command(name="Qshop")
async def qshop_command(ctx):
    p = get_player(ctx.author.id)
    embed = discord.Embed(
        title="⭐ CỬA HÀNG ĐIỂM NHIỆM VỤ (QSHOP)",
        description=f"Điểm Qpoint hiện có của bạn: **{p['qpoint']} ⭐**\nDùng lệnh `!Qbuy <mã>` để đổi quà:",
        color=discord.Color.purple()
    )
    embed.add_field(
        name="🎁 MẶT HÀNG ĐỔI THƯỞNG",
        value=(
            "`spin_ticket` (50 Qpoint) : Nhận 1x Vé Vòng Quay Ngẫu Nhiên.\n"
            "`mystery_box` (80 Qpoint) : Nhận 1x Hộp Bí Ẩn Yên & EXP.\n"
            "`huge_yen` (120 Qpoint) : Đổi nhận ngay ¥50,000 Yên."
        ),
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command(name="Qbuy")
async def qbuy_command(ctx, item_code: str = None):
    if not item_code: return await ctx.send("Nhập mã vật phẩm Qshop muốn mua: `!Qbuy spin_ticket`")
    p = get_player(ctx.author.id)
    code = item_code.lower()

    costs = {"spin_ticket": 50, "mystery_box": 80, "huge_yen": 120}
    if code not in costs: return await ctx.send("Mã mặt hàng Qshop không hợp lệ!")

    cost = costs[code]
    if p["qpoint"] < cost:
        return await ctx.send(f"❌ Không đủ Qpoint! Bạn cần **{cost} ⭐** (Hiện có: {p['qpoint']} ⭐).")

    p["qpoint"] -= cost
    if code == "spin_ticket":
        p["inventory"]["lucky_spin"] = p["inventory"].get("lucky_spin", 0) + 1
        res = "1x Vé Vòng Quay Ngẫu Nhiên"
    elif code == "mystery_box":
        p["inventory"]["mystery_box"] = p["inventory"].get("mystery_box", 0) + 1
        res = "1x Hộp Bí Ẩn"
    else:
        p["yen"] += 50000
        res = "¥50,000 Yên"

    save_json(RPG_DATA_PATH, rpg_data)
    await ctx.send(f"🎉 Đổi thành công **{res}** bằng điểm Qpoint!")

@bot.command(name="Tuse")
async def use_item(ctx, item_code: str = None):
    if not item_code: return await ctx.send("Nhập mã vật phẩm muốn dùng: `!Tuse mystery_box` hoặc `!Tuse spin`")

    p = get_player(ctx.author.id)
    code = item_code.lower()
    if code in ["spin", "vongquay"]: code = "lucky_spin"

    inv = p.get("inventory", {})
    if inv.get(code, 0) <= 0: return await ctx.send("⚠️ Bạn không có vật phẩm này trong túi đồ!")

    inv[code] -= 1

    if code == "mystery_box":
        lvl = p["level"]
        yen_drop = random.randint(500, 2000) * lvl
        exp_drop = random.randint(100, 400) * lvl
        p["yen"] += yen_drop
        p["exp"] += exp_drop
        
        # ----------------- TỈ LỆ 0.02% XUẤT HIỆN CODE SIÊU HIẾM -----------------
        code_spawned_str = ""
        chance = random.uniform(0, 100)
        if chance <= 0.02:  # Tỉ lệ 0.02%
            new_code = f"BOX-{uuid.uuid4().hex[:6].upper()}"
            codes_data["valid_codes"][new_code] = {"reward_yen": 5000000, "reward_exp": 25000}
            save_json(CODES_DATA_PATH, codes_data)
            code_spawned_str = f"\n\n🚨 **QUÁ MAY MẮN!** Hộp bí ẩn đã rơi ra một **MÃ CODE ĐẶC BIỆT**: `{new_code}`\n*(Phần thưởng: 5,000,000 Yên & 25,000 EXP. Code chỉ nhập được một lần duy nhất qua lệnh `!redeem <code>`)*"

        leveled = check_level_up(p)
        save_json(RPG_DATA_PATH, rpg_data)
        
        lvl_str = "\n⚡ **BẠN ĐÃ LÊN CẤP!**" if leveled else ""
        await ctx.send(f"🎁 **MỞ HỘP BÍ ẨN (Level {lvl})**\n🎉 Bạn nhận được: **¥{yen_drop:,} Yên** và **{exp_drop} EXP**!{lvl_str}{code_spawned_str}")

    elif code == "lucky_spin":
        val = random.randint(3000, 15000) * p["level"]
        p["yen"] += val
        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send(f"🎰 **VÒNG QUAY NGẪU NHIÊN**\n🎉 Bạn nhận được: **¥{val:,} Yên**!")
    else:
        await ctx.send("Vật phẩm không thể sử dụng trực tiếp lúc này.")

# -------------------- COMMAND: TINVENTORY --------------------
@bot.command(name="Tinventory")
async def tinventory(ctx):
    p = get_player(ctx.author.id)
    inv = p.get("inventory", {})
    
    embed = discord.Embed(title=f"🎒 TÚI ĐỒ CỦA {ctx.author.display_name.upper()}", color=discord.Color.blue())
    
    if not inv or all(qty <= 0 for qty in inv.values()):
        embed.description = "Túi đồ của bạn hiện đang trống rỗng!"
    else:
        items_desc = ""
        item_names = {
            "mystery_box": "🎁 Hộp Bí Ẩn",
            "lucky_spin": "🎟️ Vé Vòng Quay",
            "stamina": "🥤 Sữa Stamina",
            "bento": "🍱 Hộp Bento"
        }
        for k, v in inv.items():
            if v > 0:
                name = item_names.get(k, k.capitalize())
                items_desc += f"- **{name}** (`{k}`) : `x{v}`\n"
        embed.add_field(name="📦 VẬT PHẨM SỞ HỮU", value=items_desc, inline=False)
        
    embed.set_footer(text="Dùng lệnh !Tuse <mã_vật_phẩm> để sử dụng!")
    await ctx.send(embed=embed)

# -------------------- COMMAND: TSTYLE --------------------
@bot.command(name="Tstyle")
async def tstyle_command(ctx, action: str = None, style_id: str = None):
    p = get_player(ctx.author.id)
    if not action:
        return await ctx.send("Dùng lệnh: `!Tstyle equip <mã_style>` hoặc `!Tstyle unequip`")

    act = action.lower()
    if act == "equip":
        if not style_id: return await ctx.send("Nhập mã style muốn trang bị!")
        sid = style_id.lower()
        if sid not in STYLES: return await ctx.send("Mã style không tồn tại!")
        if sid not in p.get("owned_styles", []): return await ctx.send("⚠️ Bạn chưa sở hữu style này! Hãy mua bằng `!Tshop buy_style <mã>`.")
        
        p["equipped_style"] = sid
        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send(f"⭐ Đã trang bị thành công UBG Style: **{STYLES[sid]['name']}**!")

    elif act == "unequip":
        p["equipped_style"] = None
        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send("🛡️ Đã tháo Style thành công.")

# -------------------- COMMAND: TPVV (PVP) --------------------
@bot.command(name="Tpvp")
async def tpvp_command(ctx, opponent: discord.Member = None, bet_yen: int = 0):
    if not opponent:
        return await ctx.send("⚠️ Vui lòng tag người muốn thách đấu! Ví dụ: `!Tpvp @user 5000`")
    if opponent.bot:
        return await ctx.send("⚠️ Không thể đấu với Bot!")
    if opponent == ctx.author:
        return await ctx.send("⚠️ Bạn không thể tự đấu với chính mình!")

    p1 = get_player(ctx.author.id)
    p2 = get_player(opponent.id)

    if bet_yen < 0:
        return await ctx.send("⚠️ Số Yên cược không hợp lệ!")
    if p1["yen"] < bet_yen:
        return await ctx.send(f"❌ Bạn không đủ ¥{bet_yen:,} Yên để cược!")
    if p2["yen"] < bet_yen:
        return await ctx.send(f"❌ Đối thủ không đủ ¥{bet_yen:,} Yên để nhận cược!")

    confirm_msg = await ctx.send(f"⚔️ {opponent.mention}, bạn nhận được lời thách đấu PvP từ **{ctx.author.display_name}** với mức cược **¥{bet_yen:,} Yên**!\nThả cảm xúc 👍 vào tin nhắn này trong 30 giây để chấp nhận chiến đấu!")
    await confirm_msg.add_reaction("👍")

    def check_reaction(reaction, user):
        return user == opponent and str(reaction.emoji) == "👍" and reaction.message.id == confirm_msg.id

    try:
        await bot.wait_for("reaction_add", timeout=30.0, check=check_reaction)
    except asyncio.TimeoutError:
        return await ctx.send("⏳ Lời thách đấu PvP đã hết hạn do đối thủ không phản hồi.")

    p1["yen"] -= bet_yen
    p2["yen"] -= bet_yen
    save_json(RPG_DATA_PATH, rpg_data)

    st1 = p1.get("equipped_style")
    st2 = p2.get("equipped_style")
    mod1 = STYLES[st1]["atk_mod"] if st1 and st1 in STYLES else 1.0
    mod2 = STYLES[st2]["atk_mod"] if st2 and st2 in STYLES else 1.0

    hp1 = int(p1["hp_max"] * (STYLES[st1]["hp_mod"] if st1 and st1 in STYLES else 1.0))
    hp2 = int(p2["hp_max"] * (STYLES[st2]["hp_mod"] if st2 and st2 in STYLES else 1.0))
    atk1 = int(p1["atk"] * mod1)
    atk2 = int(p2["atk"] * mod2)

    battle_log = f"🥊 **TRẬN CHIẾN PVP GIỮA {ctx.author.display_name.upper()} & {opponent.display_name.upper()}**\n\n"
    
    while hp1 > 0 and hp2 > 0:
        dmg1 = random.randint(atk1 - 3, atk1 + 5)
        hp2 -= dmg1
        battle_log += f"🗡️ {ctx.author.display_name} tấn công gây **{dmg1}** sát thương (Còn lại: {max(0, hp2)} HP)\n"
        if hp2 <= 0: break

        dmg2 = random.randint(atk2 - 3, atk2 + 5)
        hp1 -= dmg2
        battle_log += f"🛡️ {opponent.display_name} phản công gây **{dmg2}** sát thương (Còn lại: {max(0, hp1)} HP)\n"

    if hp1 > hp2:
        winner, loser = ctx.author, opponent
        p1["yen"] += bet_yen * 2
        battle_log += f"\n🏆 **VINH QUANG THUỘC VỀ {winner.display_name}!** Nhận phần thưởng cược ¥{bet_yen * 2:,} Yên."
    else:
        winner, loser = opponent, ctx.author
        p2["yen"] += bet_yen * 2
        battle_log += f"\n🏆 **VINH QUANG THUỘC VỀ {winner.display_name}!** Nhận phần thưởng cược ¥{bet_yen * 2:,} Yên."

    save_json(RPG_DATA_PATH, rpg_data)
    await ctx.send(battle_log)

# -------------------- COMMAND: PROFILE --------------------
@bot.command(name="profile")
async def profile(ctx):
    p = get_player(ctx.author.id)
    c_name, _ = get_player_clan(ctx.author.id)
    
    st_id = p.get("equipped_style")
    if st_id and st_id in STYLES:
        st = STYLES[st_id]
        style_str = f"[{RARITY_COLORS[st['rarity']]}] **{st['name']}**"
    else:
        style_str = "❌ Chưa trang bị"

    clan_str = f"🏰 **{c_name}** (+15% ATK)" if c_name else "❌ Chưa tham gia Clan"
    inv = p.get("inventory", {})

    embed = discord.Embed(title=f"💳 THẺ VÕ SĨ: {ctx.author.display_name.upper()}", color=discord.Color.gold())
    embed.set_thumbnail(url=ctx.author.display_avatar.url)

    embed.add_field(
        name="📊 **THÔNG TIN CƠ BẢN**",
        value=f"⭐ **Cấp độ**: Level `{p['level']}`\n⚡ **EXP**: `{p['exp']}/{p['level']*300}`\n💰 **Tài sản**: `¥{p['yen']:,}` Yên\n⭐ **Qpoint**: `{p['qpoint']}` điểm",
        inline=False
    )

    embed.add_field(
        name="🎒 **TÚI ĐỒ VẬT PHẨM**",
        value=f"🎁 **Hộp Bí Ẩn**: `{inv.get('mystery_box', 0)}`\n🎟️ **Vé Spin**: `{inv.get('lucky_spin', 0)}`\n🥤 **Stamina / Bento**: `{inv.get('stamina', 0)} / {inv.get('bento', 0)}`",
        inline=True
    )

    embed.add_field(
        name="🛡️ **TRANG BỊ & TỔ CHỨC**",
        value=f"🥊 **UBG Style**: {style_str}\n{clan_str}",
        inline=True
    )

    embed.set_footer(text="Dùng lệnh !Thelps để xem danh sách lệnh hoặc !Tinventory xem túi đồ!")
    await ctx.send(embed=embed)

# -------------------- COMMANDS CHIẾN ĐẤU & TẬP LUYỆN --------------------
@bot.command(name="battle")
async def battle_command(ctx):
    enemy = random.choice(REGULAR_ENEMIES)
    await run_battle_engine(ctx, enemy, is_boss=False, is_training=False)

@bot.command(name="Ttrain")
async def train_command(ctx):
    enemy = random.choice(REGULAR_ENEMIES)
    await ctx.send("🏋️ Bạn bước vào phòng tập thể lực khắc nghiệt! (Tăng mạnh lượng EXP nhận được, giảm tiền thưởng Yên).")
    await run_battle_engine(ctx, enemy, is_boss=False, is_training=True)

@bot.command(name="Tboss")
async def boss_command(ctx):
    p = get_player(ctx.author.id)
    if p["level"] < 5: return await ctx.send("⚠️ Cần đạt Level 5 trở lên để khiêu chiến Boss!")
    boss = random.choice(BOSSES)
    await run_battle_engine(ctx, boss, is_boss=True, is_training=False)

# -------------------- KHỞI ĐỘNG --------------------
@bot.event
async def on_message(message):
    if message.author.bot: return
    await bot.process_commands(message)

@bot.event
async def on_ready():
    logger.info(f"✅ Bot đã trực tuyến: {bot.user.name}")

if __name__ == "__main__":
    keep_alive()
    if DISCORD_TOKEN: bot.run(DISCORD_TOKEN)
