import os
import subprocess
import threading
import time
import winreg
from pathlib import Path

import customtkinter as ctk
import cv2
import numpy as np


BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "button_templates"


class EFootballBotApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("eFootball Auto-Bot (Trained)")
        self.geometry("520x430")
        self.resizable(False, False)
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.is_running = False
        self.adb_path = None
        self.devices = []
        self.templates = []

        self.title_label = ctk.CTkLabel(
            self,
            text="eFootball บอทช่วยกดจากวิดีโอเทรน",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.title_label.pack(pady=15)

        self.btn_connect = ctk.CTkButton(
            self,
            text="1. ค้นหาและเชื่อมต่อ LDPlayer",
            fg_color="#1f538d",
            command=self.auto_connect,
        )
        self.btn_connect.pack(pady=8)

        self.btn_launch = ctk.CTkButton(
            self,
            text="2. เปิด eFootball",
            fg_color="#6750a4",
            state="disabled",
            command=self.launch_game,
        )
        self.btn_launch.pack(pady=8)

        self.status_box = ctk.CTkTextbox(self, width=460, height=165)
        self.status_box.pack(pady=10)
        self.status_box.insert(
            "0.0",
            "ระบบ: เปิด LDPlayer ไว้ก่อน แล้วกดค้นหาและเชื่อมต่อ\n",
        )
        self.status_box.configure(state="disabled")

        self.btn_control = ctk.CTkButton(
            self,
            text="3. เริ่มบอท (Start)",
            fg_color="green",
            state="disabled",
            command=self.toggle_bot,
        )
        self.btn_control.pack(pady=12)

    def log(self, message):
        self.status_box.configure(state="normal")
        self.status_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.status_box.see("end")
        self.status_box.configure(state="disabled")

    def find_ldplayer_path(self):
        registry_paths = [
            r"SOFTWARE\XuanZhi\LDPlayer9",
            r"SOFTWARE\ChangZhi\LDPlayer9",
            r"SOFTWARE\XuanZhi\dnplayer",
        ]

        for reg_path in registry_paths:
            try:
                reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path)
                install_dir, _ = winreg.QueryValueEx(reg_key, "InstallDir")
                possible_adb = Path(install_dir) / "adb.exe"
                if possible_adb.exists():
                    return str(possible_adb)
            except OSError:
                continue

        fallback_paths = [
            r"E:\LDPlayer\LDPlayer9\adb.exe",
            r"C:\XuanZhi\LDPlayer9\adb.exe",
            r"C:\LDPlayer\LDPlayer9\adb.exe",
            r"D:\XuanZhi\LDPlayer9\adb.exe",
            r"D:\LDPlayer\LDPlayer9\adb.exe",
        ]
        for adb_path in fallback_paths:
            if Path(adb_path).exists():
                return adb_path

        return None

    def find_ld_console(self):
        if not self.adb_path:
            return None

        adb_dir = Path(self.adb_path).parent
        console_names = ["ldconsole.exe", "dnconsole.exe"]

        for name in console_names:
            console_path = adb_dir / name
            if console_path.exists():
                return str(console_path)
        return None

    def run_console_cmd(self, console_path, args, timeout=15):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            result = subprocess.run([console_path] + args, capture_output=True, text=True, startupinfo=startupinfo, timeout=timeout, encoding='utf-8', errors='ignore')
            return result.stdout, result.stderr
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "", "Console command failed or timed out"

    def run_adb_cmd(self, args, timeout=20, device=None):
        if not self.adb_path:
            return b"", b"", 1

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        command = [self.adb_path]
        if device:
            command.extend(["-s", device])
        command.extend(args)

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                startupinfo=startupinfo,
                timeout=timeout,
            )
            return result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired:
            return b"", b"ADB command timed out", 1

    def adb_text(self, args, timeout=20, device=None):
        stdout, stderr, code = self.run_adb_cmd(args, timeout=timeout, device=device)
        text = stdout.decode("utf-8", errors="ignore")
        err = stderr.decode("utf-8", errors="ignore")
        return text, err, code

    def get_connected_devices(self):
        output, _, _ = self.adb_text(["devices"])
        devices = []
        for line in output.splitlines():
            if "\tdevice" in line:
                devices.append(line.split("\t", 1)[0])
        self.devices = devices
        return devices, output

    def auto_connect(self):
        self.log("กำลังค้นหา adb.exe ของ LDPlayer...")
        self.adb_path = self.find_ldplayer_path()

        if not self.adb_path:
            self.log("ไม่พบ adb.exe กรุณาตรวจสอบตำแหน่ง LDPlayer")
            return

        self.log(f"พบ ADB: {self.adb_path}")
        self.run_adb_cmd(["start-server"])

        # 1. ลองใช้ ldconsole/dnconsole เพื่อหาพอร์ตที่แม่นยำ
        ld_console_path = self.find_ld_console()
        if ld_console_path:
            self.log(f"กำลังใช้ {Path(ld_console_path).name} เพื่อค้นหาพอร์ต...")
            output, err = self.run_console_cmd(ld_console_path, ["list2"])
            if output:
                lines = output.strip().splitlines()
                for line in lines:
                    # format: index,title,top_win_handle,bind_win_handle,android_started,pid,pid_hyperv,adb_port,adb_conn_state
                    parts = line.split(',')
                    if len(parts) > 7 and parts[7].isdigit():
                        port = parts[7]
                        # parts[4] is android_started (0 or 1)
                        if parts[4] == '1' and int(port) != -1:
                            self.log(f"พบ Instance ที่ทำงานอยู่บนพอร์ต: {port}")
                            self.adb_text(["connect", f"127.0.0.1:{port}"], timeout=5)
                            time.sleep(0.5)

        # 2. ตรวจสอบ device ที่เชื่อมต่อ
        devices, raw_output = self.get_connected_devices()
        if not devices:
            self.log("ไม่พบเครื่องที่เชื่อมต่อ, กำลังลองสแกนพอร์ตพื้นฐาน...")
            for port in (5554,5555, 5556, 5557, 5558, 5559, 5560, 5561, 5562):
                self.adb_text(["connect", f"127.0.0.1:{port}"], timeout=5)
                time.sleep(0.2)
            devices, raw_output = self.get_connected_devices()

        # 3. สรุปผล
        if devices:
            self.log(f"เชื่อมต่อสำเร็จ: {', '.join(devices)}")
            self.btn_launch.configure(state="normal")
            self.btn_control.configure(state="normal")
        else:
            self.log("ยังไม่พบ emulator ใน ADB")

    def find_efootball_package(self, device=None):
        output, _, _ = self.adb_text(["shell", "pm", "list", "packages"], device=device)
        packages = [line.replace("package:", "").strip() for line in output.splitlines()]

        preferred = [
            "jp.konami.pesam",
            "jp.konami.pesam.lite",
            "com.konami.efootball",
        ]
        for package_name in preferred:
            if package_name in packages:
                return package_name

        for package_name in packages:
            lowered = package_name.lower()
            if "konami" in lowered or "pes" in lowered or "efootball" in lowered:
                return package_name

        return None

    def launch_game(self):
        devices = self.devices or self.get_connected_devices()[0]
        if devices:
            for device in devices:
                package_name = self.find_efootball_package(device=device)
                if not package_name:
                    self.log(f"[{device}] ไม่พบ package ของ eFootball ใน emulator")
                    continue

                self.log(f"[{device}] กำลังเปิดเกม: {package_name}")
                self.adb_text(
                    [
                        "shell",
                        "monkey",
                        "-p",
                        package_name,
                        "-c",
                        "android.intent.category.LAUNCHER",
                        "1",
                    ],
                    timeout=10,
                    device=device,
                )
            return

        package_name = self.find_efootball_package()
        if not package_name:
            self.log("ไม่พบ package ของ eFootball ใน emulator")
            return

        self.log(f"กำลังเปิดเกม: {package_name}")
        self.adb_text(
            [
                "shell",
                "monkey",
                "-p",
                package_name,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            timeout=10,
        )

    def load_templates(self):
        if not TEMPLATE_DIR.exists():
            return []

        # กำหนดลำดับความสำคัญ: ยิ่งเลขน้อย ยิ่งทำก่อน
        # จัดการหน้าอัปเดต ปิดโฆษณา และรับของรางวัลให้เรียบร้อยตามลำดับ
        priority = {
            "popup_no": 2,
            "ok_button": 4,
            "download_button": 1,  # เจอหน้าดาวน์โหลดไฟล์อัปเดต ต้องกดทันที
            "banner_no": 2,        # หน้าต่างถามแบนเนอร์แนะนำ ให้เลือก "ไม่ใช่" เพื่อข้าม
            "continue_button": 3,  # ปุ่ม "ทำต่อ" ในหน้าล็อกอินรับของรางวัลต่างๆ
            "confirm_ok": 4,       # ปุ่ม "ตกลง" หลังจากกดรับของรางวัลเสร็จ
            "close_x": 5,          # ปุ่มปิดกากบาท X ตามหน้าต่างโฆษณาแบนเนอร์กิจกรรม
            "mailbox_icon": 6,     # ไอคอนกล่องจดหมายหน้าเมนูหลัก (ทำเมื่อไม่มี popup ค้างอยู่)
            "receive_all": 7,      # ปุ่ม "รับทั้งหมด" ภายในกล่องจดหมาย
            "back_button": 8,      # ปุ่ม "กลับ" เพื่อกลับสู่หน้าหลักหลังจากรับของเสร็จ
        }

        templates = []
        for path in TEMPLATE_DIR.glob("*.png"):
            if path.name == "templates_sheet.png":
                continue
            image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if image is None:
                continue
            
            # ปรับ threshold พื้นฐานที่ 0.80 (ลดปัญหาการตรวจจับผิดพลาด)
            # แต่บางปุ่ม เช่น ไอคอนจดหมาย อาจปรับลดลงเหลือ 0.75 ได้หากหาไม่เจอ
            current_threshold = 0.75 if path.stem in ["mailbox_icon", "close_x"] else 0.80

            templates.append(
                {
                    "name": path.stem,
                    "path": path,
                    "image": image,
                    "priority": priority.get(path.stem, 99),
                    "threshold": current_threshold,
                }
            )

        # เรียงลำดับตามความสำคัญก่อน-หลัง
        return sorted(templates, key=lambda item: item["priority"])

    def bot_core_logic_with_priority(self, device=None):
        while self.is_running:
            try:
                screen_img = self.get_screenshot(device=device)
                if screen_img is None:
                    self.log("ยังจับภาพหน้าจอไม่ได้ รอ ADB พร้อม...")
                    time.sleep(1.5)
                    continue

                match = self.find_template_match(screen_img)
                if match:
                    self.tap(match["x"], match["y"], device=device)
                    self.log(
                        f"พบเป้าหมาย: [{match['name']}] "
                        f"สมาตรเด่น ({match['score']:.2f}) -> ดำเนินการกดที่พิกัด {match['x']},{match['y']}"
                    )
                    
                    # ดีเลย์ตามความเหมาะสมของหน้าต่างเกม
                    if match["name"] in ["download_button", "receive_all"]:
                        time.sleep(5.0)  # หน้ารอโหลดหรือรับของขวัญ ให้เวลาระบบประมวลผลนานหน่อย
                    else:
                        time.sleep(2.5)  # หน้ากดข้ามทั่วไป ดีเลย์ปกติป้องกันเกมตอบสนองไม่ทัน
                else:
                    self.log("กำลังสแกนและตรวจสอบสถานะหน้าจอเกม...")
                    time.sleep(1.5)
            except Exception as exc:
                self.log(f"เกิดข้อผิดพลาดในการทำงาน: {exc}")
                time.sleep(2)

    def get_screenshot(self, device=None):
        stdout, _, _ = self.run_adb_cmd(["shell", "screencap", "-p"], timeout=10, device=device)
        if not stdout:
            return None

        # บาง ADB แทรก CRLF ทำให้ OpenCV อ่านภาพไม่ได้
        clean_bytes = stdout.replace(b"\r\n", b"\n")
        nparr = np.frombuffer(clean_bytes, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    def find_template_match(self, screen_img):
        gray_screen = cv2.cvtColor(screen_img, cv2.COLOR_BGR2GRAY)

        for item in self.templates:
            template = item["image"]
            if gray_screen.shape[0] < template.shape[0] or gray_screen.shape[1] < template.shape[1]:
                continue

            result = cv2.matchTemplate(gray_screen, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val >= item["threshold"]:
                h, w = template.shape[:2]
                return {
                    "name": item["name"],
                    "score": max_val,
                    "x": max_loc[0] + w // 2,
                    "y": max_loc[1] + h // 2,
                }

        return None

    def tap(self, x, y, device=None):
        self.run_adb_cmd(["shell", "input", "tap", str(int(x)), str(int(y))], timeout=5, device=device)

    def toggle_bot(self):
        if not self.is_running:
            self.templates = self.load_templates()
            if not self.templates:
                self.log(f"ไม่พบ template ในโฟลเดอร์ {TEMPLATE_DIR}")
                return

            self.is_running = True
            self.btn_control.configure(text="หยุดบอท (Stop)", fg_color="red")
            self.log(f"เริ่มสแกนด้วย template {len(self.templates)} ตัว")
            devices = self.devices or self.get_connected_devices()[0]
            if not devices:
                self.log("ยังไม่พบ emulator ใน ADB")
                self.is_running = False
                self.btn_control.configure(text="3. เริ่มบอท (Start)", fg_color="green")
                return

            for device in devices:
                threading.Thread(
                    target=self.bot_core_logic_with_priority,
                    args=(device,),
                    daemon=True,
                ).start()
        else:
            self.is_running = False
            self.btn_control.configure(text="3. เริ่มบอท (Start)", fg_color="green")
            self.log("หยุดบอทแล้ว")

    def bot_core_logic(self):
        while self.is_running:
            try:
                screen_img = self.get_screenshot()
                if screen_img is None:
                    self.log("ยังจับภาพหน้าจอไม่ได้ รอ ADB พร้อม...")
                    time.sleep(1.5)
                    continue

                match = self.find_template_match(screen_img)
                if match:
                    self.tap(match["x"], match["y"])
                    self.log(
                        f"เจอ {match['name']} "
                        f"({match['score']:.2f}) -> กดที่ {match['x']},{match['y']}"
                    )
                    time.sleep(2.0)
                else:
                    self.log("ยังไม่เจอปุ่มที่เทรนไว้ กำลังรอหน้าถัดไป...")
                    time.sleep(1.5)
            except Exception as exc:
                self.log(f"เกิดข้อผิดพลาด: {exc}")
                time.sleep(2)


if __name__ == "__main__":
    app = EFootballBotApp()
    app.mainloop()
