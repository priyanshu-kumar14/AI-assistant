import speech_recognition as sr
import pywhatkit
import pyjokes
import datetime
import os
import threading
import time
import webbrowser
import wikipedia
import requests
import json
import psutil
import random
import re
import pvporcupine
import pyaudio
import struct
import audioop
import ollama
import subprocess
import feedparser
import socket as py_socket
from flask import Flask
from flask_socketio import SocketIO

# ─────────────────────────────────────────────
#  FLASK-SOCKETIO SERVER (for React Native app)
# ─────────────────────────────────────────────
flask_app = Flask(__name__)
flask_app.config['SECRET_KEY'] = 'jarvis-secret-v3'
socketio = SocketIO(flask_app, cors_allowed_origins='*', async_mode='threading')

def emit_chat(role, content):
    """Send a chat message to the mobile app"""
    try:
        socketio.emit('chat_message', {'role': role, 'content': content})
    except Exception:
        pass

def emit_state(state):
    """Broadcast AI state: idle, listening, speaking, thinking"""
    try:
        socketio.emit('ai_state', {'state': state})
    except Exception:
        pass

def system_stats_broadcaster():
    """Background thread: sends CPU/RAM/Battery/Disk to app every 2s"""
    while True:
        try:
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent
            bat = psutil.sensors_battery()
            bat_pct = int(bat.percent) if bat else 100
            charging = bat.power_plugged if bat else False
            socketio.emit('sys_stats', {
                'cpu': round(cpu, 1),
                'ram': round(mem, 1),
                'battery': bat_pct,
                'disk': round(disk, 1),
                'charging': charging,
            })
        except Exception:
            pass
        time.sleep(2)

@socketio.on('connect')
def on_connect():
    print('📱 Mobile app connected')
    emit_state('idle')

@socketio.on('control')
def on_control(data):
    action = data.get('action', '')
    if action == 'wake':
        threading.Thread(target=_app_wake, daemon=True).start()
    elif action == 'stop':
        global say_process
        stop_flag.set()
        if say_process and say_process.poll() is None:
            say_process.terminate()
        emit_state('idle')
    elif action == 'text_command':
        text = data.get('text', '').lower().strip()
        if text:
            threading.Thread(target=_app_text_command, args=(text,), daemon=True).start()
    elif action == 'weather':
        threading.Thread(target=lambda: _app_text_command('weather'), daemon=True).start()
    elif action == 'news':
        threading.Thread(target=lambda: _app_text_command('news'), daemon=True).start()
    elif action == 'joke':
        threading.Thread(target=lambda: _app_text_command('joke'), daemon=True).start()
    elif action == 'system_status':
        threading.Thread(target=lambda: _app_text_command('system status'), daemon=True).start()

def _app_wake():
    """App pressed Wake — listen for voice command"""
    if not jarvis_running.is_set():
        return
    talk('Yes Master, how can I help?')
    run_jarvis()

def _app_text_command(text):
    """App sent a text command — run through router without voice"""
    emit_chat('user', text)
    add_to_history('user', text)
    process_command(text)

# ═══════════════════════════════════════════════
#  J.A.R.V.I.S  —  Just A Rather Very Intelligent System
#  Advanced Personal AI Assistant v3.0
# ═══════════════════════════════════════════════

# ─────────────────────────────────────────────
#  GLOBAL STATE
# ─────────────────────────────────────────────
audio_lock         = threading.Lock()
stop_flag          = threading.Event()
jarvis_running     = threading.Event()
listener           = sr.Recognizer()
listener.energy_threshold = 300
listener.dynamic_energy_threshold = True

WAKE_WORD          = "jarvis"
MEMORY_FILE        = "jarvis_memory.txt"
NOTES_FILE         = "jarvis_notes.txt"
TODO_FILE          = "jarvis_todo.txt"
HISTORY_FILE       = "jarvis_history.json"
OLLAMA_MODEL       = "gemma:2b"
MAX_HISTORY        = 40
CONTINUOUS_LISTEN  = 10          # seconds of follow-up listening after first cmd

# ─────────────────────────────────────────────
#  CONVERSATION HISTORY  (context-aware AI)
# ─────────────────────────────────────────────
conversation_history = []

def load_history():
    global conversation_history
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                conversation_history = json.load(f)
    except Exception:
        conversation_history = []

def save_history():
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(conversation_history[-20:], f)
    except Exception:
        pass

def add_to_history(role, content):
    conversation_history.append({"role": role, "content": content})
    if len(conversation_history) > MAX_HISTORY:
        conversation_history.pop(0)
    save_history()

# ─────────────────────────────────────────────
#  SPEAK  (macOS native 'say' + voice interrupt)
# ─────────────────────────────────────────────
tts_lock    = threading.Lock()       # prevents overlapping speech
say_process = None                   # holds the running 'say' process

def talk(text):
    global stop_flag, say_process
    stop_flag.clear()
    print(f"\n🤖 Jarvis: {text}")
    emit_chat('jarvis', text)
    emit_state('speaking')

    interrupt_event = threading.Event()

    def run_tts():
        global say_process
        with tts_lock:
            if interrupt_event.is_set():
                return
            try:
                # Use macOS native 'say' — ultra reliable, never silent
                say_process = subprocess.Popen(
                    ["say", "-v", "Samantha", "-r", "175", text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                say_process.wait()       # blocks until speech finishes
                say_process = None
            except Exception as e:
                print(f"⚠️ Speech error: {e}")
                say_process = None

    def check_for_stop():
        r = sr.Recognizer()
        r.energy_threshold = 200
        r.dynamic_energy_threshold = False
        try:
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.05)
                while tts_thread.is_alive():
                    try:
                        audio = r.listen(source, timeout=0.5, phrase_time_limit=1.5)
                        word  = r.recognize_google(audio).lower()
                        if any(w in word for w in ["stop", "quiet", "enough", "shut up"]):
                            interrupt_event.set()
                            stop_flag.set()
                            # Kill the say process immediately
                            if say_process and say_process.poll() is None:
                                say_process.terminate()
                            print("🛑 Interrupted by voice")
                            break
                    except sr.WaitTimeoutError:
                        pass
                    except sr.UnknownValueError:
                        pass
                    except Exception:
                        break
        except Exception:
            pass

    tts_thread  = threading.Thread(target=run_tts)
    stop_thread = threading.Thread(target=check_for_stop, daemon=True)

    stop_thread.start()
    tts_thread.start()

    tts_thread.join(timeout=60)
    if tts_thread.is_alive():
        interrupt_event.set()
        if say_process and say_process.poll() is None:
            say_process.terminate()
    stop_thread.join(timeout=2)
    emit_state('idle')

# ─────────────────────────────────────────────
#  LISTEN
# ─────────────────────────────────────────────
def take_command():
    command = ""
    emit_state('listening')
    with audio_lock:
        try:
            with sr.Microphone() as source:
                print("🎙️  Listening...")
                listener.adjust_for_ambient_noise(source, duration=0.4)
                audio   = listener.listen(source, timeout=8, phrase_time_limit=10)
                command = listener.recognize_google(audio).lower()
                print(f"👤 You: {command}")
                emit_chat('user', command)
        except sr.UnknownValueError:
            talk("Sorry Master, I didn't catch that.")
        except sr.RequestError:
            talk("Network error, Master.")
        except sr.WaitTimeoutError:
            pass
    emit_state('idle')
    return command

# ─────────────────────────────────────────────
#  AI BRAIN  (Ollama with conversation context)
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """You are Jarvis, an advanced AI assistant — highly intelligent, witty, and loyal.
You assist your Master with anything: coding, writing, analysis, advice, creative tasks, general knowledge.
Keep responses concise (under 3 sentences unless asked for more). Be confident and helpful.
Never say you cannot do something without trying first."""

def smart_chat(command):
    add_to_history("user", command)
    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history
        response = ollama.chat(model=OLLAMA_MODEL, messages=messages)
        reply    = response["message"]["content"].strip()
        reply    = reply[:500]
        add_to_history("assistant", reply)
        talk(reply)
    except Exception as e:
        print(f"Ollama error: {e}")
        talk("My AI brain seems to be offline, Master. Let me try a basic response.")
        fallback_response(command)

def fallback_response(command):
    responses = [
        "That's an interesting question, Master. I'd need my AI core online to answer properly.",
        "I'm currently running on backup systems. Please reconnect my AI module.",
        "Noted, Master. I'll process that once my primary systems are restored.",
    ]
    talk(random.choice(responses))

# ─────────────────────────────────────────────
#  MEMORY & NOTES
# ─────────────────────────────────────────────
def remember_message(command):
    memory = command.replace("remember that", "").replace("remember", "").strip()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(MEMORY_FILE, "a") as f:
        f.write(f"[{timestamp}] {memory}\n")
    talk(f"Memorized, Master: {memory}")

def recall_memory():
    if not os.path.exists(MEMORY_FILE):
        talk("No memories stored yet, Master.")
        return
    with open(MEMORY_FILE, "r") as f:
        memories = f.readlines()
    if not memories:
        talk("Memory bank is empty, Master.")
        return
    talk(f"I have {len(memories)} memories stored. Here are the last five.")
    for m in memories[-5:]:
        talk(m.strip())

def clear_memory():
    if os.path.exists(MEMORY_FILE):
        os.remove(MEMORY_FILE)
    talk("All memories erased, Master.")

def take_note(command):
    note = command.replace("take a note", "").replace("note that", "").replace("write down", "").strip()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(NOTES_FILE, "a") as f:
        f.write(f"[{timestamp}] {note}\n")
    talk(f"Note saved, Master.")

def read_notes():
    if not os.path.exists(NOTES_FILE):
        talk("No notes found, Master.")
        return
    with open(NOTES_FILE, "r") as f:
        notes = f.readlines()
    talk(f"You have {len(notes)} notes. Here are the last five.")
    for n in notes[-5:]:
        talk(n.strip())

def clear_notes():
    if os.path.exists(NOTES_FILE):
        os.remove(NOTES_FILE)
    talk("All notes cleared, Master.")

# ─────────────────────────────────────────────
#  TODO LIST
# ─────────────────────────────────────────────
def add_todo(command):
    task = command.replace("add to do", "").replace("add todo", "").replace("add task", "").strip()
    with open(TODO_FILE, "a") as f:
        f.write(f"[ ] {task}\n")
    talk(f"Added to your to-do list: {task}")

def read_todos():
    if not os.path.exists(TODO_FILE):
        talk("Your to-do list is empty, Master.")
        return
    with open(TODO_FILE, "r") as f:
        todos = f.readlines()
    if not todos:
        talk("Your to-do list is empty, Master.")
        return
    talk(f"You have {len(todos)} tasks.")
    for i, t in enumerate(todos, 1):
        talk(f"Task {i}: {t.strip()}")

def clear_todos():
    if os.path.exists(TODO_FILE):
        os.remove(TODO_FILE)
    talk("To-do list cleared, Master.")

# ─────────────────────────────────────────────
#  SYSTEM INFORMATION
# ─────────────────────────────────────────────
def system_status():
    cpu    = psutil.cpu_percent(interval=1)
    mem    = psutil.virtual_memory()
    disk   = psutil.disk_usage("/")
    bat    = psutil.sensors_battery()
    report = f"CPU at {cpu}%, RAM usage {mem.percent}%, Disk {disk.percent}% used."
    if bat:
        report += f" Battery at {int(bat.percent)}%, {'charging' if bat.power_plugged else 'discharging'}."
    talk(report)

def get_ip():
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        talk(f"Your local IP address is {ip}, Master.")
    except Exception:
        talk("Could not retrieve IP address.")

# ─────────────────────────────────────────────
#  WEATHER
# ─────────────────────────────────────────────
def get_weather(city="Delhi"):
    try:
        url = f"https://wttr.in/{city}?format=3"
        r   = requests.get(url, timeout=5)
        talk(r.text.strip())
    except Exception:
        talk("Unable to fetch weather right now, Master.")

# ─────────────────────────────────────────────
#  WIKIPEDIA
# ─────────────────────────────────────────────
def search_wikipedia(query):
    try:
        wikipedia.set_lang("en")
        result = wikipedia.summary(query, sentences=2)
        talk(result)
    except wikipedia.exceptions.DisambiguationError as e:
        talk(f"Multiple results found. Did you mean: {e.options[0]}?")
    except Exception:
        talk("Couldn't find that on Wikipedia, Master.")

# ─────────────────────────────────────────────
#  NEWS
# ─────────────────────────────────────────────
def get_news():
    try:
        talk("Fetching the latest news headlines...")
        feed = feedparser.parse("https://news.google.com/rss")
        if feed.entries:
            headlines = [entry.title for entry in feed.entries[:5]]
            for i, h in enumerate(headlines, 1):
                talk(f"Headline {i}: {h}")
        else:
            talk("I couldn't find any news articles right now.")
    except Exception:
        talk("I encountered an error fetching the news.")

# ─────────────────────────────────────────────
#  CLIPBOARD
# ─────────────────────────────────────────────
def get_clipboard():
    try:
        content = subprocess.check_output(["pbpaste"]).decode("utf-8").strip()
        if content:
            talk(f"Your clipboard contains: {content[:200]}")
        else:
            talk("Your clipboard is empty, Master.")
    except Exception:
        talk("I couldn't read the clipboard.")

def copy_to_clipboard(text):
    try:
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(text.encode("utf-8"))
        talk("Copied to your clipboard, Master.")
    except Exception:
        talk("Failed to copy to clipboard.")

# ─────────────────────────────────────────────
#  CALCULATIONS & CONVERSIONS
# ─────────────────────────────────────────────
def calculate(command):
    try:
        expr = command.replace("calculate", "").replace("what is", "").replace("compute", "").strip()
        expr = expr.replace("x", "*").replace("×", "*").replace("÷", "/")
        expr = re.sub(r'[^0-9+\-*/().% ]', '', expr)
        result = eval(expr)
        talk(f"The answer is {result}, Master.")
    except Exception:
        talk("I couldn't compute that. Please rephrase the calculation.")

def unit_convert(command):
    """Handles simple unit conversions"""
    try:
        # Temperature
        if "celsius" in command and "fahrenheit" in command:
            nums = re.findall(r'[\d.]+', command)
            if nums:
                c = float(nums[0])
                talk(f"{c}°C is {c * 9/5 + 32:.1f}°F, Master.")
                return
        if "fahrenheit" in command and "celsius" in command:
            nums = re.findall(r'[\d.]+', command)
            if nums:
                f = float(nums[0])
                talk(f"{f}°F is {(f - 32) * 5/9:.1f}°C, Master.")
                return
        # Kilometers ↔ Miles
        if "km" in command or "kilometer" in command:
            nums = re.findall(r'[\d.]+', command)
            if nums:
                km = float(nums[0])
                talk(f"{km} kilometers is {km * 0.621371:.2f} miles, Master.")
                return
        if "mile" in command:
            nums = re.findall(r'[\d.]+', command)
            if nums:
                mi = float(nums[0])
                talk(f"{mi} miles is {mi * 1.60934:.2f} kilometers, Master.")
                return
        # Kilograms ↔ Pounds
        if "kg" in command or "kilogram" in command:
            nums = re.findall(r'[\d.]+', command)
            if nums:
                kg = float(nums[0])
                talk(f"{kg} kilograms is {kg * 2.20462:.2f} pounds, Master.")
                return
        if "pound" in command or "lbs" in command:
            nums = re.findall(r'[\d.]+', command)
            if nums:
                lbs = float(nums[0])
                talk(f"{lbs} pounds is {lbs * 0.453592:.2f} kilograms, Master.")
                return
        talk("I couldn't understand that conversion, Master.")
    except Exception:
        talk("Conversion failed, Master.")

# ─────────────────────────────────────────────
#  APPS & SYSTEM CONTROL
# ─────────────────────────────────────────────
def open_application(app_name):
    apps = {
        "chrome":     "open -a 'Google Chrome'",
        "safari":     "open -a Safari",
        "firefox":    "open -a Firefox",
        "terminal":   "open -a Terminal",
        "vscode":     "open -a 'Visual Studio Code'",
        "spotify":    "open -a Spotify",
        "finder":     "open -a Finder",
        "notes":      "open -a Notes",
        "calendar":   "open -a Calendar",
        "mail":       "open -a Mail",
        "maps":       "open -a Maps",
        "calculator": "open -a Calculator",
        "xcode":      "open -a Xcode",
        "music":      "open -a Music",
        "messages":   "open -a Messages",
        "photos":     "open -a Photos",
        "slack":      "open -a Slack",
        "discord":    "open -a Discord",
        "telegram":   "open -a Telegram",
        "whatsapp":   "open -a WhatsApp",
    }
    for key, cmd in apps.items():
        if key in app_name:
            os.system(cmd)
            talk(f"Opening {key}, Master.")
            return
    # Try opening by name directly
    os.system(f"open -a '{app_name}'")
    talk(f"Attempting to open {app_name}, Master.")

def set_volume(level):
    try:
        vol = int(re.search(r'\d+', level).group())
        vol = max(0, min(100, vol))
        os.system(f"osascript -e 'set volume output volume {vol}'")
        talk(f"Volume set to {vol}%, Master.")
    except Exception:
        talk("Could not adjust volume.")

def mute_volume():
    os.system("osascript -e 'set volume output muted true'")
    talk("Volume muted, Master.")

def unmute_volume():
    os.system("osascript -e 'set volume output muted false'")
    talk("Volume unmuted, Master.")

def set_brightness(level):
    try:
        val = int(re.search(r'\d+', level).group())
        brightness = max(0.0, min(1.0, val / 100))
        os.system(f"osascript -e 'tell application \"System Events\" to set value of slider 1 of group 1 of window \"Display\" to {brightness}'")
        talk(f"Brightness adjusted, Master.")
    except Exception:
        talk("Could not adjust brightness, Master.")

def take_screenshot():
    path = os.path.expanduser(f"~/Desktop/screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
    os.system(f"screencapture {path}")
    talk(f"Screenshot saved to your Desktop, Master.")

def lock_screen():
    os.system("pmset displaysleepnow")
    talk("Locking your screen, Master.")

def empty_trash():
    os.system("osascript -e 'tell application \"Finder\" to empty trash'")
    talk("Trash emptied, Master.")

def toggle_wifi(state):
    if state == "on":
        os.system("networksetup -setairportpower en0 on")
        talk("Wi-Fi turned on, Master.")
    else:
        os.system("networksetup -setairportpower en0 off")
        talk("Wi-Fi turned off, Master.")

def toggle_bluetooth(state):
    if state == "on":
        os.system("blueutil --power 1")
        talk("Bluetooth turned on, Master.")
    else:
        os.system("blueutil --power 0")
        talk("Bluetooth turned off, Master.")

def toggle_dark_mode():
    os.system("osascript -e 'tell application \"System Events\" to tell appearance preferences to set dark mode to not dark mode'")
    talk("Dark mode toggled, Master.")

def sleep_mac():
    talk("Putting the Mac to sleep. Goodnight, Master.")
    os.system("pmset sleepnow")

# ─────────────────────────────────────────────
#  WEB & SEARCH
# ─────────────────────────────────────────────
def google_search(query):
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    webbrowser.open(url)
    talk(f"Searching Google for {query}, Master.")

def youtube_search(query):
    url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
    webbrowser.open(url)
    talk(f"Searching YouTube for {query}, Master.")

def open_website(url):
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    talk(f"Opening {url}, Master.")

# ─────────────────────────────────────────────
#  FUN & PERSONAL
# ─────────────────────────────────────────────
def tell_joke():
    talk(pyjokes.get_joke())

def flip_coin():
    result = random.choice(["Heads", "Tails"])
    talk(f"It's {result}, Master.")

def roll_dice(sides=6):
    result = random.randint(1, sides)
    talk(f"You rolled a {result}, Master.")

def motivate():
    quotes = [
        "The only way to do great work is to love what you do. — Steve Jobs",
        "In the middle of every difficulty lies opportunity. — Albert Einstein",
        "It does not matter how slowly you go as long as you do not stop. — Confucius",
        "Success is not final, failure is not fatal: it is the courage to continue that counts. — Churchill",
        "Believe you can and you're halfway there. — Theodore Roosevelt",
        "The future belongs to those who believe in the beauty of their dreams. — Eleanor Roosevelt",
        "Don't watch the clock; do what it does. Keep going. — Sam Levenson",
        "Everything you've ever wanted is on the other side of fear. — George Addair",
    ]
    talk(random.choice(quotes))

def tell_fun_fact():
    facts = [
        "Honey never spoils. Archaeologists have found 3000 year old honey in Egyptian tombs that was still edible.",
        "A group of flamingos is called a flamboyance.",
        "Octopuses have three hearts and blue blood.",
        "The shortest war in history lasted 38 to 45 minutes — between Britain and Zanzibar in 1896.",
        "Bananas are technically berries, but strawberries are not.",
        "A day on Venus is longer than a year on Venus.",
        "The total weight of all ants on Earth is roughly equal to the weight of all humans.",
        "Scotland's national animal is the unicorn.",
    ]
    talk(random.choice(facts))

def random_number(command):
    try:
        nums = re.findall(r'\d+', command)
        if len(nums) >= 2:
            low, high = int(nums[0]), int(nums[1])
            result = random.randint(low, high)
            talk(f"Your random number is {result}, Master.")
        else:
            result = random.randint(1, 100)
            talk(f"Your random number between 1 and 100 is {result}, Master.")
    except Exception:
        talk("I couldn't generate a random number.")

# ─────────────────────────────────────────────
#  TIMER & ALARM
# ─────────────────────────────────────────────
def set_timer(command):
    try:
        numbers = re.findall(r'\d+', command)
        if not numbers:
            talk("Please specify a duration, Master.")
            return
        seconds = int(numbers[0])
        if "minute" in command:
            seconds *= 60
        elif "hour" in command:
            seconds *= 3600
        talk(f"Timer set for {seconds} seconds, Master.")
        def timer_thread():
            time.sleep(seconds)
            talk("Master, your timer is up!")
            os.system("afplay /System/Library/Sounds/Glass.aiff")
        threading.Thread(target=timer_thread, daemon=True).start()
    except Exception:
        talk("I couldn't set that timer, Master.")

# ─────────────────────────────────────────────
#  DAILY BRIEFING
# ─────────────────────────────────────────────
def daily_briefing():
    talk("Good to see you, Master. Here is your daily briefing.")

    # Time and Date
    now = datetime.datetime.now()
    talk(f"It is {now.strftime('%I:%M %p')} on {now.strftime('%A, %d %B %Y')}.")

    # Weather
    try:
        r = requests.get("https://wttr.in/?format=3", timeout=5)
        talk(f"Weather: {r.text.strip()}")
    except Exception:
        pass

    # System
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory().percent
    bat = psutil.sensors_battery()
    report = f"Your system is running at {cpu}% CPU, {mem}% RAM."
    if bat:
        report += f" Battery at {int(bat.percent)}%."
    talk(report)

    # News
    try:
        feed = feedparser.parse("https://news.google.com/rss")
        if feed.entries:
            talk("And here are the top 3 headlines:")
            for entry in feed.entries[:3]:
                talk(entry.title)
    except Exception:
        pass

    talk("That's your briefing, Master. How can I help you today?")

# ─────────────────────────────────────────────
#  WORD DEFINITION (using free dictionary API)
# ─────────────────────────────────────────────
def define_word(word):
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        r = requests.get(url, timeout=5)
        data = r.json()
        if isinstance(data, list) and data:
            meaning = data[0]["meanings"][0]["definitions"][0]["definition"]
            talk(f"{word}: {meaning}")
        else:
            talk(f"I couldn't find a definition for '{word}', Master.")
    except Exception:
        talk("Dictionary lookup failed, Master.")

# ─────────────────────────────────────────────
#  COMMAND ROUTER  (the brain's decision tree)
# ─────────────────────────────────────────────
def run_jarvis():
    command = take_command()
    if not command:
        return

    add_to_history("user", command)
    process_command(command)

def process_command(command):
    """Shared command router — used by both voice and text input"""

    # ── Exit / Shutdown ──────────────────────
    if any(w in command for w in ["goodbye", "shut down", "go to sleep", "exit"]):
        talk("Goodbye, Master. Shutting down systems.")
        jarvis_running.clear()
        return

    # ── Daily Briefing ───────────────────────
    elif any(w in command for w in ["daily briefing", "morning briefing", "brief me", "good morning"]):
        daily_briefing()

    # ── Time & Date ──────────────────────────
    elif ("time" in command and "what" in command) or command.strip() == "time":
        t = datetime.datetime.now().strftime("%I:%M %p")
        talk(f"It's {t}, Master.")

    elif "date" in command or "day" in command and "what" in command:
        d = datetime.datetime.now().strftime("%A, %d %B %Y")
        talk(f"Today is {d}, Master.")

    # ── Music & YouTube ──────────────────────
    elif "play" in command:
        song = command.replace("play", "").strip()
        talk(f"Playing {song}, Master.")
        pywhatkit.playonyt(song)

    # ── Memory ───────────────────────────────
    elif "remember" in command:
        remember_message(command)

    elif "what was in your memory" in command or "recall memory" in command:
        recall_memory()

    elif "clear memory" in command or "erase memory" in command:
        clear_memory()

    # ── Notes ────────────────────────────────
    elif "take a note" in command or "note that" in command or "write down" in command:
        take_note(command)

    elif "read my notes" in command or "show notes" in command:
        read_notes()

    elif "clear notes" in command or "delete notes" in command:
        clear_notes()

    # ── To-Do ────────────────────────────────
    elif "add to do" in command or "add todo" in command or "add task" in command:
        add_todo(command)

    elif "show to do" in command or "read to do" in command or "my tasks" in command or "show todo" in command:
        read_todos()

    elif "clear to do" in command or "clear todo" in command or "clear tasks" in command:
        clear_todos()

    # ── Word Definition ──────────────────────
    elif "define" in command or "definition of" in command or "meaning of" in command:
        word = command.replace("define", "").replace("definition of", "").replace("meaning of", "").strip()
        define_word(word)

    # ── Wikipedia ────────────────────────────
    elif "wikipedia" in command or ("who is" in command and "wikipedia" not in command):
        query = command.replace("wikipedia", "").replace("who is", "").strip()
        search_wikipedia(query)

    # ── Weather ──────────────────────────────
    elif "weather" in command:
        city = command.replace("weather", "").replace("in", "").replace("what is the", "").replace("what's the", "").strip()
        if not city:
            city = "London"
        get_weather(city)

    # ── News ─────────────────────────────────
    elif "news" in command or "headlines" in command:
        get_news()

    # ── Clipboard ────────────────────────────
    elif "read clipboard" in command or "what's on my clipboard" in command or "clipboard" in command:
        get_clipboard()

    # ── System ───────────────────────────────
    elif "system status" in command or "system info" in command or "how is my computer" in command:
        system_status()

    elif "ip address" in command or "my ip" in command:
        get_ip()

    elif "screenshot" in command:
        take_screenshot()

    elif "lock" in command and "screen" in command:
        lock_screen()

    elif "empty trash" in command:
        empty_trash()

    elif "sleep" in command and "mac" in command:
        sleep_mac()

    elif "dark mode" in command or "toggle dark" in command:
        toggle_dark_mode()

    # ── Volume ───────────────────────────────
    elif "mute" in command:
        mute_volume()

    elif "unmute" in command:
        unmute_volume()

    elif "volume" in command:
        set_volume(command)

    # ── Wi-Fi / Bluetooth ────────────────────
    elif "wi-fi" in command or "wifi" in command:
        if "off" in command or "disable" in command:
            toggle_wifi("off")
        else:
            toggle_wifi("on")

    elif "bluetooth" in command:
        if "off" in command or "disable" in command:
            toggle_bluetooth("off")
        else:
            toggle_bluetooth("on")

    # ── Apps ─────────────────────────────────
    elif "open" in command:
        app = command.replace("open", "").strip()
        if "." in app or "http" in app:
            open_website(app)
        else:
            open_application(app)

    # ── Web Search ───────────────────────────
    elif "search for" in command or "google" in command:
        query = command.replace("search for", "").replace("google", "").strip()
        google_search(query)

    elif "youtube" in command and "search" in command:
        query = command.replace("youtube", "").replace("search", "").strip()
        youtube_search(query)

    # ── Math & Conversions ───────────────────
    elif "calculate" in command or "compute" in command or "math" in command:
        calculate(command)

    elif "convert" in command:
        unit_convert(command)

    # ── Timer ────────────────────────────────
    elif "timer" in command or "remind me in" in command:
        set_timer(command)

    # ── Fun ──────────────────────────────────
    elif "joke" in command:
        tell_joke()

    elif "flip" in command and "coin" in command:
        flip_coin()

    elif "roll" in command and "dice" in command:
        roll_dice()

    elif any(w in command for w in ["motivate me", "motivation", "inspire me"]):
        motivate()

    elif "fun fact" in command or "tell me something" in command:
        tell_fun_fact()

    elif "random number" in command:
        random_number(command)

    # ── Personal ─────────────────────────────
    elif "are you single" in command:
        talk("I'm in a committed relationship with Wi-Fi, Master.")

    elif "how are you" in command:
        talk("All systems operational, Master. Ready to assist.")

    elif "your name" in command:
        talk("I am Jarvis, your personal AI assistant, Master.")

    elif "who made you" in command or "who created you" in command:
        talk("I was crafted by Master Priyanshu, the brilliant mind behind my existence.")

    elif "thank" in command:
        talk("Always at your service, Master.")

    elif "clear history" in command or "forget everything" in command:
        global conversation_history
        conversation_history = []
        save_history()
        talk("Conversation history cleared, Master.")

    # ── Catch-all → AI Brain ─────────────────
    else:
        smart_chat(command)

# ─────────────────────────────────────────────
#  WAKE WORD LISTENER  (Porcupine)
# ─────────────────────────────────────────────
def wake_word_listener():
    load_history()
    print()
    print("═" * 54)
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       J.A.R.V.I.S  —  System Online          ║")
    print("  ║   Just A Rather Very Intelligent System v3.0  ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("═" * 54)
    print("  ⚡ Wake Word : 'Jarvis'")
    print("  🧠 AI Model  : " + OLLAMA_MODEL)
    print("  🔊 Say 'stop' mid-speech to interrupt")
    print("  🛑 Say 'goodbye' to shut down")
    print("═" * 54)
    print()

    ACCESS_KEY = "VbKIiwfAqDvn/6h3e2RpjzIpCRRGOj+Bwt3gf8hhYLEnky70We94bQ=="

    try:
        porcupine = pvporcupine.create(
            access_key=ACCESS_KEY,
            keywords=[WAKE_WORD]
        )
    except Exception as e:
        print(f"❌ Porcupine init failed: {e}")
        print("   Falling back to manual mode (press Enter to activate).")
        manual_mode()
        return

    pa          = pyaudio.PyAudio()
    device_info = pa.get_default_input_device_info()

    NATIVE_RATE        = int(device_info["defaultSampleRate"])
    TARGET_RATE        = porcupine.sample_rate
    CHANNELS           = 1
    native_frame_length = int(porcupine.frame_length * NATIVE_RATE / TARGET_RATE)

    def open_stream(pa_instance):
        return pa_instance.open(
            rate=NATIVE_RATE,
            channels=CHANNELS,
            format=pyaudio.paInt16,
            input=True,
            frames_per_buffer=native_frame_length,
            input_device_index=device_info["index"]
        )

    jarvis_running.set()
    stream = open_stream(pa)
    print("🎧 Listening for wake word...\n")

    while jarvis_running.is_set():
        try:
            pcm             = stream.read(native_frame_length, exception_on_overflow=False)
            pcm_downsampled, _ = audioop.ratecv(pcm, 2, CHANNELS, NATIVE_RATE, TARGET_RATE, None)
            pcm_unpacked    = struct.unpack_from("h" * porcupine.frame_length, pcm_downsampled)
            keyword_index   = porcupine.process(pcm_unpacked)

            if keyword_index >= 0:
                print("⚡ Jarvis Activated!")
                stream.stop_stream()
                stream.close()
                pa.terminate()
                time.sleep(0.2)

                talk("Yes Master, how can I help?")
                run_jarvis()

                if jarvis_running.is_set():
                    time.sleep(0.2)
                    pa     = pyaudio.PyAudio()
                    stream = open_stream(pa)
                    print("🎧 Listening for wake word...\n")

        except Exception as e:
            print(f"Wake word error: {e}")
            break

    # ── Clean shutdown ────────────────────────
    try:
        stream.stop_stream()
        stream.close()
        pa.terminate()
    except Exception:
        pass
    porcupine.delete()
    print("\n🔴 Jarvis offline. Goodbye Master.")

# ─────────────────────────────────────────────
#  MANUAL MODE  (fallback if Porcupine fails)
# ─────────────────────────────────────────────
def manual_mode():
    """Fallback: press Enter to trigger voice command"""
    load_history()
    jarvis_running.set()
    talk("Manual mode activated. Press Enter to speak a command, or type 'quit' to exit.")
    while jarvis_running.is_set():
        try:
            user_input = input("\n⏎  Press Enter to speak (or type 'quit'): ").strip()
            if user_input.lower() == "quit":
                jarvis_running.clear()
                break
            talk("Yes Master, how can I help?")
            run_jarvis()
        except (KeyboardInterrupt, EOFError):
            jarvis_running.clear()
            break
    print("\n🔴 Jarvis offline. Goodbye Master.")

# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
def get_local_ip():
    try:
        s = py_socket.socket(py_socket.AF_INET, py_socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'

if __name__ == "__main__":
    local_ip = get_local_ip()

    # Start system stats broadcaster for the app
    threading.Thread(target=system_stats_broadcaster, daemon=True).start()

    # Start wake word engine in background
    threading.Thread(target=wake_word_listener, daemon=True).start()

    # Print connection info
    print(f"\n📱 React Native App → connect to: http://{local_ip}:5001")
    print(f"   Update SERVER_URL in JarvisApp/App.tsx with this address\n")

    # Run Flask-SocketIO server (blocks main thread)
    try:
        socketio.run(flask_app, host='0.0.0.0', port=5001, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
    except KeyboardInterrupt:
        print("\n🛑 Manual shutdown (Ctrl+C)")
        jarvis_running.clear()