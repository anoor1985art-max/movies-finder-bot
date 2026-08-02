import os
import sys
from dotenv import load_dotenv

# تحميل المتغيرات البيئية من ملف .env
load_dotenv()

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
elif sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")
elif sys.platform.startswith('win'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
import re
import time
import uuid
import threading
import urllib.parse
import requests
from bs4 import BeautifulSoup
import telebot
from telebot import types
from flask import Flask
import google.generativeai as genai
import PIL.Image

# ==========================================
# إعدادات البوت والتوكن
# ==========================================
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "DUMMY_TOKEN").strip()
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


# مجلد الصور ومقاطع التميز المؤقتة
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_images")
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR, exist_ok=True)

# مفتاح API الخاص بـ TMDb العامل المضمون
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "").strip()

# ==========================================
# 1. أوامر البداية والمساعدة
# ==========================================
@bot.message_handler(commands=['start', 'help'])
@bot.message_handler(func=lambda message: message.text and message.text.strip().lower() in ['start', 'help', 'مرحبا', 'أهلا', 'اهلين', 'بداية', 'السلام عليكم', 'هلو'])
def send_welcome(message):
    welcome_text = (
        "🎬 <b>أهلاً بك في بوت الأفلام والمسلسلات والأنمي الذكي!</b> 🍿✨\n\n"
        "أنا مساعدك السينمائي الشامل المجهز بالذكاء الاصطناعي ومحركات البحث الفائقة، وإليك ما يمكنني فعله:\n\n"
        "1️⃣ <b>البحث عن الأفلام والمسلسلات:</b>\n"
        "أرسل اسم أي فيلم أو مسلسل (بالعربية أو الإنجليزية)، أو حتى وصف القصة وسأجلب لك كافة التفاصيل والبوسترات والتقييمات وإعلان اليوتيوب!\n"
        "<i>مثال:</i> <code>أوبنهايمر</code> أو <code>Inception</code> أو <code>فيلم عن غرق سفينة وتيتانيك</code>\n\n"
        "2️⃣ <b>التعرف على مشاهد الأنمي (trace.moe):</b>\n"
        "أرسل لي <b>صورة (لقطة شاشة) أو مقطع مرئي قصير</b> من أي أنمي، وسأخبرك فوراً باسم الأنمي، ورقم الحلقة، والدقيقة بالضبط التي ظهر فيها المشهد مع فيديو استعراضي!\n\n"
        "👇 <i>ابدأ الآن بإرسال اسم فيلم أو صورة مشهد!</i>"
    )
    bot.reply_to(message, welcome_text)

# ==========================================
# 2. التعرف على الصور بالذكاء الاصطناعي (Gemini) ومشاهد الأنمي (trace.moe)
# ==========================================
@bot.message_handler(content_types=['photo', 'video', 'animation'])
def handle_media_search(message):
    if message.photo:
        status_msg = bot.reply_to(message, "🔍 <b>جاري تحليل الصورة والبحث بالذكاء الاصطناعي...</b> ⏳")
    else:
        status_msg = bot.reply_to(message, "🔍 <b>جاري تحليل المشهد والبحث في قواعد بيانات الأنمي العالمية (trace.moe)...</b> ⏳")
        
    threading.Thread(
        target=process_visual_search,
        args=(message, status_msg)
    ).start()

def process_visual_search(message, status_msg):
    chat_id = message.chat.id
    temp_file = None
    try:
        # تحديد معرف الملف بناءً على نوع الوسائط
        if message.photo:
            file_id = message.photo[-1].file_id
            ext = ".jpg"
        elif message.animation:
            file_id = message.animation.file_id
            ext = ".mp4"
        elif message.video:
            file_id = message.video.file_id
            ext = ".mp4"
        else:
            bot.edit_message_text("❌ صيغة الملف غير مدعومة.", chat_id=chat_id, message_id=status_msg.message_id)
            return

        file_info = bot.get_file(file_id)
        downloaded_bytes = bot.download_file(file_info.file_path)
        temp_file = os.path.join(TEMP_DIR, f"{uuid.uuid4().hex[:8]}{ext}")
        with open(temp_file, "wb") as f:
            f.write(downloaded_bytes)

        # إذا كانت صورة، نستخدم Gemini للبحث عن اسم الفيلم/المسلسل
        if message.photo and GEMINI_API_KEY:
            try:
                model = genai.GenerativeModel('gemini-2.5-flash')
                img = PIL.Image.open(temp_file)
                prompt = "هذه صورة من فيلم، مسلسل، أو أنمي. ما هو الاسم الرسمي لهذا العمل باللغة الإنجليزية (أو العربية إذا كان عربياً)؟ أجب فقط باسم العمل دون أي كلمات إضافية."
                response = model.generate_content([prompt, img])
                
                if response and response.text:
                    movie_name = response.text.strip().replace('"', '').replace("'", "")
                    print(f"[GEMINI VISION] Detected movie: {movie_name}")
                    
                    # تمرير الاسم لمحرك البحث النصي العادي لجلب البوستر والتفاصيل
                    bot.edit_message_text(f"🧠 <b>الذكاء الاصطناعي:</b> يبدو أن هذا العمل هو <i>«{movie_name}»</i>\nجاري جلب التفاصيل... 🔍", chat_id=chat_id, message_id=status_msg.message_id)
                    process_movie_search(message, status_msg, movie_name)
                    return
            except Exception as e:
                print(f"[ERROR] Gemini Vision failed: {e}")
                bot.edit_message_text(f"❌ حدث خطأ أثناء تحليل الصورة بالذكاء الاصطناعي.", chat_id=chat_id, message_id=status_msg.message_id)
                return

        # إرسال الصورة/المقطع إلى trace.moe API (في حالة الفيديو أو فشل Gemini أو عدم توفر المفتاح)
        url = "https://api.trace.moe/search?anilistInfo"
        with open(temp_file, "rb") as f:
            response = requests.post(url, files={"file": f}, timeout=30)

        if response.status_code != 200:
            bot.edit_message_text("❌ تعذر الاتصال بخادم التعرف على الأنمي حالياً. حاول لاحقاً.", chat_id=chat_id, message_id=status_msg.message_id)
            return

        data = response.json()
        if "result" not in data or not data["result"]:
            bot.edit_message_text("😕 لم أتمكن من التعرف على هذا المشهد. تأكد أن الصورة واضحة ومن أنمي ياباني معروف.", chat_id=chat_id, message_id=status_msg.message_id)
            return

        best_match = data["result"][0]
        similarity = best_match.get("similarity", 0) * 100
        anilist_info = best_match.get("anilist", {})
        
        title_romaji = isinstance(anilist_info, dict) and anilist_info.get("title", {}).get("romaji") or best_match.get("filename", "بدون عنوان")
        title_native = isinstance(anilist_info, dict) and anilist_info.get("title", {}).get("native") or ""
        title_english = isinstance(anilist_info, dict) and anilist_info.get("title", {}).get("english") or ""
        
        episode = best_match.get("episode", "غير محدد")
        from_sec = int(best_match.get("from", 0))
        to_sec = int(best_match.get("to", 0))
        timestamp_str = f"{from_sec//60}:{from_sec%60:02d} - {to_sec//60}:{to_sec%60:02d}"
        video_url = best_match.get("video")
        image_url = best_match.get("image")

        is_high_confidence = similarity >= 85.0
        confidence_badge = "🟢 تطابق مؤكد الفائق" if is_high_confidence else "🟡 تطابق تقريبي (قد يكون مشهداً مشابهاً)"

        caption_text = (
            f"🎯 <b>تم التعرف على المشهد بنجاح!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📺 <b>اسم الأنمي:</b> <code>{title_romaji}</code>\n"
            f"🇬🇧 <b>الاسم الإنجليزي:</b> {title_english or title_romaji}\n"
            f"🇯🇵 <b>الاسم الأصلي:</b> {title_native}\n\n"
            f"🎞️ <b>رقم الحلقة:</b> الحلقة {episode}\n"
            f"⏱️ <b>توقيت المشهد:</b> {timestamp_str}\n"
            f"📊 <b>نسبة التطابق:</b> {similarity:.1f}% ({confidence_badge})\n"
            f"━━━━━━━━━━━━━━━━━━"
        )

        bot.edit_message_text("📤 <b>جاري إرسال المقطع والمعلومات الآن...</b> ⚡", chat_id=chat_id, message_id=status_msg.message_id)

        # محاولة إرسال فيديو المعاينة للمشهد إن وجد
        if video_url:
            try:
                vid_resp = requests.get(video_url, timeout=15)
                if vid_resp.status_code == 200:
                    bot.send_video(
                        chat_id,
                        vid_resp.content,
                        caption=caption_text,
                        reply_to_message_id=message.message_id
                    )
                    bot.delete_message(chat_id, status_msg.message_id)
                    return
            except Exception:
                pass

        # إذا لم نتمكن من إرسال الفيديو نرسل الصورة أو النص مباشرة
        if image_url:
            bot.send_photo(chat_id, image_url, caption=caption_text, reply_to_message_id=message.message_id)
        else:
            bot.send_message(chat_id, caption_text, reply_to_message_id=message.message_id)
            
        bot.delete_message(chat_id, status_msg.message_id)

    except Exception as e:
        bot.edit_message_text(f"❌ حدث خطأ أثناء تحليل الصورة: {e}", chat_id=chat_id, message_id=status_msg.message_id)
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

# ==========================================
# 3. البحث النصي عن الأفلام والمسلسلات (TMDb / Multi-Engine)
# ==========================================
@bot.message_handler(func=lambda message: message.text and not message.text.startswith('/'))
def handle_text_query(message):
    query = message.text.strip()
    print(f"[SEARCH QUERY] User {message.chat.id} searching for: {query}")
    status_msg = bot.reply_to(message, f"🎬 <b>جاري البحث في قواعد البيانات السينمائية عن:</b> <i>«{query}»</i>... 🔍")
    threading.Thread(
        target=process_movie_search,
        args=(message, status_msg, query)
    ).start()

def smart_plot_fallback(query):
    """محرك بحث ذكي باستخدام Gemini عندما يكتب المستخدم وصفاً أو اسماً غير دقيق للفيلم"""
    try:
        if GEMINI_API_KEY:
            model = genai.GenerativeModel('gemini-2.5-flash')
            prompt = f"أنا أبحث عن فيلم أو مسلسل بناءً على هذا الوصف أو الاسم العام: '{query}'. ما هو الاسم الرسمي الإنجليزي (أو العربي إذا كان عملاً عربياً) لهذا العمل؟ أجب فقط باسم العمل دون أي كلمات إضافية أو مقدمات."
            response = model.generate_content(prompt)
            if response and response.text:
                candidate = response.text.strip().replace('"', '').replace("'", "")
                print(f"[GEMINI] Suggested movie name: {candidate}")
                
                keys_to_try = [TMDB_API_KEY, "15d2ea6d0dc1d476efbca3eba2b9bbfb"]
                for api_k in keys_to_try:
                    if not api_k: continue
                    s_url = f"https://api.themoviedb.org/3/search/multi?api_key={api_k}&language=ar-SA&query={urllib.parse.quote(candidate)}&include_adult=false"
                    r = requests.get(s_url, timeout=8)
                    if r.status_code == 200:
                        items = [item for item in r.json().get('results', []) if item.get('media_type') in ['movie', 'tv']]
                        if items:
                            return items
                    s_url_en = f"https://api.themoviedb.org/3/search/multi?api_key={api_k}&language=en-US&query={urllib.parse.quote(candidate)}&include_adult=false"
                    r_en = requests.get(s_url_en, timeout=8)
                    if r_en.status_code == 200:
                        items_en = [item for item in r_en.json().get('results', []) if item.get('media_type') in ['movie', 'tv']]
                        if items_en:
                            return items_en
        return []
    except Exception as e:
        print(f"[ERROR] Smart fallback (Gemini) failed: {e}")
        return []

def process_movie_search(message, status_msg, query):
    chat_id = message.chat.id
    try:
        keys_to_try = [TMDB_API_KEY, "15d2ea6d0dc1d476efbca3eba2b9bbfb"]
        results = []

        # البحث المباشر بالعربية
        safe_query = urllib.parse.quote(query)
        results_dict = {}
        
        for api_k in keys_to_try:
            if not api_k: continue
            search_url = f"https://api.themoviedb.org/3/search/multi?api_key={api_k}&language=ar-SA&query={safe_query}&include_adult=false"
            resp = requests.get(search_url, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get('results', []):
                    if item.get('media_type') in ['movie', 'tv']:
                        results_dict[item['id']] = item
                if results_dict:
                    break

        # البحث بالإنجليزية لضمان دقة الأسماء
        for api_k in keys_to_try:
            if not api_k: continue
            search_url_en = f"https://api.themoviedb.org/3/search/multi?api_key={api_k}&language=en-US&query={safe_query}&include_adult=false"
            resp_en = requests.get(search_url_en, timeout=15)
            if resp_en.status_code == 200:
                data_en = resp_en.json()
                for item in data_en.get('results', []):
                    if item.get('media_type') in ['movie', 'tv']:
                        if item['id'] not in results_dict:
                            results_dict[item['id']] = item
                        else:
                            results_dict[item['id']]['en_title'] = item.get('title') or item.get('name') or ''
                break

        results = list(results_dict.values())

        # إذا لم نجد بالبحث المباشر، نقوم بتشغيل محرك البحث الذكي للوصف والقصة وربط ويكيبيديا
        if not results:
            try:
                bot.edit_message_text(f"🧠 <b>جاري تشغيل البحث الذكي وربط الموسوعات لـ: «{query}»...</b> 🔍", chat_id=chat_id, message_id=status_msg.message_id)
            except Exception:
                pass
            results = smart_plot_fallback(query)

        if not results:
            msg = (
                f"❌ <b>لم يتم العثور على عنوان مطابق في قاعدة البيانات لـ:</b> «{query}»\n\n"
                f"💡 <b>توضيح مهم:</b>\n"
                f"قاعدة بيانات الأفلام العالمية (TMDb) تتطلب كتابة <b>اسم الفيلم الرسمي</b> وليس وصف القصة الكاملة.\n\n"
                f"🎯 <b>مثال للفيلم الذي تقصده:</b>\n"
                f"الفيلم الذي يتحدث عن سجن الصواريخ الكيميائية المحرمة هو الفيلم الشهير <b>The Rock</b> (الصخرة - 1996).\n"
                f"👉 جرب الآن كتابة: <code>The Rock</code> أو <code>ذا روك</code> وسأجلب لك بوستره وتفاصيله فوراً!"
            )
            bot.edit_message_text(msg, chat_id=chat_id, message_id=status_msg.message_id)
            return

        # تحسين الاختيار: ترتيب النتائج بحيث تكون الأولوية للتطابق التام بالاسم ثم الأكثر شهرة
        query_lower = query.strip().lower()
        def get_score(item):
            t1 = (item.get('title') or item.get('name') or '').lower()
            t2 = (item.get('original_title') or item.get('original_name') or '').lower()
            t3 = item.get('en_title', '').lower()
            is_exact = 1 if (query_lower in [t1, t2, t3]) else 0
            return (is_exact, item.get('popularity', 0.0))
        
        results.sort(key=get_score, reverse=True)
        
        # أخذ النتيجة الأولى مباشرة وعرض تفاصيلها
        best_match = results[0]
        media_type = best_match.get('media_type')
        item_id = best_match.get('id')
        
        bot.edit_message_text("⏳ <b>جاري جلب البوستر السينمائي وملخص القصة...</b> 🍿", chat_id=chat_id, message_id=status_msg.message_id)
        
        # استدعاء دالة عرض التفاصيل فوراً
        send_movie_full_details(chat_id, media_type, item_id, status_msg)
        print(f"[SEARCH SUCCESS] Automatically selected first result for '{query}' to {chat_id}")

    except Exception as e:
        print(f"[SEARCH ERROR] Exception for '{query}': {e}")
        try:
            bot.edit_message_text(f"❌ حدث خطأ أثناء الاتصال بقاعدة البيانات السينمائية: {e}", chat_id=chat_id, message_id=status_msg.message_id)
        except Exception:
            pass

# ==========================================
# 4. معالجة النقرات وجلب تفاصيل الفيلم/المسلسل والبوستر
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("show_"))
def handle_item_details(call):
    parts = call.data.split("_")
    media_type = parts[1] # movie or tv
    item_id = parts[2]
    
    bot.answer_callback_query(call.id, "🎬 جاري جلب التفاصيل والبوستر...")
    status_msg = bot.send_message(call.message.chat.id, "⏳ <b>جاري جلب البوستر السينمائي وملخص القصة...</b> 🍿")
    
    threading.Thread(
        target=send_movie_full_details,
        args=(call.message.chat.id, media_type, item_id, status_msg)
    ).start()

def send_movie_full_details(chat_id, media_type, item_id, status_msg):
    try:
        keys_to_try = [TMDB_API_KEY, "15d2ea6d0dc1d476efbca3eba2b9bbfb"]
        data_en = {}
        data_ar = {}

        # جلب البيانات بالإنجليزية للحصول على الاسم الإنجليزي
        for api_k in keys_to_try:
            if not api_k: continue
            url_en = f"https://api.themoviedb.org/3/{media_type}/{item_id}?api_key={api_k}&language=en-US&append_to_response=credits,videos"
            resp_en = requests.get(url_en, timeout=15)
            if resp_en.status_code == 200:
                data_en = resp_en.json()
                break

        # جلب البيانات بالعربية للحصول على القصة
        for api_k in keys_to_try:
            if not api_k: continue
            url_ar = f"https://api.themoviedb.org/3/{media_type}/{item_id}?api_key={api_k}&language=ar-SA&append_to_response=credits,videos"
            resp = requests.get(url_ar, timeout=15)
            if resp.status_code == 200:
                data_ar = resp.json()
                break
        
        # استخدام القصة العربية، وإذا لم تتوفر نستخدم الإنجليزية
        overview = data_ar.get('overview', '').strip() or data_en.get('overview', '').strip()
        
        # الدمج: الاعتماد على الإنجليزية للاسم، والعربية لبقية التفاصيل الممكنة
        data = data_ar if data_ar else data_en
        
        title = data_en.get('title') or data_en.get('name') or data.get('title') or data.get('name') or 'بدون عنوان'
        original_title = data.get('original_title') or data.get('original_name') or ''
        year = (data.get('release_date') or data.get('first_air_date') or 'غير محدد')[:4]
        rating = data.get('vote_average', 0)
        votes = data.get('vote_count', 0)
        genres = ", ".join([g.get('name', '') for g in data.get('genres', [])]) or "عام"
        
        # أبرز الممثلين
        cast_list = []
        for actor in data.get('credits', {}).get('cast', [])[:4]:
            cast_list.append(actor.get('name', ''))
        cast_str = "، ".join(cast_list) if cast_list else "غير متوفر"

        # رابط الإعلان (Trailer)
        trailer_url = f"https://www.youtube.com/results?search_query={title}+{year}+trailer"
        for video in data.get('videos', {}).get('results', []):
            if video.get('site') == 'YouTube' and video.get('type') in ['Trailer', 'Teaser']:
                trailer_url = f"https://www.youtube.com/watch?v={video.get('key')}"
                break

        # رابط صورة البوستر
        poster_path = data.get('poster_path')
        poster_url = f"https://image.tmdb.org/t/p/w600_and_h900_bestv2{poster_path}" if poster_path else None

        type_label = "🎬 فيلم سينمائي" if media_type == 'movie' else "📺 مسلسل تلفزيوني"

        caption_text = (
            f"🍿 <code>{title}</code> ({year})\n"
            f"<i>(اضغط على الاسم لنسخه)</i>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>النوع:</b> {type_label}\n"
            f"🌟 <b>التقييم:</b> {rating:.1f}/10 ({votes} صوت)\n"
            f"🎭 <b>التصنيف:</b> {genres}\n"
            f"👥 <b>أبرز الأبطال:</b> {cast_str}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📖 <b>القصة والملخص:</b>\n"
            f"<i>{overview or 'لا يوجد ملخص متاح حالياً.'}</i>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 <i>اختر منصة المشاهدة المجانية أو الإعلان من الأزرار أدناه:</i> 👇"
        )

        import urllib.parse
        safe_title = urllib.parse.quote(title)
        safe_query = urllib.parse.quote(f"{title} {year}")

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🎬 مشاهدة الإعلان الترويجي (Trailer) على YouTube", url=trailer_url),
            types.InlineKeyboardButton("🟡 بحث في شبكتي سينمانا (Cinemana)", url=f"https://cinemana.shabakaty.com/search?query={safe_title}"),
            types.InlineKeyboardButton("🔵 بحث في منصة شاهد (Shahid VIP)", url=f"https://shahid.mbc.net/ar/search?q={safe_title}"),
            types.InlineKeyboardButton("🖥️ بحث في فاصل إعلاني (FaselHD)", url=f"https://www.faselhd.ac/?s={safe_title}"),
            types.InlineKeyboardButton("🍿 بحث في إيجي بست (EgyBest)", url=f"https://egybest.com/explore/?q={safe_title}"),
            types.InlineKeyboardButton("⚡ بحث شامل في جوجل عن روابط مجانية", url=f"https://www.google.com/search?q=مشاهدة+وتحميل+فيلم+مسلسل+{safe_query}+مترجم+مجانا")
        )

        if poster_url:
            bot.send_photo(chat_id, poster_url, caption=caption_text, reply_markup=markup)
        else:
            bot.send_message(chat_id, caption_text, reply_markup=markup, disable_web_page_preview=False)

        try:
            bot.delete_message(chat_id, status_msg.message_id)
        except Exception:
            pass

    except Exception as e:
        bot.edit_message_text(f"❌ حدث خطأ أثناء جلب التفاصيل: {e}", chat_id=chat_id, message_id=status_msg.message_id)

# ==========================================
# 5. تشغيل خادم الويب للعمل 24/7 على Render وتشغيل البوت
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "<h1>🎬 Movies and Anime Finder Bot is Online and Alive 24/7!</h1><p>Ready to search movies, series, and anime scenes instantly.</p>"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def run_bot_polling():
    if BOT_TOKEN == "DUMMY_TOKEN":
        print("[WARNING] TELEGRAM_BOT_TOKEN is missing or set to DUMMY_TOKEN. Bot polling will not start.")
        return
    while True:
        try:
            print("[INFO] Movies Bot is polling Telegram...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[ERROR] Movies Bot polling restart due to: {e}")
            time.sleep(5)

# في بيئة Render (عندما يقوم Gunicorn باستيراد التطبيق، فإن __name__ لا يساوي "__main__")
if __name__ != "__main__":
    polling_thread = threading.Thread(target=run_bot_polling, daemon=True)
    polling_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # تشغيل خادم الويب في مسار منفصل محمي
    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port, use_reloader=False), daemon=True)
    flask_thread.start()
    # تشغيل البوت في المسار الرئيسي ليظل يعمل 24/7 ولا يتوقف نهائياً
    run_bot_polling()
