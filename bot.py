import telebot
import yt_dlp
import os
import requests
import time
import traceback

try:
    import ssl
except ImportError:
    ssl = None  # Handle missing SSL module gracefully

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

if not BOT_TOKEN:
    raise ValueError("Error: BOT_TOKEN is not set. Please configure it as an environment variable.")

bot = telebot.TeleBot(BOT_TOKEN)
user_links = {}

def upload_to_gofile(file_path):
    try:
        server_res = requests.get("https://api.gofile.io/getServer").json()
        server = server_res.get('data', {}).get('server')
        if not server:
            raise ValueError("Failed to fetch server from Gofile API")
        
        with open(file_path, 'rb') as f:
            files = {'file': f}
            res = requests.post(f"https://{server}.gofile.io/uploadFile", files=files).json()
        
        return res.get('data', {}).get('downloadPage')
    except Exception as e:
        print(f'Error: {e}')
        return None

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "مرحبًا! أرسل رابط فيديو (يوتيوب، تيك توك، تيليجرام).")

@bot.message_handler(func=lambda m: True)
def handle_link(message):
    url = message.text.strip()
    if not url.startswith("http"):
        bot.reply_to(message, "أرسل رابط يبدأ بـ http")
        return

    user_links[message.chat.id] = url
    markup = telebot.types.InlineKeyboardMarkup()

    if "tiktok.com" in url:
        markup.add(telebot.types.InlineKeyboardButton("تحميل TikTok", callback_data="tiktok"))
    elif "t.me" in url:
        markup.add(telebot.types.InlineKeyboardButton("تحميل Telegram", callback_data="telegram"))
    else:
        markup.add(
            telebot.types.InlineKeyboardButton("تحميل MP3", callback_data="mp3"),
            telebot.types.InlineKeyboardButton("اختيار الجودة", callback_data="quality")
        )

    bot.send_message(message.chat.id, "اختر طريقة التحميل:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    url = user_links.get(chat_id)
    
    if not url:
        bot.send_message(chat_id, "❌ خطأ: لم يتم العثور على الرابط.")
        return

    try:
        if call.data == "tiktok":
            download_video(chat_id, url, "best")
        elif call.data == "telegram":
            r = requests.get(url)
            with open("tg.mp4", "wb") as f:
                f.write(r.content)
            send_file(chat_id, "tg.mp4")
        elif call.data == "mp3":
            download_audio(chat_id, url)
        elif call.data == "quality":
            show_quality_options(chat_id, url)
        elif call.data.startswith("res_"):
            height = call.data.split("_")[1]
            download_video(chat_id, url, height)
    except Exception as e:
        notify_admin(traceback.format_exc())

def show_quality_options(chat_id, url):
    markup = telebot.types.InlineKeyboardMarkup()
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            res_list = set()
            
            for f in formats:
                h = f.get("height")
                if h and h not in res_list:
                    res_list.add(h)
                    markup.add(telebot.types.InlineKeyboardButton(f"{h}p", callback_data=f"res_{h}"))
        bot.send_message(chat_id, "اختر الجودة:", reply_markup=markup)
    except Exception:
        notify_admin(traceback.format_exc())
        bot.send_message(chat_id, "تعذر استخراج الجودات.")

def download_video(chat_id, url, res):
    bot.send_message(chat_id, "جاري تحميل الفيديو...")
    ydl_opts = {
        'format': f'bestvideo[height={res}]+bestaudio/best/best[height={res}]',
        'outtmpl': '%(title)s.%(ext)s',
        'merge_output_format': 'mp4',
        'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info).replace('.webm', '.mp4')
    send_file(chat_id, filename)

def download_audio(chat_id, url):
    bot.send_message(chat_id, "جاري تحويل الفيديو إلى MP3...")
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
    send_file(chat_id, filename, audio=True)

def send_file(chat_id, path, audio=False):
    try:
        if os.path.getsize(path) > 50 * 1024 * 1024:
            link = upload_to_gofile(path)
            bot.send_message(chat_id, "طلبك كبير، لم نتمكن من إرساله عبر تيليجرام.")
            bot.send_message(chat_id, f"رابط التحميل: {link}")
        else:
            with open(path, "rb") as f:
                if audio:
                    bot.send_audio(chat_id, f)
                else:
                    bot.send_video(chat_id, f)
    except Exception:
        notify_admin(traceback.format_exc())
    finally:
        os.remove(path)

def notify_admin(msg):
    if ADMIN_CHAT_ID:
        try:
            bot.send_message(ADMIN_CHAT_ID, f'''❌ خطأ:
{msg}''')
        except:
            pass

print("✅ البوت يعمل ومتصِل...")

while True:
    try:
        bot.polling()
    except Exception:
        notify_admin(traceback.format_exc())
        time.sleep(5)
