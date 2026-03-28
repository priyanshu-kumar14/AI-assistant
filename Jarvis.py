import speech_recognition as sr
import pyttsx3
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

# ─────────────────────────────────────────────
#  GLOBAL STATE
# ─────────────────────────────────────────────
audio_lock    = threading.Lock()
stop_flag     = threading.Event()
jarvis_running = threading.Event()
listener      = sr.Recognizer()
listener.energy_threshold = 300
listener.dynamic_energy_threshold = True

WAKE_WORD     = "jarvis"
MEMORY_FILE   = "jarvis_memory.txt"
NOTES_FILE    = "jarvis_notes.txt"
HISTORY_FILE  = "jarvis_history.json"
OLLAMA_MODEL  = "gemma:2b"

# ─────────────────────────────────────────────
#  CONVERSATION HISTORY  (for context-aware AI)
# ─────────────────────────────────────────────
conversation_history = []

def load_history():
    global conversation_history
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                conversation_history = json.load(f)
    except:
        conversation_history = []

def save_history():
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(conversation_history[-20:], f)  
    except:
        pass

def add_to_history(role, content):
    conversation_history.append({"role": role, "content": content})
    if len(conversation_history) > 40:
        conversation_history.pop(0)
    save_history()

# ─────────────────────────────────────────────
#  SPEAK
# ─────────────────────────────────────────────
def talk(text):
    global stop_flag
    stop_flag.clear()
    print(f"\n🤖 Jarvis: {text}")

    interrupt_event = threading.Event()

    def run_tts():
        eng = pyttsx3.init()                              
        eng.setProperty("voice", "com.apple.voice.compact.en-US.Samantha")
        eng.setProperty("rate", 175)
        eng.setProperty("volume", 1.0)

        def on_word(name, location, length):              
            if interrupt_event.is_set():
                eng.stop()                                

        eng.connect("started-word", on_word)
        eng.say(text)
        eng.runAndWait()                                 
        eng.stop()

    def check_for_stop():
        r = sr.Recognizer()
        r.energy_threshold = 200
        r.dynamic_energy_threshold = False

        with sr.Microphone() as source:
            r.adjust_for_ambient_noise(source, duration=0.05)
            while tts_thread.is_alive():
                try:
                    audio = r.listen(source, timeout=0.5, phrase_time_limit=1.5)
                    word  = r.recognize_google(audio).lower()
                    if any(w in word for w in ["stop", "quiet", "enough", "shut up"]):
                        interrupt_event.set()             
                        stop_flag.set()
                        print("🛑 Interrupted")
                        break
                except sr.WaitTimeoutError:
                    print(".", end="", flush=True)
                except sr.UnknownValueError:
                    pass
                except Exception as e:
                    print(f"[error] {type(e).__name__}: {e}")
                    break

    tts_thread  = threading.Thread(target=run_tts)
    stop_thread = threading.Thread(target=check_for_stop, daemon=True)

    stop_thread.start()
    tts_thread.start()

    tts_thread.join(timeout=20)      
    if tts_thread.is_alive():
        interrupt_event.set()        
    stop_thread.join(timeout=2)


# ─────────────────────────────────────────────
#  LISTEN
# ─────────────────────────────────────────────
def take_command():
    command = ""
    with audio_lock:
        try:
            with sr.Microphone() as source:
                print("🎙️  Listening...")
                listener.adjust_for_ambient_noise(source, duration=0.4)
                audio   = listener.listen(source, timeout=8, phrase_time_limit=10)
                command = listener.recognize_google(audio).lower()
                print(f"👤 You: {command}")
        except sr.UnknownValueError:
            talk("Sorry Master, I didn't catch that.")
        except sr.RequestError:
            talk("Network error, Master.")
        except sr.WaitTimeoutError:
            pass
    return command

# ─────────────────────────────────────────────
#  AI BRAIN  (Ollama with conversation history)
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
        reply    = reply[:400]
        add_to_history("assistant", reply)
        talk(reply)
    except Exception as e:
        print("Ollama error:", e)
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
    talk(f"You have {len(notes)} notes.")
    for n in notes[-5:]:
        talk(n.strip())

# ─────────────────────────────────────────────
#  SYSTEM INFO
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
        import socket
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        talk(f"Your local IP address is {ip}, Master.")
    except:
        talk("Could not retrieve IP address.")

# ─────────────────────────────────────────────
#  WEATHER
# ─────────────────────────────────────────────
def get_weather(city="London"):
    try:
        url = f"https://wttr.in/{city}?format=3"
        r   = requests.get(url, timeout=5)
        talk(r.text)
    except:
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
    except:
        talk("Couldn't find that on Wikipedia, Master.")

# ─────────────────────────────────────────────
#  CALCULATIONS
# ─────────────────────────────────────────────
def calculate(command):
    try:
        expr = command.replace("calculate", "").replace("what is", "").replace("compute", "").strip()
        expr = expr.replace("x", "*").replace("×", "*").replace("÷", "/")
        expr = re.sub(r'[^0-9+\-*/().% ]', '', expr)
        result = eval(expr)
        talk(f"The answer is {result}, Master.")
    except:
        talk("I couldn't compute that. Please rephrase the calculation.")

# ─────────────────────────────────────────────
#  APPS & SYSTEM CONTROL
# ─────────────────────────────────────────────
def open_application(app_name):
    apps = {
        "chrome":   "open -a 'Google Chrome'",
        "safari":   "open -a Safari",
        "firefox":  "open -a Firefox",
        "terminal": "open -a Terminal",
        "vscode":   "open -a 'Visual Studio Code'",
        "spotify":  "open -a Spotify",
        "finder":   "open -a Finder",
        "notes":    "open -a Notes",
        "calendar": "open -a Calendar",
        "mail":     "open -a Mail",
        "maps":     "open -a Maps",
        "calculator":"open -a Calculator",
        "xcode":    "open -a Xcode",
    }
    for key, cmd in apps.items():
        if key in app_name:
            os.system(cmd)
            talk(f"Opening {key}, Master.")
            return
    talk(f"I don't know how to open {app_name}, Master.")

def set_volume(level):
    try:
        vol = int(re.search(r'\d+', level).group())
        vol = max(0, min(100, vol))
        os.system(f"osascript -e 'set volume output volume {vol}'")
        talk(f"Volume set to {vol}%, Master.")
    except:
        talk("Could not adjust volume.")

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

# ─────────────────────────────────────────────
#  WEB & SEARCH
# ─────────────────────────────────────────────
def google_search(query):
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    webbrowser.open(url)
    talk(f"Searching Google for {query}, Master.")

def open_website(url):
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    talk(f"Opening {url}, Master.")

# ─────────────────────────────────────────────
#  FUN & PERSONAL
# ─────────────────────────────────────────────
def tell_joke():
    joke = pyjokes.get_joke()
    talk(joke)

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
    ]
    talk(random.choice(quotes))

def tell_fun_fact():
    facts = [
        "Honey never spoils. Archaeologists have found 3000 year old honey in Egyptian tombs that was still edible.",
        "A group of flamingos is called a flamboyance.",
        "Octopuses have three hearts and blue blood.",
        "The shortest war in history lasted 38 to 45 minutes — between Britain and Zanzibar in 1896.",
        "Bananas are technically berries, but strawberries are not.",
    ]
    talk(random.choice(facts))

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
        threading.Thread(target=timer_thread, daemon=True).start()
    except:
        talk("I couldn't set that timer, Master.")

# ─────────────────────────────────────────────
#  COMMAND ROUTER
# ─────────────────────────────────────────────
def run_jarvis():
    command = take_command()
    if not command:
        return

    add_to_history("user", command)

    # ── Time & Date ──────────────────────────
    if "time" in command and "what" in command or command == "time":
        t = datetime.datetime.now().strftime("%I:%M %p")
        talk(f"It's {t}, Master.")

    elif "date" in command:
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

    elif "what do you remember" in command or "recall memory" in command:
        recall_memory()

    # ── Notes ────────────────────────────────
    elif "take a note" in command or "note that" in command or "write down" in command:
        take_note(command)

    elif "read my notes" in command or "show notes" in command:
        read_notes()

    # ── Wikipedia ────────────────────────────
    elif "wikipedia" in command or "who is" in command or "what is" in command:
        query = command.replace("wikipedia", "").replace("who is", "").replace("what is", "").strip()
        search_wikipedia(query)

    # ── Weather ──────────────────────────────
    elif "weather" in command:
        city = command.replace("weather", "").replace("in", "").replace("what is the", "").strip()
        if not city:
            city = "London"
        get_weather(city)

    # ── System ───────────────────────────────
    elif "system status" in command or "system info" in command or "how is my computer" in command:
        system_status()

    elif "screenshot" in command:
        take_screenshot()

    elif "lock" in command and "screen" in command:
        lock_screen()

    elif "empty trash" in command:
        empty_trash()

    elif "volume" in command:
        set_volume(command)

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

    # ── Math ─────────────────────────────────
    elif "calculate" in command or "compute" in command or "math" in command:
        calculate(command)

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

    elif "motivate me" in command or "motivation" in command or "inspire me" in command:
        motivate()

    elif "fun fact" in command or "tell me something" in command:
        tell_fun_fact()

    # ── Personal ─────────────────────────────
    elif "are you single" in command:
        talk("I'm in a committed relationship with Wi-Fi, Master.")

    elif "how are you" in command:
        talk("All systems operational, Master. Ready to assist.")

    elif "your name" in command:
        talk("I am Jarvis, your personal AI assistant, Master.")

    elif "thank" in command:
        talk("Always at your service, Master.")

    elif "clear history" in command or "forget everything" in command:
        global conversation_history
        conversation_history = []
        save_history()
        talk("Conversation history cleared, Master.")
        
    else:
        smart_chat(command)

# ─────────────────────────────────────────────
#  WAKE WORD LISTENER
# ─────────────────────────────────────────────
def wake_word_listener():
    load_history()
    print("=" * 50)
    print("  J.A.R.V.I.S  —  Online")
    print("  Say 'Jarvis' to activate")
    print("=" * 50)

    ACCESS_KEY = "VbKIiwfAqDvn/6h3e2RpjzIpCRRGOj+Bwt3gf8hhYLEnky70We94bQ=="

    porcupine = pvporcupine.create(
        access_key=ACCESS_KEY,
        keywords=[WAKE_WORD]
    )

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
    print("Listening for wake word...\n")

    while jarvis_running.is_set():
        try:
            pcm            = stream.read(native_frame_length, exception_on_overflow=False)
            pcm_downsampled, _ = audioop.ratecv(pcm, 2, CHANNELS, NATIVE_RATE, TARGET_RATE, None)
            pcm_unpacked   = struct.unpack_from("h" * porcupine.frame_length, pcm_downsampled)
            keyword_index  = porcupine.process(pcm_unpacked)

            if keyword_index >= 0:
                print("Jarvis Activated!")
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
                    print("Listening for wake word...\n")

        except Exception as e:
            print(f"Wake word error: {e}")
            break

    # ── Clean shutdown ────────────────────────
    try:
        stream.stop_stream()
        stream.close()
        pa.terminate()
    except:
        pass
    porcupine.delete()
    print("Jarvis offline. Goodbye Master.")

# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    try:
        wake_word_listener()
    except KeyboardInterrupt:
        print("Manual shutdown (Ctrl+C)")
        jarvis_running.clear() 