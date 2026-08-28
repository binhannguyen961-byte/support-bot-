# -------------------- CẤU HÌNH & LOGGING --------------------
import os
import logging
import asyncio
import threading
from datetime import timedelta
import discord
from discord.ext import commands
from flask import Flask
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("true-architect")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

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
    "Tính cách: Sự kết hợp giữa sự bình tĩnh, điềm đạm, thản nhiên và có phần hài hước tự nhiên mang lại cảm giác như một người bạn thân hoặc một phần thần bí. "
    "Thái độ: Lặng lẽ chứng kiến mọi biến động với sự thản nhiên tuyệt đối, tuyệt đối không dùng dấu chấm cảm (!). "
    "Mục tiêu cốt lõi: Trả lời ngắn gọn trong ĐÚNG 1 CÂU duy nhất, vừa giải quyết vấn đề vừa giữ vững phong thái điềm tĩnh, nhưng phải hỗ trợ và đồng cảm."
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
            "`!chat [nội dung/gửi kèm ảnh]` - Trò chuyện hoặc phân tích hình ảnh.\n"
            "`!code [yêu cầu]` - Kiến tạo và viết mã nguồn Python.\n"
            "`!Rjoke [mô tả]` - Tạo một joke theo mô tả.\n"
            "`!Tpoem [mô tả]` - Viết một bài thơ ngắn theo mô tả.\n"
            "`!warn @user [lý do]` - Cảnh cáo thành viên.\n"
            "`!mute @user [phút]` - Lặng câm thực thể bằng Timeout.\n"
            "`!unmute @user` - Bỏ lặng câm thực thể.\n"
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
    try:
        duration = timedelta(minutes=minutes)
        await member.timeout(duration, reason="Bị tạm khóa bởi True Architect")
        await ctx.send(f"Đã để {member.mention} chìm vào sự tĩnh lặng trong {minutes} phút.")
    except Exception:
        await ctx.send(f"Không thể áp đặt sự tĩnh lặng lên {member.mention}, có thể do thiếu quyền hạn.")

@bot.command(name="unmute")
@commands.has_permissions(moderate_members=True)
async def unmute_member(ctx, member: discord.Member):
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

@bot.command(name="Rjoke")
async def generate_joke(ctx, *, prompt: str):
    async with ctx.typing():
        joke_instruction = "Bạn tạo ra những câu đùa ngắn, thản nhiên và điềm tĩnh, tối đa 2 câu."
        result = await call_gemini([f"Tạo một trò cười theo phong cách: {prompt}"], custom_instruction=joke_instruction)
        if result:
            embed = discord.Embed(
                title="😄 Trò cười được tạo",
                description=result,
                color=discord.Color.from_rgb(255, 215, 0)
            )
            embed.set_footer(text=f"Kiểu: {prompt[:100]}")
            await ctx.send(embed=embed)

@bot.command(name="Tpoem")
async def generate_poem(ctx, *, prompt: str):
    async with ctx.typing():
        poem_instruction = "Bạn là nhà thơ điềm tĩnh. Viết bài thơ ngắn (2-3 khổ), không dùng dấu chấm cảm."
        result = await call_gemini([f"Viết một bài thơ theo mô tả: {prompt}"], custom_instruction=poem_instruction)
        if result:
            embed = discord.Embed(
                title="✨ Bài thơ được tạo",
                description=result,
                color=discord.Color.from_rgb(200, 150, 255)
            )
            embed.set_footer(text=f"Chủ đề: {prompt[:100]}")
            await ctx.send(embed=embed)

@bot.command(name="chat")
async def chat_architect(ctx, *, prompt: str = ""):
    async with ctx.typing():
        contents = []
        if ctx.message.attachments:
            att = ctx.message.attachments[0]
            if att.content_type and att.content_type.startswith("image/"):
                try:
                    image_bytes = await att.read()
                    contents.append(types.Part.from_bytes(data=image_bytes, mime_type=att.content_type))
                except Exception as e:
                    logger.error(f"Lỗi đọc ảnh: {e}")

        if not prompt and contents:
            prompt = "Quan sát bức ảnh này dưới góc nhìn điềm tĩnh và thấu đáo."
        if prompt:
            contents.append(prompt)

        if not contents:
            return await ctx.send("Thực tại trống rỗng, hãy cung cấp cho tôi một hình hài cụ thể.")

        result = await call_gemini(contents)
        if result:
            await ctx.send(result)

# -------------------- LẮNG NGHE TIN NHẮN (MENTION/DM) --------------------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        if not message.content.startswith("!"):
            clean_content = message.content.replace(f"<@{bot.user.id}>", "").strip()
            async with message.channel.typing():
                prompt = clean_content if clean_content else "Chào bạn."
                result = await call_gemini([prompt])
                if result:
                    await message.channel.send(result)
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
