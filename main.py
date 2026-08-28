# -------------------- CẤU HÌNH & LOGGING --------------------
import os
import logging
import asyncio
import threading
import json
import random
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

# -------------------- LƯU TRỮ DỮ LIỆU MODERATION, RPG & CLAN --------------------
DATA_PATH = "moderation_data.json"
RPG_DATA_PATH = "rpg_data.json"
CLAN_DATA_PATH = "clan_data.json"

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
            "trait": None,
            "quest": None,
            "in_battle": False,
            "spin_counter": random.randint(1, 3),
            "owned_styles": [],
            "equipped_style": None
        }
        save_json(RPG_DATA_PATH, rpg_data)
    
    player = rpg_data[uid]
    fields = {
        "qpoint": 0, "sp": 0, "skills": [], "equipped_skills": [None, None, None],
        "inventory": {}, "last_daily": None, "trait": None, "quest": None,
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

# -------------------- SKILL TREE & UNTITLED BOXING GAME STYLES --------------------
SKILL_TREE = {
    "heal": {"name": "Hồi Xuân", "cost": 2, "type": "active", "mp_cost": 20, "desc": "Hồi 40 HP ngay lập tức."},
    "crossover": {"name": "Tuyệt Kỹ Crossover", "cost": 3, "type": "active", "mp_cost": 15, "desc": "Gây 180%-250% sát thương ATK."},
    "rest": {"name": "Rest (Tĩnh Tâm)", "cost": 2, "type": "active", "mp_cost": 0, "desc": "Hồi 15 MP trong trận."},
    
    # Skills cố định tương ứng theo các Style
    "basic_jab": {"name": "Basic Jab", "cost": 0, "type": "active", "mp_cost": 10, "desc": "Cú đấm cơ bản ổn định."},
    "long_guard_counter": {"name": "Long Guard Counter", "cost": 0, "type": "active", "mp_cost": 15, "desc": "Phòng thủ phản đòn tầm xa."},
    "outbox_swift": {"name": "Swift Footwork", "cost": 0, "type": "active", "mp_cost": 12, "desc": "Di chuyển né tránh và phản công nhanh."},
    "hitman_flicker": {"name": "Flicker Jab", "cost": 0, "type": "active", "mp_cost": 15, "desc": "Đòn Jab lắt léo tầm xa khó đoán."},
    "challenger_rush": {"name": "Challenger Barrage", "cost": 0, "type": "active", "mp_cost": 20, "desc": "Chuỗi đòn liên hoàn dồn ép đối thủ."},
    "smash_heavy": {"name": "Demolishing Smash", "cost": 0, "type": "active", "mp_cost": 25, "desc": "Cú đấm móc trời giáng cực mạnh."},
    "chronos_delay": {"name": "Time-Lag Punch", "cost": 0, "type": "active", "mp_cost": 30, "desc": "Đòn đánh làm lệch nhịp độ đối thủ."},
    "freedom_flash": {"name": "Unpredictable Flash", "cost": 0, "type": "active", "mp_cost": 30, "desc": "Bay nhảy tự do tung đòn bất định."},
    "slugger_power": {"name": "Devastating Slugger Hook", "cost": 0, "type": "active", "mp_cost": 35, "desc": "Cú đấm uy lực hủy diệt phòng thủ."},
    "ippo_dempsey": {"name": "Dempsey Roll", "cost": 0, "type": "active", "mp_cost": 40, "desc": "Vòng xoáy số 8 huyền thoại kết liễu kẻ thù."}
}

STYLES = {
    # COMMON
    "basic": {
        "name": "Basic", "rarity": "common", "price": 1000,
        "atk_mod": 1.0, "hp_mod": 1.0,
        "skills": ["basic_jab", "heal", "rest"],
        "desc": "Phong cách cơ bản nhất, không có điểm yếu cũng không quá nổi bật."
    },
    "long_guard": {
        "name": "Long Guard", "rarity": "common", "price": 1200,
        "atk_mod": 1.05, "hp_mod": 1.05,
        "skills": ["long_guard_counter", "heal", "rest"],
        "desc": "Tư thế thủ cao giúp tăng nhẹ khả năng chống đỡ."
    },
    # RARE
    "out_boxer": {
        "name": "Out-Boxer", "rarity": "rare", "price": 2500,
        "atk_mod": 1.10, "hp_mod": 0.95,
        "skills": ["outbox_swift", "crossover", "rest"],
        "desc": "Chuyên gia giữ khoảng cách và tung đòn cấu máu nhanh gọn."
    },
    "hitman": {
        "name": "Hitman", "rarity": "rare", "price": 3000,
        "atk_mod": 1.15, "hp_mod": 0.95,
        "skills": ["hitman_flicker", "crossover", "heal"],
        "desc": "Góc đánh thấp hiểm hóc với những cú Flicker Jab cấu rỉa."
    },
    # EPIC
    "challenger": {
        "name": "Challenger", "rarity": "epic", "price": 6000,
        "atk_mod": 1.20, "hp_mod": 1.10,
        "skills": ["challenger_rush", "crossover", "rest"],
        "desc": "Ý chí chiến đấu kiên cường với chuỗi combo dồn dập."
    },
    "smash": {
        "name": "Smash", "rarity": "epic", "price": 7500,
        "atk_mod": 1.25, "hp_mod": 1.05,
        "skills": ["smash_heavy", "crossover", "heal"],
        "desc": "Sở hữu cú đấm Smash từ dưới lên gây tổn thương diện rộng."
    },
    # LEGEND
    "chronos": {
        "name": "Chronos", "rarity": "legend", "price": 15000,
        "atk_mod": 1.35, "hp_mod": 1.20,
        "skills": ["chronos_delay", "crossover", "heal"],
        "desc": "Kiểm soát nhịp độ trận đấu bằng các đòn đánh lệch nhịp."
    },
    "freedom": {
        "name": "Freedom", "rarity": "legend", "price": 18000,
        "atk_mod": 1.40, "hp_mod": 1.15,
        "skills": ["freedom_flash", "crossover", "rest"],
        "desc": "Lối đánh linh hoạt và phóng khoáng không thể đoán trước."
    },
    # MYTH
    "slugger": {
        "name": "Slugger", "rarity": "myth", "price": 35000,
        "atk_mod": 1.50, "hp_mod": 1.30,
        "skills": ["slugger_power", "crossover", "heal"],
        "desc": "Sức mạnh tối thượng chuyên ép góc và phá vỡ mọi khối phòng thủ."
    },
    "ippo": {
        "name": "Ippo", "rarity": "myth", "price": 50000,
        "atk_mod": 1.60, "hp_mod": 1.40,
        "skills": ["ippo_dempsey", "crossover", "heal"],
        "desc": "Tuyệt kỹ Dempsey Roll huyền thoại mang lại sức sát thương kinh hoàng."
    }
}

RARITY_COLORS = {
    "common": "⚪ Common",
    "rare": "🔵 Rare",
    "epic": "🟣 Epic",
    "legend": "🟡 Legend",
    "myth": "🔴 Myth"
}

BOSSES = [
    {"name": "Superman (DC)", "hp": 950, "atk": 75, "exp": 1200, "yen": 35000, "skill_name": "❄️ Hơi Thở Băng Giá", "skill_type": "freeze"},
    {"name": "Sentry (Marvel)", "hp": 1050, "atk": 85, "exp": 1500, "yen": 42000, "skill_name": "☀️ Sức Mạnh 1 Triệu Mặt Trời", "skill_type": "enrage"}
]

ITEMS = {
    "stamina": {"name": "Hộp sữa Stamina", "price": 300, "desc": "Hồi 40 HP.", "type": "heal_hp", "value": 40},
    "bento": {"name": "Hộp Bento Kamurocho", "price": 800, "desc": "Hồi 100 HP.", "type": "heal_hp", "value": 100},
    "lucky_spin": {"name": "🎟️ Vòng Quay Ngẫu Nhiên", "price": 0, "desc": "Quay nhận ngẫu nhiên Yên, Qpoint, EXP hoặc UBG Style!", "type": "spin", "value": 0}
}

REGULAR_ENEMIES = [
    {"name": "Quickbullet", "hp": 110, "atk": 15, "exp": 55, "yen": 1100},
    {"name": "Gã Trộm Đồ Lặt Vặt Hẻm Nhỏ", "hp": 70, "atk": 8, "exp": 25, "yen": 400},
    {"name": "Sát Thủ Passione (JoJo Part 5)", "hp": 130, "atk": 16, "exp": 60, "yen": 1200}
]

# -------------------- ADVANCED RPG BATTLE ENGINE --------------------
async def run_battle_engine(ctx, enemy_data, is_boss=False):
    p = get_player(ctx.author.id)

    if p.get("in_battle", False):
        return await ctx.send("⚠️ Bạn đang ở trong trận đấu! Không thể dùng lệnh battle/boss/pvp lúc này.")

    p["in_battle"] = True
    save_json(RPG_DATA_PATH, rpg_data)

    try:
        c_name, _ = get_player_clan(ctx.author.id)

        scale = 1 + (p["level"] - 1) * 0.18
        e_name = enemy_data["name"]
        e_hp = int(enemy_data["hp"] * scale)
        e_max_hp = e_hp
        e_atk = int(enemy_data["atk"] * scale)
        
        exp_reward = int(enemy_data["exp"] * (1 + (p["level"] - 1) * 0.12))
        yen_reward = int(enemy_data["yen"] * (1 + (p["level"] - 1) * 0.15))

        p_hp, p_mp, p_atk = p["hp_max"], p["mp_max"], p["atk"]
        st_id = p.get("equipped_style")
        
        if st_id and st_id in STYLES:
            st = STYLES[st_id]
            p_atk = int(p_atk * st["atk_mod"])
            p_hp = int(p_hp * st["hp_mod"])

        clan_bonus = 1.15 if c_name else 1.0
        base_atk = int(p_atk * clan_bonus)

        rage_turns = 0
        player_frozen = False

        if st_id and st_id in STYLES:
            eq = STYLES[st_id]["skills"]
        else:
            eq = p.get("equipped_skills", [None, None, None])

        active_menu = {"1": "Đánh thường", "2": "Phòng thủ"}
        skill_mapping = {}

        opt_idx = 3
        for sid in eq:
            if sid and sid in SKILL_TREE:
                sinfo = SKILL_TREE[sid]
                active_menu[str(opt_idx)] = sinfo["name"]
                skill_mapping[str(opt_idx)] = sid
                opt_idx += 1

        valid_choices = [str(k) for k in active_menu.keys()]

        def check_msg(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content in valid_choices

        prefix = f"🔥 **BOSS BẢO VỆ: {enemy_data.get('skill_name', '')}** 🔥" if is_boss else "⚔️ **BATTLE THƯỜNG**"
        
        def battle_status(log_msg=""):
            style_str = f" [{STYLES[st_id]['name']}]" if st_id else ""
            embed = discord.Embed(title=f"💥 {ctx.author.display_name}{style_str} VS {e_name}", color=discord.Color.purple())
            embed.add_field(name=f"👤 {ctx.author.display_name}", value=f"❤️ HP: {p_hp}/{p['hp_max']}\n🧪 MP: {p_mp}/{p['mp_max']}\n⚔️ ATK: {base_atk}", inline=True)
            embed.add_field(name=f"👹 {e_name}", value=f"❤️ HP: {e_hp}/{e_max_hp}\n⚔️ ATK: {e_atk}", inline=True)
            
            cmd_text = "\n".join([f"`{k}` - {v}" for k, v in active_menu.items()])
            embed.add_field(name="📋 Lựa chọn kỹ năng:", value=cmd_text, inline=False)
            if log_msg: embed.set_footer(text=log_msg)
            return embed

        status_msg = await ctx.send(f"{prefix}", embed=battle_status("Bắt đầu trận đấu!"))

        while p_hp > 0 and e_hp > 0:
            if player_frozen:
                player_frozen = False
                await ctx.send("❄️ **Bạn bị ĐÓNG BĂNG! Mất lượt này.**")
                e_dmg = random.randint(e_atk - 2, e_atk + 5)
                p_hp -= e_dmg
                await status_msg.edit(embed=battle_status(f"❄️ Bị đóng băng! {e_name} đánh gây {e_dmg} sát thương!"))
                if p_hp <= 0: break
                continue

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
                    p_action_log = f"Bạn đánh gây {dmg} sát thương!"
                elif action == "2":
                    is_defending = True
                    p_action_log = "🛡️ Bạn giơ giáp Phòng Thủ!"
                else:
                    sid = skill_mapping[action]
                    sinfo = SKILL_TREE[sid]
                    req_mp = sinfo.get("mp_cost", 0)

                    if p_mp < req_mp:
                        p_action_log = f"❌ Không đủ MP! (Cần {req_mp} MP)."
                    else:
                        p_mp -= req_mp
                        if sid in ["crossover", "challenger_rush"]:
                            dmg = int(random.randint(int(base_atk * 1.8), int(base_atk * 2.5)))
                            e_hp -= dmg
                            p_action_log = f"💥 {sinfo['name']} gây {dmg} sát thương!"
                        elif sid in ["basic_jab", "long_guard_counter", "outbox_swift", "hitman_flicker"]:
                            dmg = int(base_atk * 1.6)
                            e_hp -= dmg
                            p_action_log = f"🥊 {sinfo['name']} chính xác gây {dmg} sát thương!"
                        elif sid == "heal":
                            p_hp = min(p["hp_max"], p_hp + 40)
                            p_action_log = "🥤 Dùng Hồi Xuân hồi +40 HP!"
                        elif sid == "rest":
                            p_mp = min(p["mp_max"], p_mp + 15)
                            p_action_log = "🧘 Dùng Rest hồi +15 MP!"
                        elif sid == "smash_heavy":
                            dmg = int(base_atk * 2.7)
                            e_hp -= dmg
                            p_action_log = f"💥 Smash Heavy đánh móc trời giáng gây {dmg} sát thương!"
                        elif sid in ["chronos_delay", "freedom_flash"]:
                            dmg = int(base_atk * 3.0)
                            e_hp -= dmg
                            p_action_log = f"⚡ {sinfo['name']} chớp nhoáng gây {dmg} sát thương!"
                        elif sid in ["slugger_power", "ippo_dempsey"]:
                            dmg = int(base_atk * 3.8)
                            e_hp -= dmg
                            p_action_log = f"🔥 **{sinfo['name']}** bộc phát toàn lực gây {dmg} sát thương hủy diệt!"

                if e_hp <= 0:
                    e_hp = 0
                    p["exp"] += exp_reward
                    p["yen"] += yen_reward
                    
                    spin_msg = ""
                    p["spin_counter"] -= 1
                    if p["spin_counter"] <= 0:
                        p["inventory"]["lucky_spin"] = p["inventory"].get("lucky_spin", 0) + 1
                        p["spin_counter"] = random.randint(1, 3)
                        spin_msg = "\n🎟️ **BẠN NHẬN ĐƯỢC 1x VÒNG QUAY NGẪU NHIÊN!**"

                    await status_msg.edit(embed=battle_status(f"🎉 CHIẾN THẮNG! Nhận {exp_reward} EXP và ¥{yen_reward:,}{spin_msg}"))
                    break

                e_dmg = random.randint(e_atk - 2, e_atk + 6)
                if is_defending: e_dmg = int(e_dmg * 0.5)
                p_hp -= e_dmg
                e_action_log = f"{e_name} đánh gây {e_dmg} sát thương!"

                if p_hp <= 0:
                    await status_msg.edit(embed=battle_status(f"💀 THẤT BẠI trước {e_name}..."))
                    break

                await status_msg.edit(embed=battle_status(f"{p_action_log} | {e_action_log}"))

            except asyncio.TimeoutError:
                await ctx.send("Quá thời gian lựa chọn!")
                break

    finally:
        p["in_battle"] = False
        save_json(RPG_DATA_PATH, rpg_data)

# -------------------- COMMANDS: STYLE SYSTEM --------------------
@bot.command(name="Tstyle")
async def style_command(ctx, action: str = None, style_id: str = None):
    p = get_player(ctx.author.id)

    if not action:
        embed = discord.Embed(title="🥊 UNTITLED BOXING GAME STYLES", description="Trang bị Style để nhận bộ skill cố định và hệ số chỉ số tương ứng!", color=discord.Color.gold())
        owned = p.get("owned_styles", [])
        curr = p.get("equipped_style")

        for sid, sinfo in STYLES.items():
            status = "⭐ Đang trang bị" if curr == sid else ("✅ Đã sở hữu" if sid in owned else f"❌ Chưa sở hữu (Giá: ¥{sinfo['price']:,})")
            atk_p = f"+{int((sinfo['atk_mod']-1)*100)}%" if sinfo['atk_mod'] >= 1 else f"{int((sinfo['atk_mod']-1)*100)}%"
            hp_p = f"+{int((sinfo['hp_mod']-1)*100)}%" if sinfo['hp_mod'] >= 1 else f"{int((sinfo['hp_mod']-1)*100)}%"
            
            embed.add_field(
                name=f"[{RARITY_COLORS[sinfo['rarity']]}] {sinfo['name']} (`{sid}`)",
                value=f"Trạng thái: **{status}**\nChỉ số: ATK ({atk_p}) | HP ({hp_p})\n*{sinfo['desc']}*",
                inline=False
            )
        embed.set_footer(text="Dùng lệnh: !Tstyle equip <mã_style> | !Tstyle unequip")
        return await ctx.send(embed=embed)

    act = action.lower()
    if act == "equip":
        if not style_id: return await ctx.send("Nhập mã style muốn trang bị! Ví dụ: `!Tstyle equip ippo`")
        sid = style_id.lower()
        if sid not in STYLES: return await ctx.send("Mã style không tồn tại!")
        if sid not in p.get("owned_styles", []): return await ctx.send("Bạn chưa sở hữu style này! Hãy mua trong Shop hoặc quay vòng quay.")

        p["equipped_style"] = sid
        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send(f"🥊 Đã trang bị thành công **{STYLES[sid]['name']}**!")

    elif act == "unequip":
        p["equipped_style"] = None
        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send("🛡️ Đã gỡ Style thành công.")

# -------------------- COMMANDS: SHOP, BATTLE, TBOSS, TUSE --------------------
@bot.command(name="battle")
async def battle_command(ctx):
    enemy = random.choice(REGULAR_ENEMIES)
    await run_battle_engine(ctx, enemy, is_boss=False)

@bot.command(name="Tboss")
async def boss_command(ctx):
    p = get_player(ctx.author.id)
    if p["level"] < 5: return await ctx.send("⚠️ Cần đạt Level 5 trở lên để đánh Boss!")
    boss = random.choice(BOSSES)
    await run_battle_engine(ctx, boss, is_boss=True)

@bot.command(name="Tshop")
async def shop_command(ctx, action: str = None, item_code: str = None):
    p = get_player(ctx.author.id)
    
    if not action:
        embed = discord.Embed(title="🛒 CỬA HÀNG STYLES & VẬT PHẨM", color=discord.Color.green())
        style_list = "\n".join([f"`{sid}` - {s['name']} ({RARITY_COLORS[s['rarity']]}) : **¥{s['price']:,}**" for sid, s in STYLES.items()])
        embed.add_field(name="🥊 UBG STYLES", value=style_list, inline=False)
        embed.add_field(name="🥤 VẬT PHẨM", value="`stamina` (¥300) | `bento` (¥800)", inline=False)
        embed.set_footer(text="Dùng: !Tshop buy_style <mã> hoặc !Tshop buy <mã>")
        return await ctx.send(embed=embed)

    if action.lower() == "buy_style":
        if not item_code: return await ctx.send("Vui lòng nhập mã style muốn mua!")
        sid = item_code.lower()
        if sid not in STYLES: return await ctx.send("Mã style không tồn tại!")
        if sid in p.get("owned_styles", []): return await ctx.send("Bạn đã sở hữu style này rồi!")
        
        price = STYLES[sid]["price"]
        if p["yen"] < price:
            return await ctx.send(f"❌ Không đủ Yên! Cần **¥{price:,} Yên** để mua style này.")

        p["yen"] -= price
        p["owned_styles"].append(sid)
        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send(f"🎉 Mua thành công style **{STYLES[sid]['name']}**!")

@bot.command(name="Tuse")
async def use_item(ctx, item_code: str = None):
    if not item_code: return await ctx.send("Nhập mã vật phẩm muốn dùng: `!Tuse spin`")

    p = get_player(ctx.author.id)
    code = item_code.lower()
    if code in ["spin", "vongquay"]: code = "lucky_spin"

    inv = p.get("inventory", {})
    if inv.get(code, 0) <= 0: return await ctx.send("⚠️ Bạn không có vật phẩm này trong túi đồ!")

    inv[code] -= 1

    if code == "lucky_spin":
        # Tỉ lệ Gacha phân chia theo độ hiếm Style
        reward_type = random.choices(["yen", "qp", "exp", "style"], weights=[35, 25, 20, 20])[0]
        
        if reward_type == "style":
            # Phân bổ tỉ lệ xuất hiện style theo cấp bậc
            rarity_weights = {"common": 50, "rare": 30, "epic": 15, "legend": 4, "myth": 1}
            pool = []
            for sid, s in STYLES.items():
                if sid not in p.get("owned_styles", []):
                    pool.extend([sid] * rarity_weights.get(s["rarity"], 10))
            
            if pool:
                got_style = random.choice(pool)
                p["owned_styles"].append(got_style)
                res_str = f"🥊 **[{RARITY_COLORS[STYLES[got_style]['rarity']]}] Style {STYLES[got_style]['name']}**"
            else:
                val = 10000
                p["yen"] += val
                res_str = f"💰 **¥{val:,} Yên** (Đã sưu tầm toàn bộ Style)"
        elif reward_type == "yen":
            val = random.randint(3000, 25000)
            p["yen"] += val
            res_str = f"💰 **¥{val:,} Yên**"
        elif reward_type == "qp":
            val = random.randint(20, 100)
            p["qpoint"] += val
            res_str = f"⭐ **{val} Qpoint**"
        else:
            val = random.randint(150, 800)
            p["exp"] += val
            res_str = f"⚡ **{val} EXP**"

        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send(f"🎰 **VÒNG QUAY NGẪU NHIÊN...**\n🎉 Bạn nhận được: {res_str}!")

@bot.command(name="profile")
async def profile(ctx):
    p = get_player(ctx.author.id)
    c_name, _ = get_player_clan(ctx.author.id)
    clan_str = f"🏰 **{c_name}** (+15% ATK)" if c_name else "Chưa có"

    st_id = p.get("equipped_style")
    style_str = f"[{RARITY_COLORS[STYLES[st_id]['rarity']]}] **{STYLES[st_id]['name']}**" if st_id else "Chưa trang bị"

    embed = discord.Embed(title=f"📜 Bảng Chỉ Số: {ctx.author.display_name}", color=discord.Color.gold())
    embed.add_field(name="Level", value=f"Lv.{p['level']} (SP: {p['sp']})", inline=True)
    embed.add_field(name="Yên", value=f"¥{p['yen']:,}", inline=True)
    embed.add_field(name="UBG Style", value=style_str, inline=False)
    embed.add_field(name="Clan", value=clan_str, inline=False)
    await ctx.send(embed=embed)

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
