# -------------------- CẤU HÌNH & LOGGING --------------------
import os
import logging
import asyncio
import threading
import json
import random
from datetime import timedelta
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

# -------------------- LƯU TRỮ DỮ LIỆU MODERATION & RPG --------------------
DATA_PATH = "moderation_data.json"
RPG_DATA_PATH = "rpg_data.json"
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
            "inventory": {}
        }
        save_json(RPG_DATA_PATH, rpg_data)
    
    # Đảm bảo có inventory
    if "inventory" not in rpg_data[uid]:
        rpg_data[uid]["inventory"] = {}
        save_json(RPG_DATA_PATH, rpg_data)
        
    return rpg_data[uid]

# -------------------- DANH SÁCH VẬT PHẨM VÀ CỬA HÀNG --------------------
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
    "spidey_mask": {
        "name": "Mặt nạ Nhện Tự chế",
        "price": 2500,
        "desc": "Sản phẩm độ lại từ Spider-Man. Tăng vĩnh viễn +8 ATK.",
        "type": "buff_atk",
        "value": 8
    },
    "ddlc_poem": {
        "name": "Tập thơ bị chỉnh sửa",
        "price": 2000,
        "desc": "Những dòng thơ bí ẩn từ CLB Văn Học. Tăng vĩnh viễn +20 MP Max.",
        "type": "buff_mp_max",
        "value": 20
    },
    "stand_arrow": {
        "name": "Mũi tên Stand Kỳ lạ",
        "price": 8000,
        "desc": "Tàn tích thức tỉnh sức mạnh từ JoJo. Tăng +30 HP Max và +12 ATK vĩnh viễn.",
        "type": "buff_stand",
        "value": 0
    },
    "pan": {
        "name": "Chảo chống dính cũ",
        "price": 200,
        "desc": "Đồ phế liệu thu gom từ gã bán hàng rong. Bán lại lấy chút tiền Yên.",
        "type": "junk",
        "value": 0
    }
}

# -------------------- TIỆN ÍCH QUYỀN & XÁC NHẬN --------------------
async def is_authorized(ctx):
    try:
        if ctx.author.id in OWNER_IDS:
            return True
    except Exception:
        pass
    return ctx.author.guild_permissions.administrator

async def confirm_action(ctx, action_desc: str, timeout: int = 20):
    confirm_msg = await ctx.send(f"Xác nhận: {action_desc}\nVui lòng phản hồi bằng ✅ trong vòng {timeout} giây để tiếp tục.")
    await confirm_msg.add_reaction("✅")

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id

    try:
        await bot.wait_for('reaction_add', timeout=timeout, check=check)
        return True
    except asyncio.TimeoutError:
        try:
            await confirm_msg.edit(content=f"Hủy: không nhận được xác nhận cho '{action_desc}'.")
        except Exception:
            pass
        return False

# -------------------- HỆ THỐNG LỆNH HƯỚNG DẪN --------------------
@bot.command(name="Thelps")
async def custom_help(ctx):
    embed = discord.Embed(
        title="⚡ True Architect - Tiến Hóa & Kiến Tạo",
        description="Hệ thống quản trị và Minigame RPG Turn-Based Crossover.",
        color=discord.Color.from_rgb(30, 30, 30)
    )
    embed.add_field(
        name="🎮 Turn-Based RPG (Multiverse Street)",
        value=(
            "`!battle` - Đụng độ các đối thủ từ JoJo, Yakuza, DDLC, Spider-Verse & Quần chúng.\n"
            "`!profile` - Xem chỉ số cá nhân, cấp độ và tiền Yên."
        ),
        inline=False
    )
    embed.add_field(
        name="🏪 Cửa Hàng & Túi Đồ",
        value=(
            "`!Tshop` / `!Tstore` - Xem danh sách vật phẩm trong cửa hàng.\n"
            "`!Tshop buy <mã_món> [số_lượng]` - Mua vật phẩm từ cửa hàng.\n"
            "`!Tshop sell <mã_món> [số_lượng]` - Bán lại vật phẩm thu về 60% tiền Yên.\n"
            "`!Tinventory` - Xem các vật phẩm đang sở hữu trong túi đồ.\n"
            "`!Tuse <mã_món>` - Sử dụng vật phẩm từ túi đồ."
        ),
        inline=False
    )
    embed.add_field(
        name="📌 Các lệnh quản trị & Hệ thống",
        value=(
            "`!warn @user [lý do]` - Cảnh cáo thành viên.\n"
            "`!mute @user [phút]` - Tạm khóa thành viên.\n"
            "`!unmute @user` - Bỏ khóa thành viên.\n"
            "`!ban @user [lý do]` - Cấm thành viên (cần xác nhận).\n"
            "`!kick @user [lý do]` - Đuổi thành viên (cần xác nhận).\n"
            "`!purge [số lượng]` - Xoá tin nhắn (cần xác nhận).\n"
            "`!create_channel [tên]` - Tạo kênh text mới.\n"
            "`!give_role @user [role]` - Gán role.\n"
            "`!remove_role @user [role]` - Gỡ role.\n"
            "`!set_builder @user` - Gán Builder.\n"
            "`!remove_builder @user` - Gỡ Builder.\n"
            "`!mod_addword [từ]` - Thêm từ vào blacklist.\n"
            "`!mod_removeword [từ]` - Xóa từ khỏi blacklist.\n"
            "`!mod_listwords` - Xem blacklist.\n"
            "`!mod_toggle [on/off]` - Bật/tắt auto-moderation."
        ),
        inline=False
    )
    await ctx.send(embed=embed)

# -------------------- TÍNH NĂNG SHOP, INVENTORY & USE --------------------
@bot.command(name="Tshop", aliases=["Tstore"])
async def shop_command(ctx, action: str = None, item_id: str = None, amount: int = 1):
    p = get_player(ctx.author.id)
    
    # Nếu không có tham số -> Hiển thị danh sách Cửa hàng
    if not action:
        embed = discord.Embed(
            title="🏪 Cửa Hàng Đa Vũ Trụ Kamurocho",
            description=f"Số tiền hiện có: **¥{p['yen']:,}**\nDùng `!Tshop buy <mã_món> [số_lượng]` để mua.",
            color=discord.Color.green()
        )
        for code, info in ITEMS.items():
            embed.add_field(
                name=f"📦 {info['name']} (`{code}`)",
                value=f"Giá: **¥{info['price']:,}**\n*{info['desc']}*",
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
        total_price = item["price"] * amount

        if p["yen"] < total_price:
            return await ctx.send(f"Bạn không đủ tiền Yên! Cần **¥{total_price:,}** nhưng chỉ có **¥{p['yen']:,}**.")

        p["yen"] -= total_price
        inv = p["inventory"]
        inv[item_key] = inv.get(item_key, 0) + amount
        save_json(RPG_DATA_PATH, rpg_data)

        await ctx.send(f"🛍️ Đã mua thành công **{amount}x {item['name']}** với giá **¥{total_price:,}**!")

    elif act == "sell":
        if not item_id or item_id.lower() not in ITEMS:
            return await ctx.send("Mã vật phẩm không hợp lệ! Dùng `!Tinventory` để xem các món bạn có.")
        
        item_key = item_id.lower()
        item = ITEMS[item_key]
        inv = p["inventory"]
        amount = max(1, amount)

        if inv.get(item_key, 0) < amount:
            return await ctx.send(f"Bạn không có đủ **{amount}x {item['name']}** để bán!")

        sell_price = int(item["price"] * 0.6) * amount
        inv[item_key] -= amount
        if inv[item_key] <= 0:
            del inv[item_key]

        p["yen"] += sell_price
        save_json(RPG_DATA_PATH, rpg_data)

        await ctx.send(f"💰 Đã bán **{amount}x {item['name']}** thu về **¥{sell_price:,}**!")
    else:
        await ctx.send("Cú pháp không hợp lệ. Sử dụng `!Tshop buy <mã_món>` hoặc `!Tshop sell <mã_món>`.")

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
        return await ctx.send("Vui lòng nhập mã vật phẩm muốn dùng. VD: `!Tuse stamina`")

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

    # Áp dụng hiệu ứng
    msg = ""
    if itype == "heal_hp":
        msg = f"🥤 Bạn đã dùng **{item['name']}** và hồi phục **+{val} HP**!"
    elif itype == "heal_mp":
        msg = f"🧪 Bạn đã dùng **{item['name']}** và hồi phục **+{val} MP**!"
    elif itype == "buff_atk":
        p["atk"] += val
        msg = f"⚔️ Sức mạnh bộc phát! **{item['name']}** đã tăng vĩnh viễn **+{val} ATK** cho bạn! (ATK hiện tại: {p['atk']})"
    elif itype == "buff_mp_max":
        p["mp_max"] += val
        msg = f"📖 Tâm trí mở rộng! **{item['name']}** đã tăng vĩnh viễn **+{val} MP Max**! (MP Max hiện tại: {p['mp_max']})"
    elif itype == "buff_stand":
        p["hp_max"] += 30
        p["atk"] += 12
        msg = f"✨ Cảm giác kỳ lạ xuất hiện! **{item['name']}** giúp bạn tăng **+30 HP Max** và **+12 ATK**!"
    elif itype == "junk":
        return await ctx.send("Vật phẩm này là phế liệu, không thể dùng! Hãy dùng `!Tshop sell pan` để bán lấy tiền.")

    # Trừ số lượng khỏi túi
    inv[item_key] -= 1
    if inv[item_key] <= 0:
        del inv[item_key]

    save_json(RPG_DATA_PATH, rpg_data)
    await ctx.send(msg)

# -------------------- DANH SÁCH NHÂN VẬT & BATTLE --------------------
ENEMIES = [
    {"name": "Gã Trộm Đồ Lặt Vặt Hẻm Nhỏ", "hp": 70, "atk": 8, "exp": 25, "yen": 400, "desc": "Một gã móc túi lề đường bình thường."},
    {"name": "Lão Bán Mì Chợ Đêm (Side Story)", "hp": 110, "atk": 12, "exp": 45, "yen": 1500, "desc": "Tự dưng đòi quyết đấu bằng vá múc nước dùng!"},
    {"name": "Kẻ Đu Dây Tơ Tằm (OC Spider)", "hp": 100, "atk": 14, "exp": 50, "yen": 800, "desc": "Đeo mặt nạ nhện, bay nhảy linh hoạt và bắn mạng làm chậm."},
    {"name": "Cựu Yakuza Hoàn Lương (Dragon Style)", "hp": 180, "atk": 22, "exp": 90, "yen": 2500, "desc": "Mang hình xăm rồng sau lưng, cú đấm đầy uy lực."},
    {"name": "Tên Cuồng Băng Nhóm Kamurocho", "hp": 140, "atk": 18, "exp": 70, "yen": 1800, "desc": "Cầm gậy bóng chày và cười điên loạn."},
    {"name": "Kẻ Thù Dùng 'Stand' Ẩn Danh", "hp": 150, "atk": 20, "exp": 100, "yen": 2200, "desc": "Có một bóng hình bí ẩn triệu hồi đằng sau gánh chịu đòn đánh!"},
    {"name": "Nữ Sinh Bị Yandere Thao Túng", "hp": 90, "atk": 16, "exp": 60, "yen": 1000, "desc": "Cầm dao rọc giấy với ánh mắt vô hồn, thì thầm những câu thơ kỳ quặc."}
]

@bot.command(name="profile")
async def profile(ctx):
    p = get_player(ctx.author.id)
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
    await ctx.send(embed=embed)

@bot.command(name="battle")
async def start_battle(ctx):
    p = get_player(ctx.author.id)
    enemy_template = random.choice(ENEMIES)
    
    p_hp = p["hp_max"]
    p_mp = p["mp_max"]
    e_name = enemy_template["name"]
    e_hp = enemy_template["hp"]
    e_max_hp = enemy_template["hp"]
    e_atk = enemy_template["atk"]
    e_desc = enemy_template.get("desc", "")
    
    def check_msg(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["1", "2", "3", "4"]

    await ctx.send(f"⚔️ **MỘT TRẬN ĐẤU BẮT ĐẦU!**\nĐối thủ: **{e_name}**\n📝 *{e_desc}*\n(HP: {e_hp} | ATK: {e_atk})")

    def battle_status(log_msg=""):
        embed = discord.Embed(title=f"💥 {ctx.author.display_name} VS {e_name}", color=discord.Color.purple())
        embed.add_field(name=f"👤 {ctx.author.display_name}", value=f"❤️ HP: {p_hp}/{p['hp_max']}\n🧪 MP: {p_mp}/{p['mp_max']}", inline=True)
        embed.add_field(name=f"👹 {e_name}", value=f"❤️ HP: {e_hp}/{e_max_hp}\n⚔️ ATK: {e_atk}", inline=True)
        embed.add_field(
            name="📋 Hành động của bạn:", 
            value="`1` - Đấm thường\n`2` - Tuyệt kỹ Crossover (Tốn 15 MP)\n`3` - Hồi máu (Tốn 20 MP)\n`4` - Thủ thế (Giảm 50% sát thương)", 
            inline=False
        )
        if log_msg:
            embed.set_footer(text=log_msg)
        return embed

    is_defending = False
    status_msg = await ctx.send(embed=battle_status("Chọn lượt của bạn!"))

    while p_hp > 0 and e_hp > 0:
        try:
            msg = await bot.wait_for("message", timeout=30.0, check=check_msg)
            action = msg.content
            try:
                await msg.delete()
            except Exception:
                pass
            
            p_action_log = ""
            is_defending = False

            # Lượt người chơi
            if action == "1":
                dmg = random.randint(p["atk"] - 3, p["atk"] + 5)
                e_hp -= dmg
                p_action_log = f"Bạn vung đấm vào {e_name} gây {dmg} sát thương!"
            elif action == "2":
                if p_mp >= 15:
                    p_mp -= 15
                    dmg = random.randint(int(p["atk"] * 1.8), int(p["atk"] * 2.4))
                    e_hp -= dmg
                    p_action_log = f"🔥 Tuyệt kỹ Ora-Tiger Drop! Gây {dmg} sát thương cực bộc phát!"
                else:
                    p_action_log = "Không đủ MP! Lượt bị trôi qua."
            elif action == "3":
                if p_mp >= 20:
                    p_mp -= 20
                    heal = random.randint(30, 50)
                    p_hp = min(p["hp_max"], p_hp + heal)
                    p_action_log = f"🥤 Bạn uống hộp sữa Stamina, hồi {heal} HP!"
                else:
                    p_action_log = "Không đủ MP! Lượt bị trôi qua."
            elif action == "4":
                is_defending = True
                p_action_log = "🛡️ Bạn tập trung phòng thủ, sẵn sàng chịu đòn!"

            # Kiểm tra kẻ thù bị hạ
            if e_hp <= 0:
                e_hp = 0
                exp_gained = enemy_template["exp"]
                yen_gained = enemy_template["yen"]
                p["exp"] += exp_gained
                p["yen"] += yen_gained
                
                lvl_up_msg = ""
                if p["exp"] >= p["level"] * 100:
                    p["exp"] -= p["level"] * 100
                    p["level"] += 1
                    p["hp_max"] += 20
                    p["mp_max"] += 10
                    p["atk"] += 5
                    lvl_up_msg = f"\n🎉 **BẠN ĐÃ THĂNG CẤP LÊN Lv.{p['level']}!** (HP +20, MP +10, ATK +5)"

                save_json(RPG_DATA_PATH, rpg_data)
                await status_msg.edit(embed=battle_status(f"BẠN ĐÃ THẮNG! Nhận {exp_gained} EXP và ¥{yen_gained:,}{lvl_up_msg}"))
                break

            # Lượt kẻ thù tấn công
            e_dmg = random.randint(e_atk - 2, e_atk + 5)
            if is_defending:
                e_dmg = int(e_dmg * 0.5)
            
            p_hp -= e_dmg
            e_action_log = f"{e_name} phản công gây {e_dmg} sát thương!"

            if p_hp <= 0:
                p_hp = 0
                await status_msg.edit(embed=battle_status(f"BẠN ĐÃ BỊ ĐẢ BẠI... Hãy rèn luyện thêm!"))
                break

            await status_msg.edit(embed=battle_status(f"{p_action_log} | {e_action_log}"))

        except asyncio.TimeoutError:
            await ctx.send("Quá thời gian lựa chọn! Trận đấu đã kết thúc.")
            break

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
    ok = await confirm_action(ctx, f"Cấm {member.mention} vì: {reason}")
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
    ok = await confirm_action(ctx, f"Đuổi {member.mention} vì: {reason}")
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
    ok = await confirm_action(ctx, f"Xóa {amount} tin nhắn trong kênh {ctx.channel.mention}")
    if not ok:
        return
    try:
        deleted = await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"Đã xóa {len(deleted) - 1} tin nhắn.", delete_after=5)
    except Exception:
        await ctx.send("Không thể xóa nhiều tin nhắn.")

@bot.command(name="create_channel")
@commands.has_permissions(manage_channels=True)
async def create_channel(ctx, *, name: str):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    try:
        channel = await ctx.guild.create_text_channel(name)
        await ctx.send(f"Đã tạo kênh {channel.mention}.")
    except Exception:
        await ctx.send("Không thể tạo kênh.")

@bot.command(name="give_role")
@commands.has_permissions(manage_roles=True)
async def give_role(ctx, member: discord.Member, *, role_name: str):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        try:
            role = await ctx.guild.create_role(name=role_name)
        except Exception:
            return await ctx.send("Không thể tạo role.")
    try:
        await member.add_roles(role)
        await ctx.send(f"Đã gán role {role.name} cho {member.mention}.")
    except Exception:
        await ctx.send("Không thể gán role.")

@bot.command(name="remove_role")
@commands.has_permissions(manage_roles=True)
async def remove_role(ctx, member: discord.Member, *, role_name: str):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        return await ctx.send("Role không tồn tại.")
    try:
        await member.remove_roles(role)
        await ctx.send(f"Đã gỡ role {role.name} khỏi {member.mention}.")
    except Exception:
        await ctx.send("Không thể gỡ role.")

@bot.command(name="set_builder")
@commands.has_permissions(manage_roles=True)
async def set_builder(ctx, member: discord.Member):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    role = discord.utils.get(ctx.guild.roles, name="Builder")
    if not role:
        try:
            role = await ctx.guild.create_role(name="Builder")
        except Exception:
            return await ctx.send("Không thể tạo role Builder.")
    try:
        await member.add_roles(role)
        await ctx.send(f"Đã gán Builder cho {member.mention}.")
    except Exception:
        await ctx.send("Không thể gán Builder.")

@bot.command(name="remove_builder")
@commands.has_permissions(manage_roles=True)
async def remove_builder(ctx, member: discord.Member):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    role = discord.utils.get(ctx.guild.roles, name="Builder")
    if not role:
        return await ctx.send("Role Builder chưa tồn tại.")
    try:
        await member.remove_roles(role)
        await ctx.send(f"Đã gỡ Builder khỏi {member.mention}.")
    except Exception:
        await ctx.send("Không thể gỡ Builder.")

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

# -------------------- LẮNG NGHE TIN NHẮN --------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Auto-moderation
    if message.guild and moderation_data.get("auto_mod", True):
        content_lower = (message.content or "").lower()
        for w in moderation_data.get("blacklist", []):
            if w and w in content_lower:
                try:
                    await message.delete()
                except Exception:
                    pass
                try:
                    await message.channel.send(f"{message.author.mention}, tin nhắn của bạn chứa nội dung không phù hợp và đã bị xóa.")
                except Exception:
                    pass
                mod_log = discord.utils.get(message.guild.text_channels, name="mod-log")
                if mod_log:
                    await mod_log.send(f"Đã xóa tin của {message.author.mention} vì chứa `{w}`: {message.content}")
                return

    # Bị mention hoặc DM
    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        if not message.content.startswith("!"):
            try:
                await message.channel.send("Sử dụng lệnh `!Thelps` để xem hướng dẫn lệnh và trải nghiệm Turn-Based RPG.")
            except Exception:
                pass
            return

    await bot.process_commands(message)

# -------------------- SỰ KIỆN KHỞI ĐỘNG --------------------
@bot.event
async def on_ready():
    logger.info(f"✅ Bot đã trực tuyến: {bot.user.name}")

if __name__ == "__main__":
    keep_alive()
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        logger.error("Chưa cấu hình DISCORD_TOKEN!")
