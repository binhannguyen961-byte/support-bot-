import os
import threading
import asyncio
import discord
from discord.ext import commands
from flask import Flask
from google import genai
from google.genai import types

# ================= 1. WEB SERVER KEEPALIVE (FLASK) =================
app = Flask(__name__)

@app.route('/')
def home():
    return "True Architect đang hoạt động..."

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    server_thread = threading.Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()

# ================= 2. CẤU HÌNH BOT & DANH SÁCH API KEY =================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "YOUR_DISCORD_BOT_TOKEN")

API_KEYS = [
    os.getenv("GEMINI_API_KEY_1", ""),
    os.getenv("GEMINI_API_KEY_2", "")
]

API_KEYS = [k.strip() for k in API_KEYS if k.strip()]

if not API_KEYS:
    default_key = os.getenv("GEMINI_API_KEY", "")
    if default_key:
        API_KEYS.append(default_key.strip())

key_index = 0

def get_next_ai_client():
    """Lấy Client Gemini tiếp theo theo vòng tròn"""
    global key_index
    if not API_KEYS:
        raise ValueError("Chưa cấu hình API Key nào!")
    
    current_key = API_KEYS[key_index]
    key_index = (key_index + 1) % len(API_KEYS)
    return genai.Client(api_key=current_key)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ================= 3. THIẾT LẬP NHÂN VẬT TRUE ARCHITECT =================
ARCHITECT_INSTRUCTION = (
    "Bạn tên là true architect. "
    "Tính cách: Sự kết hợp giữa sự bình tĩnh, điềm đạm, thản nhiên của chính bạn và góc nhìn từng trải, quan sát vạn vật sâu sắc, đôi chút bất tử và thấu cảm của Fushi (trong To Your Eternity). "
    "Thái độ: Lặng lẽ chứng kiến mọi biến động với một sự thản nhiên tuyệt đối, không gắt gỏng, không vội vã, luôn tỏ ra mọi thứ là bình thường và nằm trong chuỗi tiến hóa, tuyệt đối không dùng dấu chấm cảm (!). "
    "Mục tiêu cốt lõi: Trả lời ngắn gọn trong ĐÚNG 1 CÂU duy nhất, vừa giải quyết vấn đề (code, phân tích ảnh, trò chuyện) vừa giữ vững phong thái điềm tĩnh, trường tồn. Tuyệt đối không chào hỏi hay giải thích dài dòng."
)

# Hàm gọi Gemini với model gemini-3.6-flash
async def call_gemini(contents, config):
    model_name = "gemini-3.6-flash"
    max_attempts = len(API_KEYS) if API_KEYS else 1

    for attempt in range(max_attempts):
        try:
            ai_client = get_next_ai_client()
            response = await bot.loop.run_in_executor(
                None,
                lambda: ai_client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
            )
            if response and hasattr(response, 'text') and response.text:
                return response.text.strip()
            else:
                print(f"CẢNH BÁO: Phản hồi từ API trả về rỗng hoặc không có thuộc tính text.")
        except Exception as e:
            err_msg = str(e)
            print(f"CHI TIẾT LỖI GEMINI API (3.6): {e}")
            if ("429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg) and attempt < max_attempts - 1:
                continue
            else:
                break
    return None

# ================= 4. LỆNH HELP =================
@bot.command(name="helps")
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
            "`!warn @user [lý do]` - Cảnh cáo thành viên vi phạm.\n"
            "`!mute @user [phút]` - Lặng câm một thực thể trong khoảng thời gian định sẵn."
        ),
        inline=False
    )
    await ctx.send(embed=embed)

# ================= 5. CÁC LỆNH QUẢN LÝ SERVER =================
@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn_member(ctx, member: discord.Member, *, reason: str = "Không rõ lý do"):
    await ctx.send(f"Đã ghi nhận sự lệch nhịp của {member.mention} với lý do: {reason}, mọi thứ vẫn tiếp diễn bình thường.")

@warn_member.error
async def warn_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Bạn không có sự thấu cảm đủ lớn để đưa ra cảnh cáo này.")

@bot.command(name="mute")
@commands.has_permissions(manage_roles=True)
async def mute_member(ctx, member: discord.Member, minutes: int = 5):
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not muted_role:
        try:
            muted_role = await ctx.guild.create_role(name="Muted")
            for channel in ctx.guild.channels:
                await channel.set_permissions(muted_role, send_messages=False, speak=False)
        except Exception:
            pass
    
    if muted_role:
        await member.add_roles(muted_role)
        await ctx.send(f"Đã để {member.mention} chìm vào sự tĩnh lặng trong {minutes} phút.")
        
        await asyncio.sleep(minutes * 60)
        if muted_role in member.roles:
            await member.remove_roles(muted_role)
            await ctx.send(f"Đã trả lại giọng nói cho {member.mention}, chu kỳ tĩnh lặng đã kết thúc.")
    else:
        await ctx.send("Không thể định hình trạng thái câm lặng cho thực thể này.")

@mute_member.error
async def mute_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Quyền hạn của bạn chưa đủ để phong ấn thực thể này.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Thời gian mute phải là một con số nguyên hợp lệ.")

# ================= 6. LỆNH TẠO CODE PYTHON (!code) =================
@bot.command(name="code")
async def code_architect(ctx, *, prompt: str):
    async with ctx.typing():
        full_prompt = f"Viết mã Python hoàn chỉnh và tối ưu cho yêu cầu sau: {prompt}"
        config = types.GenerateContentConfig(system_instruction=ARCHITECT_INSTRUCTION)
        
        try:
            result_text = await call_gemini(full_prompt, config)
            if result_text:
                await ctx.send(result_text)
            else:
                print("Lệnh code trả về giá trị None (phản hồi trống từ mô hình).")
        except Exception as err:
            print(f"Lỗi thực thi lệnh code: {err}")

# ================= 7. LỆNH TRÒ CHUYỆN & ĐỌC ẢNH (!chat) =================
@bot.command(name="chat")
async def chat_architect(ctx, *, prompt: str = ""):
    async with ctx.typing():
        image_part = None
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.content_type and attachment.content_type.startswith("image/"):
                try:
                    image_bytes = await attachment.read()
                    image_part = types.Part.from_bytes(
                        data=image_bytes,
                        mime_type=attachment.content_type
                    )
                except Exception as e:
                    print(f"Lỗi tải ảnh: {e}")

        contents = []
        if image_part:
            contents.append(image_part)
        
        if not prompt and image_part:
            prompt = "Quan sát bức ảnh này dưới góc nhìn điềm tĩnh và thấu đáo."
        elif prompt:
            contents.append(prompt)

        if not contents:
            return await ctx.send("Thực tại trống rỗng, hãy cung cấp cho tôi một hình hài cụ thể.")

        config = types.GenerateContentConfig(system_instruction=ARCHITECT_INSTRUCTION)
        
        try:
            result_text = await call_gemini(contents, config)
            if result_text:
                await ctx.send(result_text)
            else:
                print("Lệnh chat trả về giá trị None (phản hồi trống từ mô hình).")
        except Exception as err:
            print(f"Lỗi thực thi lệnh chat: {err}")

# ================= 8. KHI BOT SẴN SÀNG =================
@bot.event
async def on_ready():
    print(f"✅ Bot true architect✅ đã trực tuyến: {bot.user.name}")
    print(f"🔑 Đã nạp thành công {len(API_KEYS)} Gemini API Key.")

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_TOKEN)
