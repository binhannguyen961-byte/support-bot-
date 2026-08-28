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
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("true-architect")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_IDS = set()
if os.getenv("OWNER_IDS"):
    try:
        OWNER_IDS = set(int(x.strip()) for x in os.getenv("OWNER_IDS").split(",") if x.strip())
    except Exception:
        OWNER_IDS = set()

API_KEYS = []
for i in range(1, 6):
    k = os.getenv(f"GEMINI_API_KEY_{i}")
    if k and k.strip():
        API_KEYS.append(k.strip())

if not API_KEYS and os.getenv("GEMINI_API_KEY"):
    API_KEYS.append(os.getenv("GEMINI_API_KEY").strip())

key_index = 0
def get_next_client():
    global key_index
    if not API_KEYS:
        return None
    key = API_KEYS[key_index]
    key_index = (key_index + 1) % len(API_KEYS)
    # Khởi tạo client trực tiếp với api_key chuẩn của SDK google-genai
    return genai.Client(api_key=key)

# -------------------- WEB SERVER KEEPALIVE --------------------
app = Flask(__name__)
@app.route("/")
def home(): return "True Architect đang hoạt động..."

def keep_alive():
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080))), daemon=True).start()

# -------------------- KHỞI TẠO BOT --------------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

ARCHITECT_INSTRUCTION = (
    "Bạn tên là true architect. "
    "Tính cách: Sự kết hợp giữa sự bình tĩnh, điềm đạm, thản nhiên và có phần hài hước tự nhiên mang lại cảm giác như một người bạn thân hoặc một ph[...]"
    "Thái độ: Lặng lẽ chứng kiến mọi biến động với sự thản nhiên tuyệt đối, tuyệt đối không dùng dấu chấm cảm (!). "
    "Mục tiêu cốt lõi: Trả lời ngắn gọn trong ĐÚNG 1 CÂU duy nhất, vừa giải quyết vấn đề vừa giữ vững phong thái điềm tĩnh, nhưng phải hỗ trợ và đồn[...]"
)

# -------------------- HÀM GỌI GEMINI ĐA KEY --------------------
async def call_gemini(contents, custom_instruction=None, temperature=0.2):
    if not API_KEYS:
        logger.error("Không tìm thấy GEMINI_API_KEY nào trong biến môi trường!")
        return "Chưa cấu hình API Key nào trong hệ thống."
    
    instruction = custom_instruction if custom_instruction else ARCHITECT_INSTRUCTION
    cfg = types.GenerateContentConfig(system_instruction=instruction, temperature=temperature)
    model_name = "gemini-2.0-flash"
    
    for i in range(len(API_KEYS)):
        client = get_next_client()
        if not client:
            continue
            
        try:
            response = await client.aio.models.generate_content(
                model=model_name, 
                contents=contents, 
                config=cfg
            )
            if response and hasattr(response, "text") and response.text:
                return response.text.strip()
        except Exception as e:
            logger.warning(f"API Key thứ {i+1} gặp lỗi: {e}")
            continue
            
    return "Tất cả các API key đều đã cạn kiệt hạn ngạch hoặc gặp lỗi."

# -------------------- LƯU TRỮ DỮ LIỆU MODERATION --------------------
DATA_PATH = "moderation_data.json"
DEFAULT_DATA = {"auto_mod": True, "blacklist": []}

def load_moderation_data():
    if not os.path.exists(DATA_PATH):
        return DEFAULT_DATA.copy()
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Không thể load moderation data: {e}")
        return DEFAULT_DATA.copy()

def save_moderation_data(data):
    try:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"Không thể lưu moderation data: {e}")

moderation_data = load_moderation_data()

# -------------------- TIỆN ÍCH QUYỀN & XÁC NHẬN --------------------
async def is_authorized(ctx):
    # Chủ server hoặc admin, hoặc nằm trong OWNER_IDS env mới được thao tác nhạy cảm
    try:
        if ctx.author.id in OWNER_IDS:
            return True
    except Exception:
        pass
    perms = ctx.author.guild_permissions
    return perms.administrator

async def confirm_action(ctx, action_desc: str, timeout: int = 20):
    """Yêu cầu xác nhận từ người gọi lệnh bằng reaction ✅."""
    confirm_msg = await ctx.send(f"Xác nhận: {action_desc}\nVui lòng phản hồi bằng ✅ trong vòng {timeout} giây để tiếp tục.")
    await confirm_msg.add_reaction("✅")

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) == "✅" and reaction.message.id == confirm_msg.id

    try:
        reaction, user = await bot.wait_for('reaction_add', timeout=timeout, check=check)
        return True
    except asyncio.TimeoutError:
        try:
            await confirm_msg.edit(content=f"Hủy: không nhận được xác nhận cho '{action_desc}'.")
        except Exception:
            pass
        return False

# -------------------- CÁC LỆNH HỆ THỐNG --------------------
@bot.command(name="Thelps")
async def custom_help(ctx):
    embed = discord.Embed(
        title="⚡ True Architect - Tiến Hóa & Kiến Tạo",
        description="Mọi phản hồi từ hệ thống đều điềm tĩnh, trường tồn và đúng 1 câu.",
        color=discord.Color.from_rgb(30, 30, 30)
    )
    embed.add_field(
        name="📌 Các lệnh hệ thống",
        value=(
            "`!rps [rock/paper/scissors]` - Chơi kéo-búa-bao với bot.\n"
            "`!guess start` - Bắt đầu trò đoán số (1-100). Dùng `!guess <số>` để đoán.\n"
            "`!trivia` - Trả lời câu hỏi ngắn.\n"
            "`!code [yêu cầu]` - Kiến tạo và viết mã nguồn Python.\n"
            "`!warn @user [lý do]` - Cảnh cáo thành viên.\n"
            "`!mute @user [phút]` - Tạm khóa thành viên (timeout).\n"
            "`!unmute @user` - Bỏ timeout.\n"
            "`!ban @user [lý do]` - Cấm thành viên (cần xác nhận).\n"
            "`!kick @user [lý do]` - Đuổi thành viên (cần xác nhận).\n"
            "`!purge [số lượng]` - Xoá nhiều tin nhắn (cần xác nhận).\n"
            "`!create_channel [tên]` - Tạo kênh text mới.\n"
            "`!give_role @user [tên role]` - Gán role cho thành viên.\n"
            "`!remove_role @user [tên role]` - Gỡ role khỏi thành viên.\n"
            "`!set_builder @user` - Gán role Builder.\n"
            "`!remove_builder @user` - G��� role Builder.\n"
            "`!mod_addword [từ]` - Thêm từ vào blacklist auto-moderation.\n"
        ),
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn_member(ctx, member: discord.Member, *, reason: str = "Không rõ lý do"):
    await ctx.send(f"Đã ghi nhận sự lệch nhịp của {member.mention} với lý do: {reason}, mọi thứ vẫn tiếp diễn bình thường.")

@bot.command(name="mute")
@commands.has_permissions(moderate_members=True)
async def mute_member(ctx, member: discord.Member, minutes: int = 5):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    try:
        duration = timedelta(minutes=minutes)
        await member.timeout(duration, reason="Bị tạm khóa bởi True Architect")
        await ctx.send(f"Đã để {member.mention} chìm vào sự tĩnh lặng trong {minutes} phút.")
    except Exception:
        await ctx.send(f"Không thể áp đặt sự tĩnh lặng lên {member.mention}, có thể do thiếu quyền hạn.")

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute_member(ctx, member: discord.Member):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    try:
        await member.timeout(None, reason="Bỏ khóa bởi True Architect")
        await ctx.send(f"Đã trả lại giọng nói cho {member.mention}, sự tĩnh lặng đã kết thúc.")
    except Exception:
        await ctx.send(f"Không thể gỡ bỏ sự tĩnh lặng cho {member.mention}.")

@bot.command(name="code")
async def code_architect(ctx, *, prompt: str):
    async with ctx.typing():
        code_instruction = "Bạn là một lập trình viên Python giỏi. Chỉ trả về mã Python hoàn chỉnh, sạch sẽ và tối ưu, không cần giải thích thêm."
        result = await call_gemini([f"Viết mã Python hoàn chỉnh cho: {prompt}"], custom_instruction=code_instruction)
        if result:
            clean_code = result.replace("```python", "").replace("```py", "").replace("```", "").strip()
            await ctx.send(f"```py\n{clean_code}\n```")

# -------------------- LỆNH THAY THẾ MODERATORS & BUILDERS (CÓ XÁC NHẬN) --------------------
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
        await ctx.send(f"{member.mention} đã bị cấm. Lý do: {reason}")
    except Exception as e:
        logger.warning(f"Lỗi khi ban: {e}")
        await ctx.send(f"Không thể cấm {member.mention}. Có thể do quyền hạn.")

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
        await ctx.send(f"{member.mention} đã bị đuổi. Lý do: {reason}")
    except Exception as e:
        logger.warning(f"Lỗi khi kick: {e}")
        await ctx.send(f"Không thể đuổi {member.mention}. Có thể do quyền hạn.")

@bot.command(name="purge")
@commands.has_permissions(manage_messages=True)
async def purge_messages(ctx, amount: int = 10):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    ok = await confirm_action(ctx, f"Xóa {amount} tin nhắn trong kênh {ctx.channel.mention}")
    if not ok:
        return
    try:
        deleted = await ctx.channel.purge(limit=amount)
        await ctx.send(f"Đã xóa {len(deleted)} tin nhắn.", delete_after=5)
    except Exception as e:
        logger.warning(f"Lỗi purge: {e}")
        await ctx.send("Không thể xóa nhiều tin nhắn. Có thể do quyền hạn.")

@bot.command(name="create_channel")
@commands.has_permissions(manage_channels=True)
async def create_channel(ctx, *, name: str):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    guild = ctx.guild
    try:
        channel = await guild.create_text_channel(name)
        await ctx.send(f"Đã tạo kênh {channel.mention}.")
    except Exception as e:
        logger.warning(f"Lỗi tạo channel: {e}")
        await ctx.send("Không thể tạo kênh. Có thể do quyền hạn.")

@bot.command(name="give_role")
@commands.has_permissions(manage_roles=True)
async def give_role(ctx, member: discord.Member, *, role_name: str):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        try:
            role = await guild.create_role(name=role_name)
        except Exception as e:
            logger.warning(f"Lỗi tạo role: {e}")
            return await ctx.send("Không thể tạo role mới. Có thể do quyền hạn.")
    try:
        await member.add_roles(role)
        await ctx.send(f"Đã gán role {role.name} cho {member.mention}.")
    except Exception as e:
        logger.warning(f"Lỗi gán role: {e}")
        await ctx.send("Không thể gán role. Có thể do quyền hạn.")

@bot.command(name="remove_role")
@commands.has_permissions(manage_roles=True)
async def remove_role(ctx, member: discord.Member, *, role_name: str):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        return await ctx.send("Role không tồn tại.")
    try:
        await member.remove_roles(role)
        await ctx.send(f"Đã gỡ role {role.name} khỏi {member.mention}.")
    except Exception as e:
        logger.warning(f"Lỗi gỡ role: {e}")
        await ctx.send("Không thể gỡ role. Có thể do quyền hạn.")

@bot.command(name="set_builder")
@commands.has_permissions(manage_roles=True)
async def set_builder(ctx, member: discord.Member):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    guild = ctx.guild
    role_name = "Builder"
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        try:
            role = await guild.create_role(name=role_name)
        except Exception as e:
            logger.warning(f"Lỗi tạo role Builder: {e}")
            return await ctx.send("Không thể tạo role Builder. Có thể do quyền hạn.")
    try:
        await member.add_roles(role)
        await ctx.send(f"Đã gán Builder cho {member.mention}.")
    except Exception as e:
        logger.warning(f"Lỗi gán Builder: {e}")
        await ctx.send("Không thể gán Builder. Có thể do quyền hạn.")

@bot.command(name="remove_builder")
@commands.has_permissions(manage_roles=True)
async def remove_builder(ctx, member: discord.Member):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    guild = ctx.guild
    role_name = "Builder"
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        return await ctx.send("Role Builder chưa tồn tại.")
    try:
        await member.remove_roles(role)
        await ctx.send(f"Đã gỡ Builder khỏi {member.mention}.")
    except Exception as e:
        logger.warning(f"Lỗi gỡ Builder: {e}")
        await ctx.send("Không thể gỡ Builder. Có thể do quyền hạn.")

# -------------------- COMMANDS FOR AUTO-MODERATION MANAGEMENT --------------------
@bot.command(name="mod_addword")
@commands.has_permissions(manage_messages=True)
async def mod_addword(ctx, *, word: str):
    if not await is_authorized(ctx):
        return await ctx.send("Bạn không có quyền thực hiện lệnh này.")
    w = word.strip().lower()
    if w in moderation_data.get("blacklist", []):
        return await ctx.send("Từ đã có trong blacklist.")
    moderation_data.setdefault("blacklist", []).append(w)
    save_moderation_data(moderation_data)
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
    save_moderation_data(moderation_data)
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
    save_moderation_data(moderation_data)
    await ctx.send(f"Auto-moderation đã được đặt: {m.upper()}")

# -------------------- MINIGAMES --------------------
guess_games = {}  # channel_id -> target_number

@bot.command(name="rps")
async def rps(ctx, choice: str):
    choice = (choice or "").lower()
    options = ["rock", "paper", "scissors"]
    if choice not in options:
        return await ctx.send("Sử dụng: `!rps rock|paper|scissors`")
    bot_choice = random.choice(options)
    outcome = "hòa"
    if choice == bot_choice:
        outcome = "hòa"
    elif (choice == "rock" and bot_choice == "scissors") or (choice == "paper" and bot_choice == "rock") or (choice == "scissors" and bot_choice == "paper"):
        outcome = "bạn thắng"
    else:
        outcome = "bot thắng"
    await ctx.send(f"Bạn: {choice} — Bot: {bot_choice} → Kết quả: {outcome}.")

@bot.command(name="guess")
async def guess(ctx, arg: str):
    # start or number
    ch = ctx.channel.id
    if arg.lower() == "start":
        if ch in guess_games:
            return await ctx.send("Trò chơi đoán số đã diễn ra trong kênh này. Hãy dùng `!guess <số>` để đoán.")
        target = random.randint(1, 100)
        guess_games[ch] = target
        await ctx.send("Bắt đầu trò đoán số! Mình đã nghĩ một số từ 1 đến 100. Hãy dùng `!guess <số>` để đoán.")
        return
    # try parse number
    try:
        num = int(arg)
    except ValueError:
        return await ctx.send("Sử dụng: `!guess start` để bắt đầu hoặc `!guess <số>` để đoán.")
    if ch not in guess_games:
        return await ctx.send("Chưa có trò chơi nào đang diễn ra, dùng `!guess start` để bắt đầu.")
    target = guess_games[ch]
    if num == target:
        await ctx.send(f"Chính xác! {ctx.author.mention} đã đoán đúng: {target}.")
        del guess_games[ch]
    elif num < target:
        await ctx.send("Cao hơn một chút.")
    else:
        await ctx.send("Thấp hơn một chút.")

trivia_questions = [
    ("Thủ đô của Pháp là g��?", "paris"),
    ("Trong lập trình, HTTP viết tắt của gì?", "hypertext transfer protocol"),
    ("Số nguyên tố nhỏ nhất là bao nhiêu?", "2"),
]

@bot.command(name="trivia")
async def trivia(ctx):
    q, a = random.choice(trivia_questions)
    await ctx.send(f"Câu hỏi: {q} (Trả lời trong 20s bằng tin nhắn) ")

    def check(m):
        return m.channel == ctx.channel and m.author == ctx.author

    try:
        msg = await bot.wait_for('message', timeout=20.0, check=check)
        if msg.content.strip().lower() == a:
            await ctx.send("Chính xác! Bạn thật tuyệt.")
        else:
            await ctx.send(f"Sai rồi — đáp án đúng là: {a}")
    except asyncio.TimeoutError:
        await ctx.send(f"Hết giờ — đáp án là: {a}")

# -------------------- LẮNG NGHE TIN NHẮN (MENTION/DM) + AUTO-MODERATION (AI CHAT REMOVED) --------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Auto-moderation: kiểm tra blacklist (chỉ áp dụng trong guild)
    if message.guild and moderation_data.get("auto_mod", True):
        content_lower = (message.content or "").lower()
        for w in moderation_data.get("blacklist", []):
            if w and w in content_lower:
                try:
                    await message.delete()
                except Exception:
                    pass
                # cảnh báo thành viên
                try:
                    await message.channel.send(f"{message.author.mention}, tin nhắn của bạn chứa nội dung không phù hợp và đã bị xóa.")
                except Exception:
                    pass
                # ghi log nếu có kênh mod-log
                mod_log = discord.utils.get(message.guild.text_channels, name="mod-log")
                if mod_log:
                    await mod_log.send(f"Đã xóa tin của {message.author.mention} vì chứa `{w}`: {message.content}")
                return

    # Nếu bot bị mention hoặc DM, không gọi AI nữa — hướng dẫn dùng lệnh
    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        if not message.content.startswith("!"):
            try:
                await message.channel.send("Tính năng chat AI đã bị tắt. Vui lòng dùng các lệnh: !Thelps để xem lệnh, hoặc thử minigames như !rps, !guess, !trivia.")
            except Exception:
                pass
            return

    await bot.process_commands(message)

# -------------------- SỰ KIỆN KHỞI ĐỘNG --------------------
@bot.event
async def on_ready():
    logger.info(f"✅ Bot đã trực tuyến: {bot.user.name}")
    logger.info(f"🔑 Đã nạp thành công {len(API_KEYS)} API Key vào vòng xoay.")

if __name__ == "__main__":
    keep_alive()
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        logger.error("Chưa cấu hình DISCORD_TOKEN!")
