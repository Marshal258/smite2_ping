import os
import re
import glob
import time
import socket
import threading
import tkinter as tk
import ctypes
from PIL import Image, ImageDraw
import pystray # Библиотека для работы с треем

# Точный путь к логам SMITE 2
LOGS_DIR = r"C:\Users\Administrator\AppData\Local\SMITE2Alpha\Saved\Logs"
GAME_PORT = 9000 

# Константы Windows API для сквозной прозрачности
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000

class PingOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SMITE 2 Ping Overlay")
        
        # Свойства окна (поверх окон, без рамок, полупрозрачный фон)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", 0.85)
        self.root.configure(bg="black")
        
        # Размеры окна и позиционирование в левом нижнем углу
        window_width = 160
        window_height = 45
        screen_height = self.root.winfo_screenheight()
        x_position = 20
        y_position = screen_height - window_height - 60
        
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        
        self.label = tk.Label(
            self.root, 
            text="Инициализация...", 
            fg="#FFFF00", 
            bg="black", 
            font=("Consolas", 10, "bold")
        )
        self.label.pack(expand=True, fill="both")
        
        # Переменные состояния
        self.current_ip = None
        self.is_running = True
        
        # Включаем сквозной клик через WinAPI сразу при инициализации
        self.hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        self.make_window_click_through()

        # Запуск фоновых потоков
        self.log_thread = threading.Thread(target=self.watch_logs_loop, daemon=True)
        self.log_thread.start()
        
        self.ping_thread = threading.Thread(target=self.ping_loop, daemon=True)
        self.ping_thread.start()
        
        # Запуск иконки в трее в отдельном потоке
        self.tray_thread = threading.Thread(target=self.setup_tray, daemon=True)
        self.tray_thread.start()

    def make_window_click_through(self):
        """Делает окно абсолютно прозрачным для любых кликов мыши"""
        styles = ctypes.windll.user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, styles | WS_EX_TRANSPARENT | WS_EX_LAYERED)

    def create_tray_image(self):
        """Генерирует временную иконку (круговые стрелки) для трея, если нет .ico файла"""
        image = Image.new('RGB', (64, 64), color='black')
        dc = ImageDraw.Draw(image)
        # Рисуем стилизованную зеленую круговую стрелку (наподобие 🔁)
        dc.arc([12, 12, 52, 52], start=0, end=270, fill='#00FF00', width=5)
        dc.polygon([(52, 32), (42, 22), (62, 22)], fill='#00FF00')
        return image

    def setup_tray(self):
        """Создает иконку в системном трее возле часов"""
        icon_image = self.create_tray_image()
        
        # Описываем меню по правому клику
        menu = pystray.Menu(
            pystray.MenuItem('Выход', self.quit_program)
        )
        
        self.tray_icon = pystray.Icon("smite2_ping", icon_image, "SMITE 2 Ping Monitor", menu)
        self.tray_icon.run()

    def quit_program(self, icon=None, item=None):
        """Корректно завершает работу оверлея и закрывает процесс"""
        self.is_running = False
        if icon:
            icon.stop() # Удаляем значок из трея
        self.root.after(0, self.root.destroy) # Закрываем окно Tkinter

    def safe_update_label(self, text, color):
        if self.root.winfo_exists():
            self.root.after(0, lambda: self.label.config(text=text, fg=color))

    def get_latest_log_file(self):
        if not os.path.exists(LOGS_DIR):
            return None
        list_of_files = glob.glob(os.path.join(LOGS_DIR, "*.log"))
        if not list_of_files:
            return None
        return max(list_of_files, key=os.path.getmtime)

    def extract_ip_from_lines(self, lines):
        for line in reversed(lines):
            if "disconnect" in line.lower() or "unuseconnection" in line.lower() or "closenetdriver" in line.lower():
                return None
            if "Browse:" in line:
                match = re.search(r'Browse:\s+([0-9\.]+)', line)
                if match:
                    ip = match.group(1)
                    if ip not in ["127.0.0.1", "0.0.0.0", "localhost"] and not ip.startswith("192.168."):
                        return ip
        return None

    def watch_logs_loop(self):
        file_handle = None
        last_file = None
        
        while self.is_running:
            try:
                active_file = self.get_latest_log_file()
                if not active_file:
                    self.safe_update_label("Логи не найдены", "#FF3333")
                    time.sleep(2)
                    continue
                
                if active_file != last_file:
                    if file_handle:
                        file_handle.close()
                    
                    last_file = active_file
                    file_handle = open(active_file, 'r', errors='ignore', encoding='utf-8')
                    
                    existing_lines = file_handle.readlines()
                    self.current_ip = self.extract_ip_from_lines(existing_lines)
                    
                    file_handle.seek(0, os.SEEK_END)
                
                line = file_handle.readline()
                if not line:
                    time.sleep(0.1)
                    continue
                
                if "disconnect" in line.lower() or "unuseconnection" in line.lower() or "closenetdriver" in line.lower():
                    self.current_ip = None
                elif "Browse:" in line:
                    match = re.search(r'Browse:\s+([0-9\.]+)', line)
                    if match:
                        ip = match.group(1)
                        if ip not in ["127.0.0.1", "0.0.0.0", "localhost"] and not ip.startswith("192.168."):
                            self.current_ip = ip

            except Exception:
                time.sleep(1)
                
        if file_handle:
            file_handle.close()

    def tcp_ping(self, ip, port=GAME_PORT, timeout=1.2):
        start_time = time.perf_counter()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((ip, port))
            s.close()
            return int((time.perf_counter() - start_time) * 1000)
        except (socket.timeout, ConnectionRefusedError):
            return int((time.perf_counter() - start_time) * 1000)
        except Exception:
            return None

    def ping_loop(self):
        while self.is_running:
            try:
                if not self.current_ip:
                    self.safe_update_label("Ждем матч...", "#FFFF00")
                    time.sleep(1)
                    continue
                
                ping = self.tcp_ping(self.current_ip)
                
                if ping is not None:
                    if ping <= 2:
                        time.sleep(0.5)
                        continue
                        
                    if ping < 60:
                        color = "#00FF00"
                    elif ping < 110:
                        color = "#FF9900"
                    else:
                        color = "#FF3333"
                        
                    self.safe_update_label(f"Ping: {ping} ms\n{self.current_ip}", color)
                else:
                    self.safe_update_label(f"Блокировка\n{self.current_ip}", "#FF3333")
                    
                time.sleep(1.0)
            except Exception:
                time.sleep(1)

    def run(self):
        self.root.mainloop()
        self.is_running = False

if __name__ == "__main__":
    overlay = PingOverlay()
    overlay.run()
