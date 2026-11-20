# Zepto Stock Alert – Telegram Bot (setup guide)

Ye utility Zepto pe aapke products ka stock check karti hai: Delhi, Haryana, Noida, Ghaziabad aur Jaipur ki
17 locations pe. Jaise hi koi product stock mein aata hai, Telegram channel pe alert jata hai, jisme
product ka naam, link, location aur kitne pieces available hain, sab hota hai.
Log bot ko apna pincode aur apne links dekar personal alerts bhi le sakte hain.

Sab kuch free hai: Python, Playwright, Telegram Bot API aur GitHub Actions (public repo pe free).

---

## Part A – Laptop pe ek baar setup (≈15 min)

Laptop pe sirf setup aur pehla test hoga. Uske baad bot GitHub pe chalega, laptop band bhi rahe toh chalega.

1. **Telegram bot banayein**
   Telegram mein `@BotFather` kholein → `/newbot` → bot ka naam aur username dein.
   BotFather ek **token** dega (jaise `123456:ABC...`). Ise kisi ke saath share na karein.

2. **Setup chalayein**
   Is folder mein `setup_windows.bat` pe double-click karein.
   Ye `.venv` naam ka virtual environment banayega aur sab install karega.

3. **Encryption key banayein**
   Is folder mein Command Prompt kholein aur chalayein:
   ```
   .venv\Scripts\activate
   python main.py genkey
   ```
   Jo lambi key aaye, use copy kar lein.

4. **`.env` file bharein** (Notepad se kholein):
   ```
   BOT_TOKEN=<BotFather wala token>
   STATE_KEY=<step 3 wali key>
   ADMIN_IDS=
   ```

5. **Apni Telegram ID nikaalein**
   Apne bot ko Telegram pe `/myid` bhejein. Phir chalayein:
   ```
   python main.py test-telegram
   ```
   Bot aapko aapki ID bhej dega. Wo ID `.env` mein `ADMIN_IDS=` ke aage likh dein.

6. **Channel banayein**
   Telegram mein New Channel banayein (public ya private). Channel settings → Administrators →
   apne bot ko admin banayein, "Post Messages" ki permission ke saath.
   Phir dobara `python main.py test-telegram` chalayein. Bot aapko "Channel connect ho gaya" bolega,
   aur channel mein ek test message aayega.

7. **Pehla asli check**
   ```
   python main.py once
   ```
   Isme 5–10 minute lagenge. Screen pe har location aur product ka result dikhega (`IN` / `out` / `qty=`).
   Agar koi product kahin stock mein hai, channel pe alert aa jayega.
   Browser khulte hue dekhna ho toh `.env` mein `HEADLESS=0` likh dein.

---

## Part B – GitHub pe 24×7 free chalana (laptop band rahe tab bhi)

1. https://github.com pe free account banayein.
2. **New repository** banayein, type **Public** rakhein. Public repo pe Actions free aur unlimited hain.
   Aapka data (users, links, status) `data/state.enc` mein encrypted rehta hai.
   Key ke bina koi use padh nahi sakta.
3. **Add file → Upload files**, aur is folder ki saari files/folders drag karein, **sirf ye chhod kar**:
   `.env` (isme aapka token hai) aur `.venv` folder.
   `data/state.enc` zaroor upload karein, kyunki isme aapka channel aur settings saved hain.
   ⚠️ `.github` folder bhi upload hona chahiye. Agar drag mein na aaye, toh "Add file → Create new file" mein
   naam `.github/workflows/check.yml` likhein aur us file ka content paste kar dein.
4. Repo → **Settings → Secrets and variables → Actions → New repository secret**, aur ye 3 secrets banayein:
   - `BOT_TOKEN`: aapka token
   - `STATE_KEY`: wahi key jo `.env` mein hai
   - `ADMIN_IDS`: aapki Telegram ID
5. Repo → **Actions** tab → workflows enable karein → "Zepto stock check" → **Run workflow**.
   2–3 minute baad run kholkar log dekhein.
   Agar log mein products ke aage `out` / `IN` dikh rahe hain, toh sab sahi chal raha hai.
   Iske baad ye har 20 minute mein apne aap chalega.

Jab GitHub chalu ho jaye, toh laptop wala `run_local.bat` mat chalaiye, warna dono ka data alag ho jayega.

---

## Bot commands

**Sab users ke liye** (bot ko private message mein):
| Command | Kaam |
|---|---|
| `/start` | help |
| `/pincode 201301` | apna pincode set karein |
| `/add <zepto link> [naam]` | apna product jodein (default limit 5) |
| `/mylist`, `/remove 2`, `/status` | apni list dekhein, hatayein, status dekhein |

**Sirf aapke liye (admin):**
`/addproduct <link> [naam]`, `/products`, `/removeproduct 2`, `/locs`, `/addloc 302017 Jaipur Malviya Nagar`,
`/removeloc 3`, `/users`, `/block <id>`, `/unblock <id>`, `/setlimit 5`, `/overview`

Users ke personal links ke alerts sirf usi user ko jaate hain, channel mein nahi.
Channel mein sirf aapke `/addproduct` wale products ke alerts aate hain.

---

## Dhyan rakhne wali baatein

- **Bot ke jawab der se aate hain:** GitHub pe bot har ~20 minute mein jaagta hai, isliye commands ka jawab
  20 minute tak late aa sakta hai. Telegram messages 24 ghante tak sambhaal kar rakhta hai, toh koi message
  khota nahi hai.
- **Quantity:** Ye wahi number hai jo Zepto apne product page pe rakhta hai. Kabhi-kabhi Zepto ye nahi deta,
  tab alert mein "qty nahi dikhayi" likha aayega.
- **Zepto blocking:** Zepto bot-protection use karta hai. Agar GitHub ke log mein har location pe
  `location error` aaye, toh iska matlab hai ki Zepto GitHub ke servers ko rok raha hai. Tab
  `run_local.bat` chalayein. Ye laptop on rehne tak har 20 minute mein check karega.
- **Zepto website badalne pe:** Agar Zepto apni website badalta hai, toh checker ko update karna padega.
- **Locations badalna:** Bot pe `/addloc` / `/removeloc` use karein.
  (`data/locations.json` sirf pehli baar ke liye starting list hai.)
- Ye tool personal/limited use ke liye hai, isliye check ka interval kam mat karein.
