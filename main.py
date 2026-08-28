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
            "inventory": {},
            "last_daily": None,
            "trait": None,
            "quest": None
        }
        save_json(RPG_DATA_PATH, rpg_data)
    
    player = rpg_data[uid]
    fields = {
        "qpoint": 0, "sp": 0, "skills": [], "inventory": {}, 
        "last_daily": None, "trait": None, "quest": None
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

def get_shop_price(base_price, level):
    scale = 1 + (level - 1) * 0.05
    return int(base_price * scale)

# -------------------- HỆ THỐNG SKILL TREE (50 KỸ NĂNG) --------------------
SKILL_TREE = {
    "rest": {"name": "Rest (Tĩnh Tâm)", "cost": 3, "type": "active", "desc": "Hồi 15 MP trong trận đấu.", "val": 15},
    "power_strike": {"name": "Đòn Đánh Uy Lực", "cost": 2, "type": "passive", "desc": "Tăng vĩnh viễn +5 ATK.", "val": 5},
    "vitality": {"name": "Sinh Lực Cường Đại", "cost": 2, "type": "passive", "desc": "Tăng vĩnh viễn +25 HP Max.", "val": 25},
    "meditation": {"name": "Thiền Định", "cost": 2, "type": "passive", "desc": "Tăng vĩnh viễn +15 MP Max.", "val": 15},
}

# Tự động bổ sung đủ 50 kỹ năng vào cây Skill Tree
for i in range(5, 51):
    SKILL_TREE[f"passive_skill_{i}"] = {
        "name": f"Kỹ Năng Thụ Động #{i}",
        "cost": 1 + (i % 4),
        "type": "passive",
        "desc": f"Tăng chỉ số bổ trợ cấp {i} cho nhân vật.",
        "val": i * 2
    }

# -------------------- DANH SÁCH TRAITS & VẬT PHẨM --------------------
BUFF_TRAITS = [
    {"id": "godlike", "name": "神 - Sức Mạnh Thần Thoại", "desc": "+50% ATK và +30% HP Max trong mọi trận đấu."},
    {"id": "speedster", "name": "⚡ Siêu Tốc Độ", "desc": "Có 20% tỷ lệ né hoàn toàn đòn đánh của kẻ thù."},
    {"id": "vampiric", "name": "🦇 Huyết Tộc", "desc": "Hồi lại 20% sát thương gây ra thành HP."}
]

CURSE_TRAITS = [
    {"id": "fragile", "name": "☠️ Cơ Thể Yếu Ớt", "desc": "Giảm 25% HP Max khi bước vào trận đấu."},
    {"id": "sluggish", "name": "🐢 Chậm Chạp", "desc": "Bị mất 10% ATK trong mọi trận chiến."}
]

ITEMS = {
    "stamina": {"name": "Hộp sữa Stamina", "price": 300, "desc": "Hồi 40 HP.", "type": "heal_hp", "value": 40},
    "bento": {"name": "Hộp Bento Kamurocho", "price": 800, "desc": "Hồi 100 HP.", "type": "heal_hp", "value": 100},
    "energy": {"name": "Nước tăng lực Starlight", "price": 500, "desc": "Hồi 35 MP.", "type": "heal_mp", "value": 35},
    "rokaka": {"name": "Trái Rokaka", "price": 5000, "desc": "Tẩy sạch Trait hiện tại.", "type": "reset_trait", "value": 0},
    "mystery_box": {"name": "Hộp bí ẩn", "price": 1250, "desc": "Mở ra ngẫu nhiên 1 - 15,000 Yên.", "type": "mystery_box", "value": 0}
}

REGULAR_ENEMIES = [
    {"name": "Quickbullet", "hp": 110, "atk": 15, "exp": 55, "yen": 1100, "desc": "Kẻ sở hữu tốc độ chớp nhoáng (25% cướp lượt)!", "special": "quickbullet"},
    {"name": "Demonking", "hp": 220, "atk": 20, "exp": 100, "yen": 2200, "desc": "Tự động hồi 90% HP khi dưới 15% máu!", "special": "demonking"},
    {"name": "Gã Trộm Đồ Lặt Vặt Hẻm Nhỏ", "hp": 70, "atk": 8, "exp": 25, "yen": 400, "desc": "Móc túi lề đường."},
    {"name": "Sát Thủ Passione (JoJo Part 5)", "hp": 130, "atk": 16, "exp": 60, "yen": 1200, "desc": "Dùng Stand cận chiến."}
]

BOSSES = [
    {"name": "Superman (DC)", "hp": 950, "atk": 75, "exp": 1200, "yen": 35000, "desc": "Người Đàn Ông Thép!"},
    {"name": "Sentry (Marvel)", "hp": 1050, "atk": 85, "exp": 1500, "yen": 42000, "desc": "Sức mạnh một triệu mặt trời!"},
    {"name": "Void (Marvel)", "hp": 1200, "atk": 95, "exp": 1800, "yen": 50000, "desc": "Thực thể bóng tối hủy diệt!"},
    {"name": "Doomsday (DC)", "hp": 1100, "atk": 80, "exp": 1600, "yen": 45000, "desc": "Quái vật tiến hóa bất tử!"},
    {"name": "Loki (MCU)", "hp": 800, "atk": 65, "exp": 1000, "yen": 30000, "desc": "Vị Thần Lừa Lọc!"},
    {"name": "Ultron (MCU)", "hp": 900, "atk": 70, "exp": 1100, "yen": 32000, "desc": "Trí tuệ nhân tạo Vibranium!"}
]

# -------------------- TIỆN ÍCH QUYỀN & XÁC NHẬN --------------------
async def is_authorized(ctx):
    try:
        if ctx.author.id in OWNER_IDS: return True
    except Exception: pass
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
        except Exception: pass
        return False

# -------------------- NHIỆM VỤ AN NGUYỄN --------------------
def check_quest_progress(p, qtype, amount=1):
    q = p.get("quest")
    if not q or q["completed"]:
        return False

    q["current"] += amount
    if q["current"] >= q["target"]:
        q["completed"] = True
        p["qpoint"] += q["reward_qp"]
        save_json(RPG_DATA_PATH, rpg_data)
        return True
    save_json(RPG_DATA_PATH, rpg_data)
    return False

@bot.command(name="Tquest")
async def quest_command(ctx):
    p = get_player(ctx.author.id)
    now = datetime.utcnow()
    
    if p["quest"]:
        last_time = datetime.fromisoformat(p["quest"]["time"])
        if now - last_time < timedelta(hours=1) and not p["quest"]["completed"]:
            q = p["quest"]
            return await ctx.send(f"📜 **Nhiệm vụ từ An Nguyễn:** {q['desc']}\nThăng tiến: **{q['current']}/{q['target']}** | Phần thưởng: **{q['reward_qp']} Qpoint**")

    # Tạo nhiệm vụ mới mỗi giờ
    q_types = [
        {"type": "damage", "target": 300, "desc": "Gây tổng cộng 300 sát thương lên kẻ địch.", "qp": 50},
        {"type": "win_battle", "target": 5, "desc": "Thắng 5 trận Battle thường.", "qp": 80},
        {"type": "kill_boss", "target": 1, "desc": "Đánh bại Boss 1 lần.", "qp": 120}
    ]
    selected_q = random.choice(q_types)
    p["quest"] = {
        "type": selected_q["type"],
        "target": selected_q["target"],
        "current": 0,
        "desc": selected_q["desc"],
        "reward_qp": selected_q["qp"],
        "time": now.isoformat(),
        "completed": False
    }
    save_json(RPG_DATA_PATH, rpg_data)
    await ctx.send(f"👤 **An Nguyễn giao nhiệm vụ mới:**\n📝 *{selected_q['desc']}*\n🎁 Phần thưởng: **{selected_q['qp']} Qpoint**!")

@bot.command(name="Qshop")
async def qshop_command(ctx, action: str = None, item_code: str = None):
    p = get_player(ctx.author.id)
    
    qitems = {
        "random_trait": {"name": "Thức tỉnh Trait Ngẫu Nhiên", "qp": 300, "desc": "75% nhận Trait xịn, 25% nhận Lời nguyền."},
        "yen_pack": {"name": "Túi 50,000 Yên", "qp": 150, "desc": "Cung cấp ngay 50,000 Yên."},
        "exp_pack": {"name": "Bình 1,000 EXP", "qp": 100, "desc": "Cung cấp ngay 1,000 EXP."},
        "rokaka": {"name": "Trái Rokaka", "qp": 80, "desc": "Dùng để tẩy Trait."}
    }

    if not action or action.lower() != "buy":
        embed = discord.Embed(title="🛍️ Cửa Hàng Nhiệm Vụ An Nguyễn (Qshop)", description=f"Qpoint hiện có: **{p['qpoint']} Qpoint**\nDùng `!Qshop buy <mã_món>` để mua.", color=discord.Color.purple())
        for code, info in qitems.items():
            embed.add_field(name=f"⭐ {info['name']} (`{code}`)", value=f"Giá: **{info['qp']} Qpoint**\n*{info['desc']}*", inline=False)
        return await ctx.send(embed=embed)

    code = item_code.lower() if item_code else ""
    if code not in qitems:
        return await ctx.send("Mã món hàng Qshop không hợp lệ!")

    item = qitems[code]
    if p["qpoint"] < item["qp"]:
        return await ctx.send(f"Bạn không đủ Qpoint! Cần **{item['qp']} Qpoint** nhưng chỉ có **{p['qpoint']}**.")

    p["qpoint"] -= item["qp"]
    if code == "random_trait":
        selected_trait = random.choice(BUFF_TRAITS) if random.random() < 0.75 else random.choice(CURSE_TRAITS)
        p["trait"] = selected_trait
        await ctx.send(f"✨ Bạn đã đổi Trait: **[{selected_trait['name']}]**!")
    elif code == "yen_pack":
        p["yen"] += 50000
        await ctx.send("💰 Bạn nhận được **¥50,000**!")
    elif code == "exp_pack":
        p["exp"] += 1000
        await ctx.send("⚡ Bạn nhận được **1,000 EXP**!")
    elif code == "rokaka":
        p["inventory"]["rokaka"] = p["inventory"].get("rokaka", 0) + 1
        await ctx.send("🍍 Đã thêm **1x Trái Rokaka** vào túi đồ!")

    save_json(RPG_DATA_PATH, rpg_data)

# -------------------- HỆ THỐNG SKILL TREE COMMAND --------------------
@bot.command(name="Tskill")
async def skill_command(ctx, action: str = None, skill_id: str = None):
    p = get_player(ctx.author.id)

    if not action:
        embed = discord.Embed(title="🌳 Cây Kỹ Năng (Skill Tree)", description=f"Skill Point (SP) hiện có: **{p['sp']} SP**\nDùng `!Tskill learn <mã_skill>` để học.", color=discord.Color.green())
        learned = p.get("skills", [])
        for sid, sinfo in list(SKILL_TREE.items())[:10]: # Hiển thị các skill chính
            status = "✅ Đã học" if sid in learned else f"❌ Giá: {sinfo['cost']} SP"
            embed.add_field(name=f"📜 {sinfo['name']} (`{sid}`)", value=f"Loại: {sinfo['type'].upper()} | {status}\n*{sinfo['desc']}*", inline=False)
        embed.set_footer(text="Gợi ý: Dùng !Tskill learn rest để học kỹ năng hồi MP trong trận đấu.")
        return await ctx.send(embed=embed)

    if action.lower() == "learn":
        if not skill_id or skill_id.lower() not in SKILL_TREE:
            return await ctx.send("Mã kỹ năng không hợp lệ!")
        
        sid = skill_id.lower()
        sinfo = SKILL_TREE[sid]

        if sid in p["skills"]:
            return await ctx.send("Bạn đã học kỹ năng này rồi!")
        if p["sp"] < sinfo["cost"]:
            return await ctx.send(f"Bạn không đủ SP! Cần **{sinfo['cost']} SP** nhưng chỉ có **{p['sp']} SP**.")

        p["sp"] -= sinfo["cost"]
        p["skills"].append(sid)

        # Buff trực tiếp chỉ số nếu là passive
        if sinfo["name"] == "Power Strike": p["atk"] += sinfo["val"]
        elif sinfo["name"] == "Vitality": p["hp_max"] += sinfo["val"]
        elif sinfo["name"] == "Meditation": p["mp_max"] += sinfo["val"]

        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send(f"🎉 Bạn đã học thành công kỹ năng **{sinfo['name']}**!")

# -------------------- PVP BET & BATTLE ENGINE --------------------
@bot.command(name="Tpvp")
async def pvp_command(ctx, target: discord.Member = None):
    if not target or target == ctx.author or target.bot:
        return await ctx.send("Vui lòng @người chơi bạn muốn thách đấu PvP!")

    p1 = get_player(ctx.author.id)
    p2 = get_player(target.id)

    ok = await confirm_action(ctx, target, f"{ctx.author.mention} thách đấu PvP với bạn!")
    if not ok:
        return

    p1_hp, p2_hp = p1["hp_max"], p2["hp_max"]
    p1_mp, p2_mp = p1["mp_max"], p2["mp_max"]

    await ctx.send(f"⚔️ **TRẬN THÁCH ĐẤU PVP BẮT ĐẦU!**\n{ctx.author.mention} (HP: {p1_hp}) VS {target.mention} (HP: {p2_hp})")

    turn = 1 # 1: p1, 2: p2
    while p1_hp > 0 and p2_hp > 0:
        attacker_user = ctx.author if turn == 1 else target
        defender_user = target if turn == 1 else ctx.author
        p_atk_data = p1 if turn == 1 else p2

        def check_pvp(m):
            return m.author == attacker_user and m.channel == ctx.channel and m.content in ["1", "2"]

        await ctx.send(f"👉 Lượt của {attacker_user.mention}: Nhập `1` để Đấm, `2` để Dùng Tuyệt kỹ (15 MP)")

        try:
            msg = await bot.wait_for("message", timeout=30.0, check=check_pvp)
            act = msg.content
            dmg = 0

            if act == "1":
                dmg = random.randint(p_atk_data["atk"] - 2, p_atk_data["atk"] + 4)
            elif act == "2":
                curr_mp = p1_mp if turn == 1 else p2_mp
                if curr_mp >= 15:
                    if turn == 1: p1_mp -= 15
                    else: p2_mp -= 15
                    dmg = random.randint(int(p_atk_data["atk"] * 1.6), int(p_atk_data["atk"] * 2.2))
                else:
                    await ctx.send("Không đủ MP! Đòn đánh bị suy giảm.")
                    dmg = 5

            if turn == 1:
                p2_hp -= dmg
                await ctx.send(f"💥 {ctx.author.mention} gây **{dmg} sát thương** lên {target.mention}! (HP còn: {max(0, p2_hp)})")
            else:
                p1_hp -= dmg
                await ctx.send(f"💥 {target.mention} gây **{dmg} sát thương** lên {ctx.author.mention}! (HP còn: {max(0, p1_hp)})")

            if p1_hp <= 0 or p2_hp <= 0:
                winner = ctx.author if p2_hp <= 0 else target
                await ctx.send(f"🏆 **{winner.mention} ĐÃ CHIẾN THẮNG TRONG TRẬN PVP!**")
                break

            turn = 2 if turn == 1 else 1

        except asyncio.TimeoutError:
            await ctx.send(f"Quá thời gian lựa chọn! Trận đấu PvP kết thúc.")
            break

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
        if p["level"] < 3 or p["yen"] < 3000:
            return await ctx.send("⚠️ **YÊU CẦU TẠO CLAN:** Bạn phải đạt **Level 3+** và có ít nhất **3,000 Yên**!")

        clan_title = arg.strip()
        if clan_title in clan_data:
            return await ctx.send("Tên Clan này đã tồn tại, hãy chọn tên khác.")

        p["yen"] -= 3000
        clan_data[clan_title] = {
            "owner": str(ctx.author.id),
            "members": [str(ctx.author.id)]
        }
        save_json(CLAN_DATA_PATH, clan_data)
        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send(f"🎉 Đã tiêu tốn 3,000 Yên và thành lập Clan **{clan_title}** thành công!")

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

# -------------------- HELPER & RPG BATTLE --------------------
@bot.command(name="Thelps")
async def custom_help(ctx):
    embed = discord.Embed(title="⚡ True Architect - Hướng Dẫn Lệnh", color=discord.Color.blue())
    embed.add_field(
        name="🎮 Battle, PvP & Boss",
        value=(
            "`!battle` - Đánh quái thường.\n"
            "`!Tboss` - Đánh Boss (Cần Level 5+).\n"
            "`!Tpvp @user` - Thách đấu PvP người chơi khác.\n"
            "`!Tquest` - Nhận nhiệm vụ mỗi giờ từ An Nguyễn.\n"
            "`!Qshop` - Cửa hàng đổi Qpoint lấy Trait/Yên/EXP.\n"
            "`!Tskill` - Xem và học kỹ năng từ Skill Tree."
        ),
        inline=False
    )
    embed.add_field(
        name="🏰 Clan & Kinh Tế",
        value=(
            "`!Tclan create <tên>` - Tạo Clan (Cần Lv3+ và 3,000 Yên).\n"
            "`!Tshop` / `!Tinventory` / `!Tuse <món>` - Cửa hàng & Túi đồ.\n"
            "`!profile` - Xem chỉ số, Qpoint, Skill Points."
        ),
        inline=False
    )
    await ctx.send(embed=embed)

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
            return await ctx.send(f"⏳ Bạn đã nhận quà rồi! Quay lại sau **{hours}h {minutes}m {seconds}s**.")

    reward_yen = 1000 + (p["level"] * 250)
    reward_exp = 50 + (p["level"] * 15)

    p["yen"] += reward_yen
    p["exp"] += reward_exp
    p["last_daily"] = now.isoformat()

    save_json(RPG_DATA_PATH, rpg_data)
    await ctx.send(f"🎁 **QUÀ HẰNG NGÀY!** Nhận **¥{reward_yen:,}** và **{reward_exp} EXP**!")

@bot.command(name="profile")
async def profile(ctx):
    p = get_player(ctx.author.id)
    c_name, _ = get_player_clan(ctx.author.id)
    clan_str = f"🏰 **{c_name}** (+15% ATK)" if c_name else "Chưa có"
    
    trait_info = "Không có"
    if p.get("trait"):
        trait_info = f"🌀 **{p['trait']['name']}**\n*{p['trait']['desc']}*"

    embed = discord.Embed(title=f"📜 Bảng Chỉ Số: {ctx.author.display_name}", color=discord.Color.gold())
    embed.add_field(name="Level", value=f"Lv.{p['level']} (SP: {p['sp']})", inline=True)
    embed.add_field(name="EXP", value=f"{p['exp']}/{p['level']*100}", inline=True)
    embed.add_field(name="Yên", value=f"¥{p['yen']:,}", inline=True)
    embed.add_field(name="Qpoint", value=f"⭐ {p['qpoint']} QP", inline=True)
    embed.add_field(name="HP Max", value=f"{p['hp_max']}", inline=True)
    embed.add_field(name="ATK", value=f"{p['atk']}", inline=True)
    embed.add_field(name="Clan", value=clan_str, inline=False)
    embed.add_field(name="Đặc tính (Trait)", value=trait_info, inline=False)
    await ctx.send(embed=embed)

async def run_battle_engine(ctx, enemy_data, is_boss=False):
    p = get_player(ctx.author.id)
    c_name, _ = get_player_clan(ctx.author.id)

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

    p_trait = p.get("trait")
    dodge_chance = 0.0
    lifesteal = False

    if p_trait:
        tid = p_trait["id"]
        if tid == "godlike": p_atk, p_hp = int(p_atk * 1.5), int(p_hp * 1.3)
        elif tid == "speedster": dodge_chance = 0.20
        elif tid == "vampiric": lifesteal = True
        elif tid == "fragile": p_hp = int(p_hp * 0.75)
        elif tid == "sluggish": p_atk = int(p_atk * 0.9)

    clan_bonus = 1.15 if c_name else 1.0
    effective_atk = int(p_atk * clan_bonus)

    def check_msg(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["1", "2", "3", "4", "5"]

    prefix = "🔥 **TRẬN ĐẤU BOSS SIÊU CẤP** 🔥" if is_boss else "⚔️ **BATTLE THƯỜNG**"
    await ctx.send(f"{prefix}\nĐối thủ: **{e_name}** (HP: {e_hp} | ATK: {e_atk})")

    def battle_status(log_msg=""):
        embed = discord.Embed(title=f"💥 {ctx.author.display_name} VS {e_name}", color=discord.Color.purple())
        embed.add_field(name=f"👤 {ctx.author.display_name}", value=f"❤️ HP: {p_hp}/{p['hp_max']}\n🧪 MP: {p_mp}/{p['mp_max']}\n⚔️ ATK: {effective_atk}", inline=True)
        embed.add_field(name=f"👹 {e_name}", value=f"❤️ HP: {e_hp}/{e_max_hp}\n⚔️ ATK: {e_atk}", inline=True)
        
        has_rest = "rest" in p.get("skills", [])
        rest_str = "\n`5` - Rest (Hồi 15 MP)" if has_rest else ""
        embed.add_field(name="📋 Hành động:", value=f"`1` - Đấm\n`2` - Tuyệt kỹ (15 MP)\n`3` - Hồi máu (20 MP)\n`4` - Phòng thủ{rest_str}", inline=False)
        if log_msg: embed.set_footer(text=log_msg)
        return embed

    status_msg = await ctx.send(embed=battle_status("Chọn lượt của bạn!"))

    while p_hp > 0 and e_hp > 0:
        if e_special == "quickbullet" and random.random() < 0.25:
            q_dmg = random.randint(e_atk - 2, e_atk + 5)
            p_hp -= q_dmg
            await ctx.send(f"⚡ **Quickbullet cướp lượt!** Gây **{q_dmg} sát thương**!")
            if p_hp <= 0: break

        try:
            msg = await bot.wait_for("message", timeout=30.0, check=check_msg)
            action = msg.content
            try: await msg.delete()
            except Exception: pass
            
            p_action_log = ""
            is_defending = False

            if action == "1":
                dmg = random.randint(effective_atk - 3, effective_atk + 5)
                e_hp -= dmg
                p_action_log = f"Bạn đánh gây {dmg} sát thương!"
                check_quest_progress(p, "damage", dmg)
                if lifesteal: p_hp = min(p["hp_max"], p_hp + int(dmg * 0.2))
            elif action == "2":
                if p_mp >= 15:
                    p_mp -= 15
                    dmg = random.randint(int(effective_atk * 1.8), int(effective_atk * 2.5))
                    e_hp -= dmg
                    p_action_log = f"🔥 Tuyệt kỹ Crossover! Gây {dmg} sát thương!"
                    check_quest_progress(p, "damage", dmg)
                else: p_action_log = "Không đủ MP!"
            elif action == "3":
                if p_mp >= 20:
                    p_mp -= 20
                    heal = random.randint(35, 55)
                    p_hp = min(p["hp_max"], p_hp + heal)
                    p_action_log = f"🥤 Hồi {heal} HP!"
                else: p_action_log = "Không đủ MP!"
            elif action == "4":
                is_defending = True
                p_action_log = "🛡️ Phòng thủ!"
            elif action == "5" and "rest" in p.get("skills", []):
                p_mp = min(p["mp_max"], p_mp + 15)
                p_action_log = "🧘 Dùng kỹ năng Rest hồi +15 MP!"

            if e_special == "demonking" and not demonking_healed and (e_hp / e_max_hp) <= 0.15 and e_hp > 0:
                heal_dk = int(e_max_hp * 0.9)
                e_hp = min(e_max_hp, e_hp + heal_dk)
                demonking_healed = True
                p_action_log += f"\n👿 Demonking hồi {heal_dk} HP!"

            if e_hp <= 0:
                e_hp = 0
                p["exp"] += exp_reward
                p["yen"] += yen_reward
                
                if not is_boss: check_quest_progress(p, "win_battle", 1)
                else: check_quest_progress(p, "kill_boss", 1)

                lvl_up_msg = ""
                if p["exp"] >= p["level"] * 100:
                    p["exp"] -= p["level"] * 100
                    p["level"] += 1
                    p["sp"] += 1
                    p["hp_max"] += 20
                    p["mp_max"] += 10
                    p["atk"] += 5
                    lvl_up_msg = f"\n🎉 **THĂNG CẤP LÊN Lv.{p['level']}!** Nhận +1 Skill Point (SP)!"

                save_json(RPG_DATA_PATH, rpg_data)
                await status_msg.edit(embed=battle_status(f"🎉 CHIẾN THẮNG! Nhận {exp_reward} EXP và ¥{yen_reward:,}{lvl_up_msg}"))
                break

            # Lượt địch
            if dodge_chance > 0 and random.random() < dodge_chance:
                e_action_log = "⚡ Né đòn thành công!"
            else:
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

@bot.command(name="battle")
async def battle_command(ctx):
    enemy = random.choice(REGULAR_ENEMIES)
    await run_battle_engine(ctx, enemy, is_boss=False)

@bot.command(name="Tboss")
async def boss_command(ctx):
    p = get_player(ctx.author.id)
    if p["level"] < 5:
        return await ctx.send("⚠️ Bạn phải đạt **Level 5 trở lên** mới đủ sức đánh Boss!")

    boss = random.choice(BOSSES)
    await run_battle_engine(ctx, boss, is_boss=True)

# -------------------- SHOP & INVENTORY --------------------
@bot.command(name="Tshop", aliases=["Tstore"])
async def shop_command(ctx, action: str = None, item_id: str = None, amount: int = 1):
    p = get_player(ctx.author.id)
    if not action:
        embed = discord.Embed(title="🏪 Cửa Hàng Kamurocho", description=f"Yên hiện có: **¥{p['yen']:,}**", color=discord.Color.green())
        for code, info in ITEMS.items():
            curr_price = get_shop_price(info["price"], p["level"])
            embed.add_field(name=f"📦 {info['name']} (`{code}`)", value=f"Giá: **¥{curr_price:,}**\n*{info['desc']}*", inline=False)
        return await ctx.send(embed=embed)

    if action.lower() == "buy" and item_id in ITEMS:
        item = ITEMS[item_id]
        total_price = get_shop_price(item["price"], p["level"]) * amount
        if p["yen"] < total_price: return await ctx.send("Không đủ Yên!")
        p["yen"] -= total_price
        p["inventory"][item_id] = p["inventory"].get(item_id, 0) + amount
        save_json(RPG_DATA_PATH, rpg_data)
        await ctx.send(f"🛍️ Mua thành công **{amount}x {item['name']}**!")

@bot.command(name="Tinventory")
async def inventory_command(ctx):
    p = get_player(ctx.author.id)
    embed = discord.Embed(title=f"🎒 Túi Đồ Của {ctx.author.display_name}", color=discord.Color.blue())
    for item_key, count in p.get("inventory", {}).items():
        if item_key in ITEMS:
            embed.add_field(name=f"🔹 {ITEMS[item_key]['name']} (`{item_key}`): {count} cái", value=f"*{ITEMS[item_key]['desc']}*", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="Tuse")
async def use_command(ctx, item_id: str = None):
    if not item_id: return await ctx.send("Vui lòng nhập mã món đồ.")
    p = get_player(ctx.author.id)
    item_key = item_id.lower()
    if p["inventory"].get(item_key, 0) <= 0: return await ctx.send("Không có món này trong túi!")

    item = ITEMS[item_key]
    if item["type"] == "reset_trait":
        p["trait"] = None
        await ctx.send("🍍 Đã dùng Rokaka tẩy Trait thành công!")
    elif item["type"] == "mystery_box":
        got_yen = random.randint(1, 15000)
        p["yen"] += got_yen
        await ctx.send(f"🎁 Mở Hộp Bí Ẩn nhận được **¥{got_yen:,}**!")

    p["inventory"][item_key] -= 1
    save_json(RPG_DATA_PATH, rpg_data)

# -------------------- LẮNG NGHE TIN NHẮN & KHỞI ĐỘNG --------------------
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
