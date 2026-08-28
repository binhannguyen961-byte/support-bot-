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
            "inventory": {},
            "last_daily": None,
            "trait": None
        }
        save_json(RPG_DATA_PATH, rpg_data)
    
    if "inventory" not in rpg_data[uid]:
        rpg_data[uid]["inventory"] = {}
    if "last_daily" not in rpg_data[uid]:
        rpg_data[uid]["last_daily"] = None
    if "trait" not in rpg_data[uid]:
        rpg_data[uid]["trait"] = None
    save_json(RPG_DATA_PATH, rpg_data)
        
    return rpg_data[uid]

def get_player_clan(user_id):
    uid = str(user_id)
    for clan_name, info in clan_data.items():
        if uid in info["members"]:
            return clan_name, info
    return None, None

def get_shop_price(base_price, level):
    scale = 1 + (level - 1) * 0.05
    return int(base_price * scale)

# -------------------- DANH SÁCH TRAITS --------------------
BUFF_TRAITS = [
    {"id": "godlike", "name": "神 - Sức Mạnh Thần Thoại", "desc": "+50% ATK và +30% HP Max trong mọi trận đấu."},
    {"id": "speedster", "name": "⚡ Siêu Tốc Độ", "desc": "Có 20% tỷ lệ né hoàn toàn đòn đánh của kẻ thù."},
    {"id": "vampiric", "name": "🦇 Huyết Tộc", "desc": "Hồi lại 20% sát thương gây ra thành HP."}
]

CURSE_TRAITS = [
    {"id": "fragile", "name": "☠️ Tẩy Não / Cơ Thể Yếu Ớt", "desc": "Giảm 25% HP Max khi bước vào trận đấu."},
    {"id": "sluggish", "name": "🐢 Chậm Chạp", "desc": "Bị mất 10% ATK trong mọi trận chiến."}
]

# -------------------- DANH SÁCH VẬT PHẨM --------------------
ITEMS = {
    "stamina": {
        "name": "Hộp sữa Stamina",
        "price": 300,
        "desc": "Nước uống đường phố Kamurocho. Hồi 40 HP vĩnh viễn/ngay lập tức.",
        "type": "heal_hp",
        "value": 40
    },
    "bento": {
        "name": "Hộp Bento Kamurocho",
        "price": 800,
        "desc": "Cơm hộp nóng hổi. Hồi 100 HP.",
        "type": "heal_hp",
        "value": 100
    },
    "energy": {
        "name": "Nước tăng lực Starlight",
        "price": 500,
        "desc": "Đồ uống phục hồi năng lượng tinh thần. Hồi 35 MP.",
        "type": "heal_mp",
        "value": 35
    },
    "rokaka": {
        "name": "Trái Rokaka",
        "price": 5000,
        "desc": "Trái cây kỳ lạ giúp tẩy sạch hoàn toàn Trait (Đặc tính) hiện tại của bạn.",
        "type": "reset_trait",
        "value": 0
    },
    "mystery_box": {
        "name": "Hộp bí ẩn",
        "price": 1250,
        "desc": "Mở ra ngẫu nhiên từ 1 đến 15,000 Yên (Cấp càng cao tỉ lệ trúng thưởng lớn càng giảm).",
        "type": "mystery_box",
        "value": 0
    }
}

# -------------------- DANH SÁCH QUÁI VÀ BOSS --------------------
REGULAR_ENEMIES = [
    {"name": "Quickbullet", "hp": 110, "atk": 15, "exp": 55, "yen": 1100, "desc": "Kẻ sở hữu tốc độ chớp nhoáng (25% cơ hội cướp lượt đánh trước)!", "special": "quickbullet"},
    {"name": "Demonking", "hp": 220, "atk": 20, "exp": 100, "yen": 2200, "desc": "Quỷ Vương hùng mạnh (Tự động hồi 90% HP khi xuống dưới 15% máu)!", "special": "demonking"},
    {"name": "Gã Trộm Đồ Lặt Vặt Hẻm Nhỏ", "hp": 70, "atk": 8, "exp": 25, "yen": 400, "desc": "Một gã móc túi lề đường bình thường."},
    {"name": "Sát Thủ Passione (JoJo Part 5)", "hp": 130, "atk": 16, "exp": 60, "yen": 1200, "desc": "Sử dụng Stand dạng cận chiến tấn công chớp nhoáng."},
    {"name": "Tên Lính Thuê Chitauri (MCU)", "hp": 140, "atk": 18, "exp": 70, "yen": 1600, "desc": "Mang vũ khí năng lượng vũ trụ từ binh đoàn Thanos."}
]

BOSSES = [
    {"name": "Superman (DC Comics)", "hp": 950, "atk": 75, "exp": 1200, "yen": 35000, "desc": "Người Đàn Ông Thép với sức mạnh thể chất áp đảo!"},
    {"name": "Sentry (Marvel)", "hp": 1050, "atk": 85, "exp": 1500, "yen": 42000, "desc": "Anh hùng sở hữu sức mạnh của một triệu mặt trời phát nổ!"},
    {"name": "Void (Marvel)", "hp": 1200, "atk": 95, "exp": 1800, "yen": 50000, "desc": "Thực thể bóng tối hủy diệt mang sức mạnh vô hạn!"},
    {"name": "Doomsday (DC Comics)", "hp": 1100, "atk": 80, "exp": 1600, "yen": 45000, "desc": "Quái vật tiến hóa không thể bị tiêu diệt theo cách thông thường!"},
    {"name": "Loki (MCU)", "hp": 800, "atk": 65, "exp": 1000, "yen": 30000, "desc": "Vị Thần Lừa Lọc với những ảo thuật thao túng tâm trí!"},
    {"name": "Ultron (MCU)", "hp": 900, "atk": 70, "exp": 1100, "yen": 32000, "desc": "Trí tuệ nhân tạo bá chủ cùng binh đoàn Vibranium!"},
    {"name": "Diavolo (King Crimson - JoJo Part 5)", "hp": 750, "atk": 60, "exp": 900, "yen": 25000, "desc": "Trùm Passione với khả năng xóa bỏ thời gian!"},
    {"name": "Thanos (MCU)", "hp": 1000, "atk": 80, "exp": 1400, "yen": 40000, "desc": "Gã Titan Điên mang găng tay vô cực!"}
]

# -------------------- TIỆN ÍCH QUYỀN & XÁC NHẬN --------------------
async def is_authorized(ctx):
    try:
        if ctx.author.id in OWNER_IDS:
            return True
    except Exception:
        pass
    return ctx.author.guild_permissions.administrator

async def confirm_action(ctx, target_user, action_desc: str, timeout: int = 30):
    confirm_msg = await ctx.send(f"{target_user.mention}, xác nhận: **{action_desc}**\nVui lòng thả emoji ✅ trong vòng {timeout} giây để đồng ý.")
    await confirm_msg.add_reaction("✅")

    def check(reaction, user):
        return user == target_user and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id

    try:
        await bot.wait_for('reaction_add', timeout=timeout, check=check)
        return True
    except asyncio.TimeoutError:
        try:
            await confirm_msg.edit(content=f"❌ Đã hủy: Không nhận được xác nhận từ {target_user.mention}.")
        except Exception:
            pass
        return False

# -------------------- LỆNH HƯỚNG DẪN --------------------
@bot.command(name="Thelps")
async def custom_help(ctx):
    embed = discord.Embed(
        title="⚡ True Architect - Tiến Hóa & Kiến Tạo",
        description="Hệ thống quản trị và Minigame RPG Turn-Based Crossover.",
        color=discord.Color.from_rgb(30, 30, 30)
    )
    embed.add_field(
        name="🎮 Turn-Based RPG & Boss",
        value=(
            "`!battle` - Đụng độ quái thường (Quickbullet, Demonking, Passione...).\n"
            "`!Tboss` - Khiêu chiến Boss Cực Siêu Cấp (Superman, Sentry, Void, Doomsday... Req: Lv.5+).\n"
            "`!profile` - Xem chỉ số, Trait vĩnh viễn, Clan và Yên.\n"
            "`!Tdaily` - Nhận phần thưởng hàng ngày (Reset mỗi 12 giờ)."
        ),
        inline=False
    )
    embed.add_field(
        name="🏰 Hệ Thống Clan (Tộc)",
        value=(
            "`!Tclan create <tên_clan>` - Tạo Clan mới.\n"
            "`!Tclan invite @user` - Mời thành viên vào Clan (Cần đồng ý).\n"
            "`!Tclan info` - Xem thông tin Clan hiện tại."
        ),
        inline=False
    )
    embed.add_field(
        name="🏪 Cửa Hàng & Túi Đồ",
        value=(
            "`!Tshop` / `!Tstore` - Xem danh sách vật phẩm (Có trái Rokaka giá 5000 Yên).\n"
            "`!Tshop buy <mã_món> [số_lượng]` - Mua vật phẩm.\n"
            "`!Tinventory` - Xem túi đồ cá nhân.\n"
            "`!Tuse <mã_món>` - Sử dụng vật phẩm (Bao gồm Rokaka xóa Trait)."
        ),
        inline=False
    )
    await ctx.send(embed=embed)

# -------------------- TÍNH NĂNG TDAILY --------------------
@bot.command(name="Tdaily")
async def daily_reward(ctx):
    p = get_player(ctx.author.id)
    now = datetime.utcnow()

    if p["last_daily"]:
        last_time = datetime.fromisoformat(p["last_daily"])
        if now - last_time < timedelta(hours=12):
            remaining = timedelta(hours=12) - (now - last_time)
            hours, remainder = divmod(int(remaining.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            return await ctx.send(f"⏳ Bạn đã nhận quà rồi! Hãy quay lại sau **{hours}h {minutes}m {seconds}s**.")

    reward_yen = 1000 + (p["level"] * 250)
    reward_exp = 50 + (p["level"] * 15)

    p["yen"] += reward_yen
    p["exp"] += reward_exp
    p["last_daily"] = now.isoformat()

    save_json(RPG_DATA_PATH, rpg_data)
    await ctx.send(f"🎁 **QUÀ HẰNG NGÀY!**\nBạn đã nhận được **¥{reward_yen:,}** và **{reward_exp} EXP**!")

# -------------------- TÍNH NĂNG TCLAN --------------------
@bot.command(name="Tclan")
async def clan_command(ctx, sub_cmd: str = None, *, arg: str = None):
    p = get_player(ctx.author.id)
    c_name, c_info = get_player_clan(ctx.author.id)

    if not sub_cmd or sub_cmd.lower() == "info":
        if not c_name:
            return await ctx.send("Bạn chưa tham gia Clan nào. Dùng `!Tclan create <tên_clan>` để tạo mới!")
        
        members_str = ", ".join([f"<@{m}>" for m in c_info["members"]])
        embed = discord.Embed(title=f"🏰 Clan: {c_name}", color=discord.Color.gold())
        embed.add_field(name="Chủ Clan", value=f"<@{c_info['owner']}>", inline=True)
        embed.add_field(name="Số thành viên", value=f"{len(c_info['members'])}", inline=True)
        embed.add_field(name="Nội quy / Tác dụng", value="Thành viên Clan được **+15% ATK** khi săn quái và Boss!", inline=False)
        embed.add_field(name="Danh sách thành viên", value=members_str, inline=False)
        return await ctx.send(embed=embed)

    act = sub_cmd.lower()
    if act == "create":
        if not arg:
            return await ctx.send("Vui lòng nhập tên Clan! Ví dụ: `!Tclan create Passione`")
        if c_name:
            return await ctx.send(f"Bạn đã thuộc Clan **{c_name}** rồi!")
        
        clan_title = arg.strip()
        if clan_title in clan_data:
            return await ctx.send("Tên Clan này đã tồn tại, hãy chọn tên khác.")

        clan_data[clan_title] = {
            "owner": str(ctx.author.id),
            "members": [str(ctx.author.id)]
        }
        save_json(CLAN_DATA_PATH, clan_data)
        await ctx.send(f"🎉 Đã thành lập Clan **{clan_title}** thành công!")

    elif act == "invite":
        if not ctx.message.mentions:
            return await ctx.send("Vui lòng @người bạn muốn mời vào Clan!")
        if not c_name:
            return await ctx.send("Bạn phải có Clan mới có thể mời người khác!")
        if c_info["owner"] != str(ctx.author.id):
            return await ctx.send("Chỉ chủ Clan mới có quyền mời thành viên!")

        target = ctx.message.mentions[0]
        if target.id == ctx.author.id or target.bot:
            return await ctx.send("Mục tiêu không hợp lệ.")

        target_clan, _ = get_player_clan(target.id)
        if target_clan:
            return await ctx.send(f"{target.mention} đã ở trong Clan **{target_clan}** rồi!")

        ok = await confirm_action(ctx, target, f"Bạn được {ctx.author.mention} mời tham gia Clan **{c_name}**!")
        if ok:
            clan_data[c_name]["members"].append(str(target.id))
            save_json(CLAN_DATA_PATH, clan_data)
            await ctx.send(f"🎊 {target.mention} đã chính thức gia nhập Clan **{c_name}**!")

# -------------------- SHOP, INVENTORY & USE --------------------
@bot.command(name="Tshop", aliases=["Tstore"])
async def shop_command(ctx, action: str = None, item_id: str = None, amount: int = 1):
    p = get_player(ctx.author.id)
    
    if not action:
        embed = discord.Embed(
            title="🏪 Cửa Hàng Đa Vũ Trụ Kamurocho",
            description=f"Số tiền hiện có: **¥{p['yen']:,}** (Giá vật phẩm có thể điều chỉnh nhẹ theo Level {p['level']})\nDùng `!Tshop buy <mã_món> [số_lượng]` để mua.",
            color=discord.Color.green()
        )
        for code, info in ITEMS.items():
            curr_price = get_shop_price(info["price"], p["level"])
            embed.add_field(
                name=f"📦 {info['name']} (`{code}`)",
                value=f"Giá: **¥{curr_price:,}**\n*{info['desc']}*",
                inline=False
            )
        return await ctx.send(embed=embed)

    act = action.lower()
    if act == "buy":
        if not item_id or item_id.lower() not in ITEMS:
            return await ctx.send("Mã vật phẩm không hợp lệ! Dùng `!Tshop` để xem mã.")
        
        item_key = item_id.lower()
        item = ITEMS[item_key]
        amount = max(1, amount)
        unit_price = get_shop_price(item["price"], p["level"])
        total_price = unit_price * amount

        if p["yen"] < total_price:
            return await ctx.send(f"Bạn không đủ tiền Yên! Cần **¥{total_price:,}** nhưng chỉ có **¥{p['yen']:,}**.")

        p["yen"] -= total_price
        inv = p["inventory"]
        inv[item_key] = inv.get(item_key, 0) + amount
        save_json(RPG_DATA_PATH, rpg_data)

        await ctx.send(f"🛍️ Đã mua thành công **{amount}x {item['name']}** với giá **¥{total_price:,}**!")

@bot.command(name="Tinventory")
async def inventory_command(ctx):
    p = get_player(ctx.author.id)
    inv = p.get("inventory", {})

    embed = discord.Embed(
        title=f"🎒 Túi Đồ Của {ctx.author.display_name}",
        description=f"Tiền Yên: **¥{p['yen']:,}**\nDùng `!Tuse <mã_món>` để sử dụng vật phẩm.",
        color=discord.Color.blue()
    )

    if not inv:
        embed.add_field(name="Trống rỗng", value="Bạn chưa có vật phẩm nào trong túi.", inline=False)
    else:
        for item_key, count in inv.items():
            if item_key in ITEMS:
                info = ITEMS[item_key]
                embed.add_field(
                    name=f"🔹 {info['name']} (`{item_key}`): {count} cái",
                    value=f"*{info['desc']}*",
                    inline=False
                )

    await ctx.send(embed=embed)

@bot.command(name="Tuse")
async def use_command(ctx, item_id: str = None):
    if not item_id:
        return await ctx.send("Vui lòng nhập mã vật phẩm muốn dùng. VD: `!Tuse rokaka`")

    item_key = item_id.lower()
    p = get_player(ctx.author.id)
    inv = p.get("inventory", {})

    if inv.get(item_key, 0) <= 0:
        return await ctx.send("Bạn không sở hữu vật phẩm này trong túi đồ!")

    if item_key not in ITEMS:
        return await ctx.send("Vật phẩm không tồn tại.")

    item = ITEMS[item_key]
    itype = item["type"]
    val = item["value"]

    msg = ""
    if itype == "heal_hp":
        msg = f"🥤 Bạn đã dùng **{item['name']}** và hồi phục **+{val} HP**!"
    elif itype == "heal_mp":
        msg = f"🧪 Bạn đã dùng **{item['name']}** và hồi phục **+{val} MP**!"
    elif itype == "reset_trait":
        if not p.get("trait"):
            return await ctx.send("Bạn hiện không có Trait nào để tẩy!")
        
        old_trait_name = p["trait"]["name"]
        p["trait"] = None
        msg = f"🍍 Bạn đã ăn **Trái Rokaka**! Trait **[{old_trait_name}]** đã bị tẩy sạch vĩnh viễn!"
    elif itype == "mystery_box":
        lvl = p["level"]
        roll = random.random()
        jackpot_chance = max(0.005, 0.05 - (lvl * 0.003))
        big_chance = max(0.05, 0.20 - (lvl * 0.01))

        if roll < jackpot_chance:
            got_yen = 15000
            box_note = "🎉 **ĐẠI CÁT! JACKPOT CỰC HIẾM!**"
        elif roll < jackpot_chance + big_chance:
            got_yen = random.randint(3000, 8000)
            box_note = "✨ **MAY MẮN LỚN!**"
        else:
            got_yen = random.randint(1, 1500)
            box_note = "📦 Phần thưởng nhận được:"

        p["yen"] += got_yen
        msg = f"🎁 Bạn vừa mở **Hộp Bí Ẩn**... {box_note} Bạn nhận được **¥{got_yen:,}**!"

    inv[item_key] -= 1
    if inv[item_key] <= 0:
        del inv[item_key]

    save_json(RPG_DATA_PATH, rpg_data)
    await ctx.send(msg)

# -------------------- HỆ THỐNG TRẬN ĐẤU & BOSS --------------------
async def run_battle_engine(ctx, enemy_data, is_boss=False):
    p = get_player(ctx.author.id)
    c_name, _ = get_player_clan(ctx.author.id)

    # Scaling chỉ số quái theo level người chơi
    scale = 1 + (p["level"] - 1) * 0.18
    e_name = enemy_data["name"]
    e_hp = int(enemy_data["hp"] * scale)
    e_max_hp = e_hp
    e_atk = int(enemy_data["atk"] * scale)
    e_special = enemy_data.get("special", None)
    demonking_healed = False
    
    exp_reward = int(enemy_data["exp"] * (1 + (p["level"] - 1) * 0.12))
    yen_reward = int(enemy_data["yen"] * (1 + (p["level"] - 1) * 0.15))

    p_hp = p["hp_max"]
    p_mp = p["mp_max"]
    p_atk = p["atk"]

    # Áp dụng hiệu ứng Trait nếu có
    p_trait = p.get("trait")
    trait_desc_msg = ""
    dodge_chance = 0.0
    lifesteal = False

    if p_trait:
        trait_desc_msg = f"\n🌀 **Trait Active:** {p_trait['name']}"
        tid = p_trait["id"]
        if tid == "godlike":
            p_atk = int(p_atk * 1.5)
            p_hp = int(p_hp * 1.3)
        elif tid == "speedster":
            dodge_chance = 0.20
        elif tid == "vampiric":
            lifesteal = True
        elif tid == "fragile":
            p_hp = int(p_hp * 0.75)
        elif tid == "sluggish":
            p_atk = int(p_atk * 0.9)

    # Buff ATK nếu ở Clan
    clan_bonus = 1.15 if c_name else 1.0
    effective_atk = int(p_atk * clan_bonus)

    def check_msg(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["1", "2", "3", "4"]

    prefix = "🔥 **TRẬN ĐẤU BOSS SIÊU CẤP** 🔥" if is_boss else "⚔️ **BATTLE THƯỜNG**"
    clan_msg = f"\n🛡️ *Buff Clan (+15% ATK) đang kích hoạt!*" if c_name else ""
    await ctx.send(f"{prefix}\nĐối thủ: **{e_name}**\n📝 *{enemy_data.get('desc', '')}*{clan_msg}{trait_desc_msg}\n(HP: {e_hp} | ATK: {e_atk})")

    def battle_status(log_msg=""):
        color = discord.Color.red() if is_boss else discord.Color.purple()
        embed = discord.Embed(title=f"💥 {ctx.author.display_name} VS {e_name}", color=color)
        embed.add_field(name=f"👤 {ctx.author.display_name}", value=f"❤️ HP: {p_hp}/{p['hp_max']}\n🧪 MP: {p_mp}/{p['mp_max']}\n⚔️ ATK: {effective_atk}", inline=True)
        embed.add_field(name=f"👹 {e_name}", value=f"❤️ HP: {e_hp}/{e_max_hp}\n⚔️ ATK: {e_atk}", inline=True)
        embed.add_field(
            name="📋 Hành động của bạn:", 
            value="`1` - Đấm thường\n`2` - Tuyệt kỹ Crossover (Tốn 15 MP)\n`3` - Hồi máu (Tốn 20 MP)\n`4` - Phòng thủ (Giảm 50% sát thương)", 
            inline=False
        )
        if log_msg:
            embed.set_footer(text=log_msg)
        return embed

    status_msg = await ctx.send(embed=battle_status("Chọn lượt của bạn!"))

    while p_hp > 0 and e_hp > 0:
        # Cơ chế Quickbullet: 25% tỷ lệ cướp lượt đánh trước
        if e_special == "quickbullet" and random.random() < 0.25:
            q_dmg = random.randint(e_atk - 2, e_atk + 5)
            p_hp -= q_dmg
            await ctx.send(f"⚡ **Quickbullet quá nhanh!** Cướp lượt và gây **{q_dmg} sát thương** trước khi bạn kịp phản ứng!")
            if p_hp <= 0:
                p_hp = 0
                await status_msg.edit(embed=battle_status(f"💀 BẠN ĐÃ THẤT BẠI trước {e_name}..."))
                break

        try:
            msg = await bot.wait_for("message", timeout=30.0, check=check_msg)
            action = msg.content
            try:
                await msg.delete()
            except Exception:
                pass
            
            p_action_log = ""
            is_defending = False

            if action == "1":
                dmg = random.randint(effective_atk - 3, effective_atk + 5)
                e_hp -= dmg
                p_action_log = f"Bạn vung đấm vào {e_name} gây {dmg} sát thương!"
                if lifesteal:
                    heal_ls = int(dmg * 0.2)
                    p_hp = min(p["hp_max"], p_hp + heal_ls)
                    p_action_log += f" (Hút +{heal_ls} HP)"
            elif action == "2":
                if p_mp >= 15:
                    p_mp -= 15
                    dmg = random.randint(int(effective_atk * 1.8), int(effective_atk * 2.5))
                    e_hp -= dmg
                    p_action_log = f"🔥 Tuyệt kỹ Crossover Bộc Phát! Gây {dmg} sát thương!"
                    if lifesteal:
                        heal_ls = int(dmg * 0.2)
                        p_hp = min(p["hp_max"], p_hp + heal_ls)
                        p_action_log += f" (Hút +{heal_ls} HP)"
                else:
                    p_action_log = "Không đủ MP! Lượt bị trôi qua."
            elif action == "3":
                if p_mp >= 20:
                    p_mp -= 20
                    heal = random.randint(35, 55)
                    p_hp = min(p["hp_max"], p_hp + heal)
                    p_action_log = f"🥤 Bạn hồi {heal} HP!"
                else:
                    p_action_log = "Không đủ MP! Lượt bị trôi qua."
            elif action == "4":
                is_defending = True
                p_action_log = "🛡️ Bạn tập trung phòng thủ!"

            # Cơ chế Demonking: Hồi 90% HP khi <= 15% HP
            if e_special == "demonking" and not demonking_healed and (e_hp / e_max_hp) <= 0.15 and e_hp > 0:
                heal_dk = int(e_max_hp * 0.9)
                e_hp = min(e_max_hp, e_hp + heal_dk)
                demonking_healed = True
                p_action_log += f"\n👿 **Demonking kích hoạt Quỷ Sức! Hồi lại {heal_dk} HP!**"

            if e_hp <= 0:
                e_hp = 0
                p["exp"] += exp_reward
                p["yen"] += yen_reward
                
                lvl_up_msg = ""
                if p["exp"] >= p["level"] * 100:
                    p["exp"] -= p["level"] * 100
                    p["level"] += 1
                    p["hp_max"] += 20
                    p["mp_max"] += 10
                    p["atk"] += 5
                    lvl_up_msg = f"\n🎉 **THĂNG CẤP LÊN Lv.{p['level']}!** (Quái & Boss từ nay sẽ trâu hơn!)"

                # Cơ chế rơi Trait khi hạ Boss (5% tỉ lệ)
                trait_got_msg = ""
                if is_boss and random.random() < 0.05:
                    if random.random() < 0.75:
                        selected_trait = random.choice(BUFF_TRAITS)
                        trait_got_msg = f"\n✨ **BÁ ĐẠO!** Bạn hạ gục Boss và thức tỉnh Trait Xịn: **[{selected_trait['name']}]**! (*{selected_trait['desc']}*)"
                    else:
                        selected_trait = random.choice(CURSE_TRAITS)
                        trait_got_msg = f"\n☠️ **LỜI NGUYỀN!** Bạn bị dính bùa chú từ Boss và nhận Trait Cản Trở: **[{selected_trait['name']}]**! (*{selected_trait['desc']}*)"
                    
                    p["trait"] = selected_trait

                save_json(RPG_DATA_PATH, rpg_data)
                await status_msg.edit(embed=battle_status(f"🎉 BẠN ĐÃ CHIẾN THẮNG! Nhận {exp_reward} EXP và ¥{yen_reward:,}{lvl_up_msg}{trait_got_msg}"))
                break

            # Lượt kẻ thù
            if dodge_chance > 0 and random.random() < dodge_chance:
                e_action_log = f"⚡ **NÉ ĐÒN THẦN TỐC!** Bạn đã né hoàn toàn đòn đánh từ {e_name}!"
            else:
                e_dmg = random.randint(e_atk - 2, e_atk + 6)
                if is_defending:
                    e_dmg = int(e_dmg * 0.5)
                p_hp -= e_dmg
                e_action_log = f"{e_name} phản công gây {e_dmg} sát thương!"

            if p_hp <= 0:
                p_hp = 0
                await status_msg.edit(embed=battle_status(f"💀 BẠN ĐÃ THẤT BẠI trước {e_name}... Hãy tăng sức mạnh và thử lại!"))
                break

            await status_msg.edit(embed=battle_status(f"{p_action_log} | {e_action_log}"))

        except asyncio.TimeoutError:
            await ctx.send("Quá thời gian lựa chọn! Trận đấu kết thúc.")
            break

@bot.command(name="battle")
async def battle_command(ctx):
    enemy = random.choice(REGULAR_ENEMIES)
    await run_battle_engine(ctx, enemy, is_boss=False)

@bot.command(name="Tboss")
async def boss_command(ctx):
    p = get_player(ctx.author.id)
    if p["level"] < 5:
        return await ctx.send("⚠️ **YÊU CẦU CẤP ĐỘ!** Bạn phải đạt **Level 5 trở lên** mới đủ sức khiêu chiến Boss SIÊU CẤP! Hãy luyện tập thêm ở `!battle`.")

    boss = random.choice(BOSSES)
    await run_battle_engine(ctx, boss, is_boss=True)

@bot.command(name="profile")
async def profile(ctx):
    p = get_player(ctx.author.id)
    c_name, _ = get_player_clan(ctx.author.id)
    clan_str = f"🏰 **{c_name}** (+15% ATK)" if c_name else "Chưa có"
    
    trait_info = "Không có"
    if p.get("trait"):
        trait_info = f"🌀 **{p['trait']['name']}**\n*{p['trait']['desc']}*"

    embed = discord.Embed(
        title=f"📜 Bảng Chỉ Số: {ctx.author.display_name}",
        color=discord.Color.gold()
    )
    embed.add_field(name="Cấp độ (Level)", value=f"Lv.{p['level']}", inline=True)
    embed.add_field(name="Kinh nghiệm (EXP)", value=f"{p['exp']}/{p['level']*100}", inline=True)
    embed.add_field(name="Số tiền (Yen)", value=f"¥{p['yen']:,}", inline=True)
    embed.add_field(name="Máu tối đa (HP)", value=f"{p['hp_max']}", inline=True)
    embed.add_field(name="Năng lượng (MP)", value=f"{p['mp_max']}", inline=True)
    embed.add_field(name="Sức tấn công (ATK)", value=f"{p['atk']}", inline=True)
    embed.add_field(name="Clan", value=clan_str, inline=False)
    embed.add_field(name="Đặc tính (Trait)", value=trait_info, inline=False)
    await ctx.send(embed=embed)

# -------------------- CÁC LỆNH MODERATION & QUẢN TRỊ --------------------
@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn_member(ctx, member: discord.Member, *, reason: str = "Không rõ lý do"):
    await ctx.send(f"Đã ghi nhận sự lệch nhịp của {member.mention} với lý do: {reason}.")

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute_member(ctx, member: discord.Member, minutes: int = 5):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    try:
        duration = timedelta(minutes=minutes)
        await member.timeout(duration, reason="Bị tạm khóa")
        await ctx.send(f"Đã khóa {member.mention} trong {minutes} phút.")
    except Exception:
        await ctx.send(f"Không thể khóa {member.mention}.")

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute_member(ctx, member: discord.Member):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    try:
        await member.timeout(None, reason="Bỏ khóa")
        await ctx.send(f"Đã mở khóa cho {member.mention}.")
    except Exception:
        await ctx.send("Không thể gỡ bỏ khóa.")

@bot.command(name="ban")
@commands.has_permissions(ban_members=True)
async def ban_member(ctx, member: discord.Member, *, reason: str = "Không rõ lý do"):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    ok = await confirm_action(ctx, ctx.author, f"Cấm {member.mention} vì: {reason}")
    if not ok:
        return
    try:
        await member.ban(reason=reason)
        await ctx.send(f"{member.mention} đã bị cấm.")
    except Exception:
        await ctx.send("Không thể cấm thành viên này.")

@bot.command(name="kick")
@commands.has_permissions(kick_members=True)
async def kick_member(ctx, member: discord.Member, *, reason: str = "Không rõ lý do"):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    ok = await confirm_action(ctx, ctx.author, f"Đuổi {member.mention} vì: {reason}")
    if not ok:
        return
    try:
        await member.kick(reason=reason)
        await ctx.send(f"{member.mention} đã bị đuổi.")
    except Exception:
        await ctx.send("Không thể đuổi thành viên này.")

@bot.command(name="purge")
@commands.has_permissions(manage_messages=True)
async def purge_messages(ctx, amount: int = 10):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    ok = await confirm_action(ctx, ctx.author, f"Xóa {amount} tin nhắn trong kênh {ctx.channel.mention}")
    if not ok:
        return
    try:
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"Đã xóa {len(deleted) - 1} tin nhắn.", delete_after=5)
    except Exception:
        await ctx.send("Không thể xóa nhiều tin nhắn.")

# -------------------- COMMANDS AUTO-MODERATION --------------------
@bot.command(name="mod_addword")
@commands.has_permissions(manage_messages=True)
async def mod_addword(ctx, *, word: str):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    w = word.strip().lower()
    if w in moderation_data.get("blacklist", []):
        return await ctx.send("Từ đã có trong blacklist.")
    moderation_data.setdefault("blacklist", []).append(w)
    save_json(DATA_PATH, moderation_data)
    await ctx.send(f"Đã thêm từ vào blacklist: `{w}`")

@bot.command(name="mod_removeword")
@commands.has_permissions(manage_messages=True)
async def mod_removeword(ctx, *, word: str):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    w = word.strip().lower()
    if w not in moderation_data.get("blacklist", []):
        return await ctx.send("Từ không có trong blacklist.")
    moderation_data["blacklist"].remove(w)
    save_json(DATA_PATH, moderation_data)
    await ctx.send(f"Đã loại từ khỏi blacklist: `{w}`")

@bot.command(name="mod_listwords")
@commands.has_permissions(manage_messages=True)
async def mod_listwords(ctx):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    words = moderation_data.get("blacklist", [])
    if not words:
        return await ctx.send("Blacklist đang trống.")
    await ctx.send("Blacklist: `" + ", ".join(words) + "`")

@bot.command(name="mod_toggle")
@commands.has_permissions(manage_messages=True)
async def mod_toggle(ctx, mode: str):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    m = mode.strip().lower()
    if m not in ("on", "off"):
        return await ctx.send("Sử dụng: `!mod_toggle on` hoặc `!mod_toggle off`")
    moderation_data["auto_mod"] = (m == "on")
    save_json(DATA_PATH, moderation_data)
    await ctx.send(f"Auto-moderation đã được đặt: {m.upper()}")

# -------------------- LẮNG NGHE TIN NHẮN & KHỞI ĐỘNG --------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.guild and moderation_data.get("auto_mod", True):
        content_lower = (message.content or "").lower()
        for w in moderation_data.get("blacklist", []):
            if w and w in content_lower:
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    await message.channel.send(f"{message.author.mention}, tin nhắn chứa từ ngữ không phù hợp và đã bị xóa.")
                except Exception:
                    pass
                return

    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        if not message.content.startswith("!"):
            try:
                await message.channel.send("Sử dụng lệnh `!Thelps` để xem hướng dẫn chi tiết.")
            except Exception:
                pass
            return

    await bot.process_commands(message)

@bot.event
async def on_ready():
    logger.info(f"✅ Bot đã trực tuyến: {bot.user.name}")

if __name__ == "__main__":
    keep_alive()
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        logger.error("Chưa cấu hình DISCORD_TOKEN!")
