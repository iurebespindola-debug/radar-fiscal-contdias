# Fiscal Radar — Contdias

A dashboard that gathers, every day, the most important tax and fiscal news (Federal, State, Municipal, and from the Tax Reform), with special focus on Minas Gerais, São Paulo, and Rio de Janeiro.

You received 3 files:

| File | What it's for |
|---|---|
| `radar_fiscal_contdias.html` | The dashboard itself — this is what you open in the browser |
| `radar_fiscal_scraper.py` | The little program that fetches the news and updates the dashboard |
| `README.md` | This guide |

Keep all three files **in the same folder**.

---

## 1. View the dashboard now (without installing anything)

Double-click the `radar_fiscal_contdias.html` file. It opens in your browser (Chrome, Edge, etc.) and already shows 3 **sample** news items, just so you can see how it looks. To bring in real news, follow step 2.

---

## 2. Install Python (only the first time)

The program that fetches the news needs Python installed on the computer (it's free).

1. Go to **python.org/downloads** and download the version for Windows (or Mac).
2. Install it normally. **Important:** on the first screen of the Windows installer, check the **"Add Python to PATH"** box before clicking Install.
3. To confirm it worked: open **Command Prompt** (Windows) or **Terminal** (Mac) and type:
   ```
   python --version
   ```
   If a version number appears (e.g., `Python 3.12.4`), you're all set.

Then, install two libraries the program uses (you also only need to do this once):

```
pip install requests beautifulsoup4
```

---

## 3. Run the news collection

1. Open Command Prompt/Terminal.
2. Navigate to the folder where the 3 files are. For example, if they're on the desktop:
   ```
   cd Desktop
   ```
3. Run:
   ```
   python radar_fiscal_scraper.py
   ```
4. Wait — it can take 1 to 3 minutes, because it visits several sources (Receita Federal, the Chamber of Deputies, CFC, Contábeis, and the SEFAZ of all 27 states).
5. When it finishes, open (or refresh, if it was already open) `radar_fiscal_contdias.html` in your browser. The real news will replace the sample items.

If a source fails (this is normal — government websites change addresses from time to time), the program **doesn't crash**: it shows `[failed] Source name: reason` on screen, skips that source, and continues normally with the others. If this happens too often with a specific source, let me know and I'll fix its address.

---

## 4. Make this run automatically, every day at 8am

### Windows (Task Scheduler)

1. In the Start menu, search for **"Task Scheduler"** and open it.
2. Click **"Create Basic Task"**.
3. Name: `Contdias Fiscal Radar`.
4. Trigger: **Daily**, time **08:00**.
5. Action: **Start a program**.
   - Program/script: the full path to Python, for example `C:\Users\YourUser\AppData\Local\Programs\Python\Python312\python.exe`
     (to find the exact path, type `where python` in Command Prompt)
   - Arguments: `radar_fiscal_scraper.py`
   - Start in: the folder where the 3 files are, for example `C:\Users\YourUser\Desktop`
6. Finish. Done — the dashboard will update itself every day at 8am (as long as the computer is on at that time).

### Mac / Linux (cron)

1. In Terminal, type `crontab -e`.
2. Add the line (adjusting the folder path):
   ```
   0 8 * * * cd /Users/YourUser/Desktop && /usr/bin/python3 radar_fiscal_scraper.py >> radar_log.txt 2>&1
   ```
3. Save and close. Done.

---

## 5. Put the dashboard online (optional)

If you want a link you can access from anywhere (or send to colleagues):

1. Go to **netlify.com** and create a free account.
2. Drag the `radar_fiscal_contdias.html` file into the area indicated on the site.
3. In seconds you'll get a public link.

**Note:** if you do this, you'll need to upload the file again (drag it again) each time you run `radar_fiscal_scraper.py` and want the online link to show the latest news — automatic updating of the link only happens if you set up something more advanced (I can help you with that later, if you'd like).

---

## 6. Receive the bulletin by email (optional)

The script can send you, every day by email, a summary with only the **high** and **medium** impact news. To enable it:

1. Find out your email provider's SMTP details (Gmail, Outlook, etc. — you'll usually need to create an "app password", not your regular account password).
2. Before running the script, set 5 pieces of information on the computer (on Windows, this is done with the `set` command; on Mac/Linux, with `export`):
   ```
   set RADAR_SMTP_HOST=smtp.gmail.com
   set RADAR_SMTP_PORT=587
   set RADAR_SMTP_USER=youremail@gmail.com
   set RADAR_SMTP_SENHA=your-app-password
   set RADAR_EMAIL_DESTINO=fiscal@contdias.com
   ```
3. Run the script normally. If you want to run it **without** sending an email, use:
   ```
   python radar_fiscal_scraper.py --sem-email
   ```

If these 5 pieces of information aren't set, the script simply won't try to send an email — it keeps working normally, it just won't send the bulletin.

---

## Customizing the dashboard

Once you're already using it, you can come back here to Claude and ask for things like:

- "Add a specific menu for Simples Nacional"
- "Include [URL] in the monitoring"
- "Change the colors to [your colors]"
- "Put the Contdias logo in the header" (then you send the logo image in the chat)
- "Adjust the Tax Reform scoreboard text"

---

## About the monitored sources

**Confirmed and working feeds (RSS):** Receita Federal, Chamber of Deputies, Federal Accounting Council (CFC), Portal Contábeis.

**"Best-effort" sources (generic HTML, no confirmed official RSS):** PGFN, Ministry of Finance, Federal Senate, MAPA, Jornal Contábil, and the 27 state Departments of Finance (SEFAZ) — with extra attention (more news collected) in **MG, SP, and RJ**, as agreed.

Government websites change layout fairly often, so from time to time a source may stop bringing in news — just let me know and I'll fix it.

---

*Original prompt developed by Nathara Muniz (Conta Mais) · Dashboard and script built with Claude (Anthropic) · September/2026*
