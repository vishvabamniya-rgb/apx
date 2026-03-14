import requests
import json
import cloudscraper
import asyncio
import aiohttp
import base64
import os

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

users = {}

# =============================
# AES DECRYPT
# =============================

def decrypt(enc):
    try:
        enc = b64decode(enc.split(":")[0])

        key = "638udh3829162018".encode()
        iv = "fedcba9876543210".encode()

        cipher = AES.new(key, AES.MODE_CBC, iv)

        data = unpad(cipher.decrypt(enc), AES.block_size)

        return data.decode()

    except:
        return ""


# =============================
# BASE64
# =============================

def decode_base64(s):
    try:
        return base64.b64decode(s).decode()
    except:
        return ""


# =============================
# TOKEN → USERID
# =============================

def get_userid(token):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)

        data = json.loads(base64.urlsafe_b64decode(payload))

        return data["id"]
    except:
        return None


# =============================
# FETCH
# =============================

async def fetch(session, url, headers):

    try:

        timeout = aiohttp.ClientTimeout(total=30)

        async with session.get(url, headers=headers, timeout=timeout) as r:

            if r.status != 200:
                return {}

            text = await r.text()

            return json.loads(text)

    except:
        return {}


# =============================
# PROCESS VIDEO
# =============================

async def process_video(session, api, cid, vid, headers, file, stats):

    r4 = await fetch(
        session,
        f"{api}/get/fetchVideoDetailsById?course_id={cid}&video_id={vid}&ytflag=0&folder_wise_course=0",
        headers
    )

    data = r4.get("data", {})
    title = data.get("Title", "")

    fl = data.get("video_id")

    if fl:

        vid = decrypt(fl)
        line = f"{title}:https://youtu.be/{vid}"

        stats["video"] += 1

        file.write(line + "\n")

    dl = data.get("download_link")

    if dl:

        dl = decrypt(dl)
        line = f"{title}:{dl}"

        stats["pdf"] += 1

        file.write(line + "\n")

    encrypted_links = data.get("encrypted_links", [])

    if encrypted_links:

        a = encrypted_links[0].get("path")
        k = encrypted_links[0].get("key")

        if a:

            da = decrypt(a)

            if k:
                dk = decode_base64(decrypt(k))
                line = f"{title}:{da}*{dk}"
            else:
                line = f"{title}:{da}"

            stats["other"] += 1

            file.write(line + "\n")


# =============================
# EXTRACTOR
# =============================

async def run_extractor(api, login, cid, batch_name):

    stats = {"video":0,"pdf":0,"other":0}

    if "*" in login:

        mobile, password = login.split("*")

        r = requests.post(
            f"{api}/post/userLogin",
            headers={"Auth-Key": "appxapi"},
            data={"email": mobile, "password": password}
        ).json()

        token = r["data"]["token"]
        userid = r["data"]["userid"]

    else:

        token = login
        userid = get_userid(token)

    headers = {
        "Auth-Key": "appxapi",
        "Authorization": token,
        "Client-Service": "Appx",
        "source": "website",
        "User-ID": str(userid)
    }

    safe_name = batch_name.replace("/", "").replace("\\", "").replace(":", "")
    filename = f"{safe_name}.txt"

    async with aiohttp.ClientSession() as session:

        subs = await fetch(
            session,
            f"{api}/get/allsubjectfrmlivecourseclass?courseid={cid}&start=-1",
            headers
        )

        with open(filename,"w",encoding="utf8") as f:

            for sub in subs.get("data",[]):

                sid = sub.get("subjectid")

                topics = await fetch(
                    session,
                    f"{api}/get/alltopicfrmlivecourseclass?courseid={cid}&subjectid={sid}&start=-1",
                    headers
                )

                for t in topics.get("data",[]):

                    tid = t.get("topicid")

                    videos = await fetch(
                        session,
                        f"{api}/get/livecourseclassbycoursesubtopconceptapiv3?courseid={cid}&subjectid={sid}&topicid={tid}&conceptid=&start=-1",
                        headers
                    )

                    for v in videos.get("data",[]):

                        vid = v.get("id")

                        await process_video(session,api,cid,vid,headers,f,stats)

    return filename, stats


# =============================
# START
# =============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id
    users[uid] = {}

    await update.message.reply_text("Send API DOMAIN")


# =============================
# MESSAGE HANDLER
# =============================

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id
    text = update.message.text

    if "api" not in users[uid]:

        users[uid]["api"] = text

        await update.message.reply_text("Send TOKEN or MOBILE*PASSWORD")

        return

    if "login" not in users[uid]:

        users[uid]["login"] = text

        api = users[uid]["api"]
        login = text

        await update.message.reply_text("Fetching Courses...")

        if "*" in login:

            mobile,password = login.split("*")

            r = requests.post(
                f"{api}/post/userLogin",
                headers={"Auth-Key":"appxapi"},
                data={"email":mobile,"password":password}
            ).json()

            token = r["data"]["token"]
            userid = r["data"]["userid"]

        else:

            token = login
            userid = get_userid(token)

        headers = {
            "Auth-Key":"appxapi",
            "Authorization":token,
            "Client-Service":"Appx",
            "source":"website",
            "User-ID":str(userid)
        }

        scraper = cloudscraper.create_scraper()

        mc = scraper.get(
            f"{api}/get/mycoursev2?userid={userid}",
            headers=headers
        ).json()

        courses = mc.get("data",[])

        users[uid]["courses"] = {}

        msg = "Send Course ID\n\n"

        for c in courses:

            cid = str(c["id"])
            name = c["course_name"]

            users[uid]["courses"][cid] = name

            msg += f"{cid} - {name}\n"

        if len(msg) > 4000:

            file="courses.txt"

            with open(file,"w",encoding="utf8") as f:
                f.write(msg)

            await update.message.reply_document(open(file,"rb"))

            os.remove(file)

        else:

            await update.message.reply_text(msg)

        return

    cid = text

    api = users[uid]["api"]
    login = users[uid]["login"]

    courses = users[uid]["courses"]

    if cid not in courses:

        await update.message.reply_text("Invalid Course ID")
        return

    batch_name = courses[cid]

    await update.message.reply_text("Extracting...")

    filename, stats = await run_extractor(api,login,cid,batch_name)

    caption = f"""
Batch : {batch_name}

Total Videos : {stats['video']}
Total PDFs : {stats['pdf']}
Other Files : {stats['other']}
"""

    await update.message.reply_document(open(filename,"rb"),caption=caption)

    os.remove(filename)


# =============================
# RUN BOT
# =============================

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, handle))

app.run_polling()