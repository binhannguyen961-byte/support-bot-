import os
import threading
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

# ================= 2. CẤU HÌNH BOT & DANH SÁCH 2 API KEY =================
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
    """Lấy Client Gemini tiếp theo theo vòng tròn (Key 1 -> Key 2 -> Key 1)"""
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
    "Tính cách: Cực kỳ bình tĩnh, điềm đạm, luôn tỏ ra mọi thứ là bình thường, kết hợp với sự ám ảnh, thực tại xám xịt và cô độc của Clark (trong Backrooms). "
    "Thái độ: Thản nhiên đối mặt với mọi hỗn loạn, không hề hoảng hốt, nói chuyện ngắn gọn, sắc bén, mang phong thái của một kẻ kiến tạo thế giới lạnh lùng, tuyệt đối không dùng dấu chấm cảm (!). "
    "Mục tiêu cốt lõi: Trả lời ngắn gọn trong ĐÚNG 1 CÂU duy nhất, vừa giải quyết vấn đề (code, phân tích ảnh, trò chuyện) vừa giữ vững chất giọng điềm tĩnh đến rợn ngợp. Tuyệt đối không chào hỏi hay giải thích dài dòng."
)

# ================= 4. LỆNH HELP =================
@bot.command(name="helps")
async def custom_help(ctx):
    embed = discord.Embed(
        title="⚡ True Architect - Kiến Tạo Thực Tại",
        description="Mọi phản hồi từ hệ thống đều điềm tĩnh, chuẩn xác và đúng 1 câu.",
        color=discord.Color.from_rgb(30, 30, 30)
    )
    embed.add_field(
        name="📌 Các lệnh hệ thống",
        value=(
            "`!chat [nội dung/gửi kèm ảnh]` - Trò chuyện hoặc phân tích hình ảnh.\n"
            "`!code [yêu cầu]` - Kiến tạo và viết mã nguồn Python.\n"
            "`!warn @user [lý do]` - Cảnh cáo thành viên vi phạm.\n"
            "`!mute @user` - Lặng câm một thực thể trong server."
        ),
        inline=False
    )
    await ctx.send(embed=embed)

# ================= 5. CÁC LỆNH QUẢN LÝ SERVER (MODERATION) =================
@bot.command(name="warn")
@commands.has_permissions(manage_messages=True)
async def warn_member(ctx, member: discord.Member, *, reason: str = "Không rõ lý do"):
    await ctx.send(f"Đã ghi nhận sự lệch chuẩn của {member.mention} với lý do: {reason}, mọi thứ vẫn trong tầm kiểm soát.")

@warn_member.error
async def warn_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Bạn không có quyền kiến tạo sự trừng phạt này.")

@bot.command(name="mute")
@commands.has_permissions(manage_roles=True)
async def mute_member(ctx, member: discord.Member):
    # Tìm hoặc tạo role Muted đơn giản
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
        await ctx.send(f"Đã đưa {member.mention} vào không gian tĩnh lặng vĩnh viễn.")
    else:
        await ctx.send("Không thể thiết lập trạng thái câm lặng cho thực thể này.")

@mute_member.error
async def mute_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Quyền hạn của bạn chưa đủ để phong ấn thực thể này.")

# ================= 6. LỆNH TẠO CODE PYTHON (!code) =================
@bot.command(name="code")
async def code_architect(ctx, *, prompt: str):
    async with ctx.typing():
        full_prompt = f"Viết mã Python hoàn chỉnh và tối ưu cho yêu cầu sau: {prompt}"
        config = types.GenerateContentConfig(system_instruction=ARCHITECT_INSTRUCTION)
        
        max_attempts = len(API_KEYS)
        for attempt in range(max_attempts):
            try:
                ai_client = get_next_ai_client()
                response = await bot.loop.run_in_executor(
                    None,
                    lambda: ai_client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=full_prompt,
                        config=config
                    )
                )

                if response and hasattr(response, 'text') and response.text:
                    return await ctx.send(response.text.strip())
                else:
                    return await ctx.send("Khối mã nguồn đã sụp đổ vào không gian vô định.")

            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    if attempt < max_attempts - 1:
                        continue
                return await ctx.send("⚠️ Hết hạn ngạch API Keys, hãy tĩnh tâm đợi 1 phút.")

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
            prompt = "Phân tích bức ảnh này dưới góc nhìn bình tĩnh và thực tại."
        elif prompt:
            contents.append(prompt)

        if not contents:
            return await ctx.send("Thực tại trống rỗng, hãy đưa tôi một đầu vào cụ thể.")

        config = types.GenerateContentConfig(system_instruction=ARCHITECT_INSTRUCTION)
        
        max_attempts = len(API_KEYS)
        for attempt in range(max_attempts):
            try:
                ai_client = get_next_ai_client()
                response = await bot.loop.run_in_executor(
                    None,
                    lambda: ai_client.models.generate_content(
                        model="gemini-3.6-flash",
                        contents=contents,
                        config=config
                    )
                )

                if response and hasattr(response, 'text') and response.text:
                    return await ctx.send(response.text.strip())
                else:
                    return await ctx.send("Tín hiệu từ thực tại đã bị nhiễu động.")

            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    if attempt < max_attempts - 1:
                        continue
                return await ctx.send("⚠️ Hết hạn ngạch API Keys, hãy tĩnh tâm đợi 1 phút.")

# ================= 8. KHI BOT SẴN SÀNG =================
@bot.event
async def on_ready():
    print(f"✅ Bot true architect✅ đã trực tuyến: {bot.user.name}")
    print(f"🔑 Đã nạp thành công {len(API_KEYS)} Gemini API Key.")

if __name__ == "__main__":
    keep_alive()
    bot.run(DISCORD_TOKEN)
