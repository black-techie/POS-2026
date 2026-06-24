from pico_i2c_lcd import I2cLcd
from Adafruit_Thermal import *
from machine import Pin, I2C, ADC  # type: ignore
from ucryptolib import aes  # type: ignore
from keypad import Keypad
import mfrc522
import struct
import time
import json
import network # type: ignore
import urequests # type: ignore


class Aes:
    def __init__(self, key, iv):
        self.key = key
        self.iv = iv
        self.MODE_CBC = 2

    def encrypt(self, plain):
        cipher = aes(self.key, self.MODE_CBC, self.iv)
        padded = plain + " " * (16 - len(plain) % 16)
        encrypted = cipher.encrypt(padded)
        return encrypted

    def decrypt(self, encrypted):
        decipher = aes(self.key, self.MODE_CBC, self.iv)
        decrypted = decipher.decrypt(encrypted)
        if "~" in decrypted.decode():
            return decrypted.decode().split("~")[0]
        return decrypted.decode()


class POS:
    def __init__(self, buzzerPin=15, batteryPin=2, lcdSda=21, lcdScl=22):
        self.station = network.WLAN(network.STA_IF)
        self.printer = Adafruit_Thermal(bus=2, heatdots=5, heatinterval=40)
        self.pvk = b"####^%^&*((!&^@&)***!@_!#)(!_!#)"
        self.siv = b":@*&^%$%$##$%876"
        self.default_password = self.rj()["key"]
        self.price_per_litter = self.rj()["ppl"]
        self.adc = ADC(Pin(2))
        self.adc1 = ADC(Pin(35))

        keys = [
            ["1", "2", "3", "A"],
            ["4", "5", "6", "B"],
            ["7", "8", "9", "C"],
            ["*", "0", "#", "D"],
        ]
        row_pins = [Pin(13), Pin(12), Pin(14), Pin(27)]
        column_pins = [Pin(26), Pin(25), Pin(33), Pin(32)]
        self.buzzerPin = buzzerPin
        self.batteryPin = batteryPin
        self.lcd = I2cLcd(
            I2C(0, sda=Pin(lcdSda), scl=Pin(lcdScl), freq=400000), 0x27, 4, 20
        )
        self.rfid = mfrc522.MFRC522(sck=18, miso=19, mosi=23, cs=4, rst=5)
        self.keypad = Keypad(row_pins, column_pins, keys)
        del (row_pins, column_pins, keys)

    def float_to_bytes(self, value):
        return struct.pack("f", value)

    def int_to_bytes(self, value):
        return struct.pack("I", value)

    def pad_to_16_bytes(self, data):
        return data + b"\x00" * (16 - len(data))

    def loading_screen(self, interval=3, function=None, percentage=False):
        resp = function()
        self.lcd.clear()
        spinner = ["|", "/", "-", "`"]
        now = time.time()
        while time.time() - now < interval:
            for symbol in spinner:
                if not percentage:
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr(
                        "       " + symbol + symbol + symbol + symbol + symbol + symbol
                    )
                else:
                    self.lcd.move_to(16, 3)
                    self.lcd.putstr(
                        str(int(((time.time() - now) / interval) * 100)) + "%"
                    )
                time.sleep(0.2)
        self.lcd.clear()
        time.sleep(0.2)
        del spinner, now
        return resp

    def rj(self):
        dt = None
        with open("database.json", "r") as file:
            dt = json.loads(file.read())
        return dt

    def wj(self, dt):
        res = False
        with open("database.json", "w") as file:
            try:
                file.write(json.dumps(dt))
                res = True
            except Exception as e:
                print("Error writing database File => {}".format(e))
        return res
    
    def map_value(self, x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min


    def register_rfid(self, method=0, obj={}):
        srt = b"####^%^&*((!&^@&)***!@_!#)(!_!#)"
        iv = b":@*&^%$%$##$%876"
        secret = Aes(srt, iv)
        user_type = 2050
        user_type_padded = self.pad_to_16_bytes(self.int_to_bytes(user_type))
        try:
            while True:
                key = self.listen_keypad()
                data = self.rj()
                (stat, tag_type) = self.rfid.request(self.rfid.REQIDL)
                if stat == self.rfid.OK:
                    (stat, raw_uid) = self.rfid.anticoll()
                    if stat == self.rfid.OK:
                        if self.rfid.select_tag(raw_uid) == self.rfid.OK:
                            key = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]
                            crd = str(int.from_bytes(bytes(raw_uid), "little", False))
                            crd = crd[:11]
                            if (
                                self.rfid.auth(self.rfid.AUTHENT1A, 8, key, raw_uid)
                                == self.rfid.OK
                            ):
                                x = None
                                if method == 0:
                                    x = secret.encrypt(json.dumps({"topUp": {crd: 0}}))
                                    data["transactions"].append({"new_user": {crd: 0}})
                                elif method == 1:
                                    x = secret.encrypt(
                                        json.dumps({"topUp": {crd: int(obj["topUp"])}})
                                    )
                                    data["transactions"].append(
                                        {"topUp": {crd: obj["topUp"]}}
                                    )
                                elif method == 2:
                                    x = secret.encrypt(
                                        json.dumps({"remove_user": [crd]})
                                    )
                                    data["transactions"].append({"remove_user": [crd]})
                                elif method == 3:
                                    x = secret.encrypt(
                                        json.dumps({"calibration_factor": obj["cf"]})
                                    )
                                    data["settings"].append(
                                        {"calibration_factor": obj["cf"]}
                                    )
                                elif method == 4:
                                    x = secret.encrypt(
                                        json.dumps({"price_per_little": obj["ppl"]})
                                    )
                                    data["settings"].append(
                                        {"price_per_little": obj["ppl"]}
                                    )
                                    self.price_per_litter = obj["ppl"] * 1000
                                    data["ppl"] = self.price_per_litter
                                elif method == 5:
                                    x = secret.encrypt(
                                        json.dumps({"lock_this_meter": obj["lock"]})
                                    )
                                    data["settings"].append(
                                        {"lock_this_meter": obj["lock"]}
                                    )
                                elif method == 6:
                                    x = secret.encrypt(
                                        json.dumps({"reset_this_meter": obj["rst"]})
                                    )
                                    data["settings"].append(
                                        {"reset_this_meter": obj["rst"]}
                                    )
                                first_half = x[:16]
                                second_half = x[16:]
                                self.rfid.write(8, first_half)
                                self.rfid.write(9, second_half)
                                self.rfid.write(10, user_type_padded)
                                self.rfid.stop_crypto1()
                                self.wj(data)
                                del data
                                return crd
                            else:
                                print("")
                        else:
                            print("")
                if key == "*":
                    break
        except KeyboardInterrupt:
            print("EXITING PROGRAM")
        self.lcd.clear()

    def stupid_function(self):
        pass

    def splash_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 1)
        self.lcd.putstr(" NYIRENDA'S COMPANY")
        self.lcd.move_to(0, 2)
        self.lcd.putstr("       LIMITED")
        time.sleep(1)
        self.lcd.clear()
        time.sleep(0.2)

    def init_gpio(self):
        ADC(Pin(2))
        self.buzzer = Pin(self.buzzerPin, Pin.OUT)
        self.buzzer.off()
        self.battery = Pin(self.batteryPin, Pin.IN)

    def listen_keypad(self):
        return self.keypad.read_keypad()

    def status_icon(self, status):
        self.lcd.move_to(7, 0)
        if status == 0:
            self.lcd.putstr(" ")

        elif status == 1:
            self.lcd.custom_char(
                5, bytearray([0x1F, 0x00, 0x0E, 0x11, 0x1F, 0x10, 0x0E, 0x00])
            )
            self.lcd.putstr(chr(5))

        elif status == 2:
            self.lcd.custom_char(
                6, bytearray([0x1F, 0x00, 0x0E, 0x10, 0x0E, 0x01, 0x0E, 0x00])
            )
            self.lcd.putstr(chr(6))

        elif status == 3:
            self.lcd.custom_char(
                7, bytearray([0x1F, 0x11, 0x15, 0x15, 0x11, 0x15, 0x11, 0x1F])
            )
            self.lcd.putstr(chr(7))

        del status
        # gc.collect()
        return 0

    def battery_icon(self, level, charging=False):
        battery = [
            bytearray([0x1F, 0x10, 0x14, 0x14, 0x14, 0x14, 0x10, 0x1F]),
            bytearray([0x1F, 0x10, 0x16, 0x16, 0x16, 0x16, 0x10, 0x1F]),
            bytearray([0x1F, 0x10, 0x17, 0x17, 0x17, 0x17, 0x10, 0x1F]),
            bytearray([0x1E, 0x02, 0x03, 0x03, 0x03, 0x03, 0x02, 0x1E]),
            bytearray([0x1E, 0x02, 0x13, 0x13, 0x13, 0x13, 0x02, 0x1E]),
            bytearray([0x1E, 0x02, 0x1B, 0x1B, 0x1B, 0x1B, 0x02, 0x1E]),
            bytearray([0x1E, 0x02, 0x03, 0x03, 0x03, 0x03, 0x02, 0x1E]),
            bytearray([0x0A, 0x0A, 0x1F, 0x1F, 0x1F, 0x0E, 0x04, 0x04]),
        ]
        self.lcd.custom_char(
            4, bytearray([0x0A, 0x0A, 0x1F, 0x1F, 0x1F, 0x0E, 0x04, 0x04])
        )

        if level <= 20:
            if level <= 10:
                pass
                # close valve is battery is very low
            self.lcd.custom_char(0, battery[0])
            self.lcd.custom_char(1, battery[6])
            self.lcd.move_to(0, 0)
            self.lcd.putstr(
                chr(0) + chr(1) +"20%   "
                if not charging
                else chr(0) + chr(1) + chr(4) + "   "
            )

        elif level <= 40:
            self.lcd.custom_char(0, battery[1])
            self.lcd.custom_char(1, battery[6])
            self.lcd.move_to(0, 0)
            self.lcd.putstr(
                chr(0) + chr(1)  +"40%   "
                if not charging
                else chr(0) + chr(1) + chr(4) + "   "
            )

        elif level <= 60:
            self.lcd.custom_char(0, battery[2])
            self.lcd.custom_char(1, battery[6])
            self.lcd.move_to(0, 0)
            self.lcd.putstr(
                chr(0) + chr(1)  +"60%   "
                if not charging
                else chr(0) + chr(1) + chr(4) + "   "
            )

        elif level <= 80:
            self.lcd.custom_char(0, battery[2])
            self.lcd.custom_char(1, battery[4])
            self.lcd.move_to(0, 0)
            self.lcd.putstr(
                chr(0) + chr(1)  +"80%   "
                if not charging
                else chr(0) + chr(1) + chr(4) + "   "
            )

        elif level <= 90:
            self.lcd.custom_char(0, battery[2])
            self.lcd.custom_char(1, battery[5])
            self.lcd.move_to(0, 0)
            self.lcd.putstr(
                chr(0) + chr(1)  +"90%   "
                if not charging
                else chr(0) + chr(1) + chr(4) + "   "
            )
        else:
            self.lcd.custom_char(0, battery[2])
            self.lcd.custom_char(1, battery[5])
            self.lcd.move_to(0, 0)
            self.lcd.putstr(
                chr(0) + chr(1)  +"100%   "
                if not charging
                else chr(0) + chr(1) + chr(4) + "   "
            )
        del battery, level, charging
        # gc.collect()
        return 0

    def network_icon(self, level):
        net = [
            bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00]),
            bytearray([0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x10, 0x00]),
            bytearray([0x00, 0x00, 0x00, 0x08, 0x08, 0x18, 0x18, 0x00]),
            bytearray([0x00, 0x00, 0x04, 0x0C, 0x0C, 0x1C, 0x1C, 0x00]),
            bytearray([0x00, 0x02, 0x06, 0x0E, 0x0E, 0x1E, 0x1E, 0x00]),
            bytearray([0x00, 0x02, 0x06, 0x0E, 0x0E, 0x1E, 0x1E, 0x00]),
        ]

        self.lcd.custom_char(
            3, bytearray([0x1F, 0x15, 0x0E, 0x04, 0x04, 0x04, 0x04, 0x00])
        )
        if level <= 10:
            self.lcd.custom_char(2, net[0])
            self.lcd.move_to(18, 0)
            self.lcd.putstr(chr(3) + chr(2))

        elif level <= 20:
            self.lcd.custom_char(2, net[1])
            self.lcd.move_to(18, 0)
            self.lcd.putstr(chr(3) + chr(2))

        elif level <= 40:
            self.lcd.custom_char(2, net[2])
            self.lcd.move_to(18, 0)
            self.lcd.putstr(chr(3) + chr(2))

        elif level <= 60:
            self.lcd.custom_char(2, net[3])
            self.lcd.move_to(18, 0)
            self.lcd.putstr(chr(3) + chr(2))

        elif level <= 80:
            self.lcd.custom_char(2, net[4])
            self.lcd.move_to(18, 0)
            self.lcd.putstr(chr(3) + chr(2))

        else:
            self.lcd.custom_char(2, net[5])
            self.lcd.move_to(18, 0)
            self.lcd.putstr(chr(3) + chr(2))
        del level, net
        # gc.collect()
        return 0

    def boot_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Booting up...")
        time.sleep(1)

    def print_process_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Repoti/Risiti")
        time.sleep(1)
        self.lcd.move_to(0, 2)
        self.lcd.putstr("1. Angalia Ripoti")
        self.lcd.move_to(0, 3)
        self.lcd.putstr("2. Wasilisha Ripoti")
        while 1:
            key = self.listen_keypad()
            if key == "1":
                data =  self.rj()
                settings = data["settings"]
                amount  = 0
                transactions = 0
                new_customers = 0
                cpy = data["transactions"]
                del data
                for x in cpy:
                    if "topUp" in x:
                        f = x["topUp"]
                        for k, v in f.items():
                            amount = amount + v
                            transactions = transactions +1
                    else:
                        new_customers = new_customers+1
                amount = int(amount)
                amount = str(amount)
                if len(amount) > 3:
                    amount = amount[:-3] + "," + amount[-3:]
                self.lcd.clear()
                self.lcd.move_to(0, 0)
                self.lcd.putstr("Mauzo = "+amount+"TSH")
                self.lcd.move_to(0, 1)
                self.lcd.putstr("Miamala = "+str(transactions))
                self.lcd.move_to(0, 2)
                self.lcd.putstr("Marekebisho = "+str(len(settings)))
                self.lcd.move_to(0, 3)
                self.lcd.putstr("Wateja Wapya = "+str(new_customers))
                time.sleep(4)
                break
            elif key == "2":
                self.send_report_wifi()
                break

    def main_screen(self):
        self.lcd.clear()
        x = self.map_value(((self.adc.read_u16()/65534) *4.2), 3.6, 4.2, 0, 100)
        y = True if self.adc1.read() > 2000 else False
        self.battery_icon(x, y)
        self.network_icon(80)
        self.status_icon(0)
        self.lcd.move_to(0, 2)
        self.lcd.putstr("1. Menyu Kuu")
        self.lcd.move_to(0, 3)
        self.lcd.putstr("2. Sajili Kadi")
        time.sleep(1)
        timer = time.time()
        while 1:
            if(time.time() - timer) > 5:
                x = self.map_value(((self.adc.read_u16()/65534) *4.2), 3.6, 4.2, 0, 100)
                y = True if self.adc1.read() > 2000 else False
                self.battery_icon(x,y)
                timer = time.time()
            
            key = self.listen_keypad()
            if key == "1":
                self.main_menu_screen()
                self.lcd.clear()
                self.battery_icon(x,y)
                self.network_icon(80)
                self.lcd.move_to(0, 2)
                self.lcd.putstr("1. Menyu Kuu")
                self.lcd.move_to(0, 3)
                self.lcd.putstr("2. Sajili Kadi")
            elif key == "2":
                self.register_user_screen()
                self.lcd.clear()
                self.battery_icon(x,y)
                self.network_icon(80)
                self.status_icon(0)
                self.lcd.move_to(0, 2)
                self.lcd.putstr("1. Menyu Kuu")
                self.lcd.move_to(0, 3)
                self.lcd.putstr("2. Sajili Kadi")

    def main_menu_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Menyu Kuu")
        time.sleep(1.5)
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("1. Ongeza Salio")
        self.lcd.move_to(0, 1)
        self.lcd.putstr("2. Ondoa Mteja")
        self.lcd.move_to(0, 2)
        self.lcd.putstr("3. Ripoti/Risiti")
        self.lcd.move_to(0, 3)
        self.lcd.putstr("4. Zaidi")
        time.sleep(1)
        while 1:
            key = self.listen_keypad()
            if key == "1":
                self.transaction_screen()
                break
            elif key == "2":
                self.remove_user_screen()
                break
            elif key == "3":
                self.print_process_screen()
                break
            elif key == "4":
                self.settings_screen()
                break
            elif key == "*":
                break

    def register_user_screen(self):
        self.lcd.clear()
        self.lcd.putstr("Sajili Kadi")
        time.sleep(1)
        self.lcd.clear()
        self.lcd.move_to(0, 3)
        self.lcd.putstr("1. Kuendelea")
        time.sleep(2)
        while 1:
            key = self.listen_keypad()
            if key == "1":
                self.lcd.clear()
                self.lcd.move_to(0, 1)
                self.lcd.putstr("   TAFADHALI WEKA")
                self.lcd.move_to(0, 2)
                self.lcd.putstr("        KADI")
                time.sleep(1)
                card = self.register_rfid(method=0)
                if card:
                    self.lcd.clear()
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("USAJILI UMEKAMILIKA")
                    self.lcd.move_to(0, 3)
                    self.lcd.putstr("  no " + str(card))
                    time.sleep(1)
                break
            elif key == "*":
                break

    def remove_user_screen(self):
        self.lcd.clear()
        self.lcd.putstr("Ondoa Mteja")
        time.sleep(1)
        self.lcd.clear()
        self.lcd.move_to(0, 3)
        self.lcd.putstr("1. Kuendelea")
        time.sleep(2)
        while 1:
            key = self.listen_keypad()
            if key == "1":
                self.lcd.clear()
                self.lcd.move_to(0, 1)
                self.lcd.putstr("   TAFADHALI WEKA")
                self.lcd.move_to(0, 2)
                self.lcd.putstr("        KADI")
                time.sleep(1)
                card = self.register_rfid(method=2)
                if card:
                    self.lcd.clear()
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr(" USAJILI UMEFUTWA")
                    self.lcd.move_to(0, 3)
                    self.lcd.putstr(" no " + str(card))
                    time.sleep(1)
                break
            elif key == "*":
                break

    def transaction_screen(self):
        ln = len(self.rj()["transactions"])
        if(ln > 60):
            self.lcd.clear()
            self.lcd.move_to(0, 1)
            self.lcd.putstr("Tafadhali Tuma Ripoti")
            self.lcd.move_to(0, 2)
            self.lcd.putstr(" Na ujaribu tena !")
            time.sleep(5)
            self.lcd.clear()
            return 0
        unit_price = self.price_per_litter
        self.lcd.clear()
        self.lcd.putstr("Ongeza salio")
        time.sleep(1)
        self.lcd.clear()
        self.lcd.move_to(0, 1)
        self.lcd.putstr("GHARAMA = 0TZS")
        time.sleep(1)
        charge = ""
        while 1:
            key = self.listen_keypad()
            if key and key.isdigit():
                charge = charge + key
                self.lcd.move_to(0, 1)
                self.lcd.putstr("GHARAMA = " + charge + "TZS    ")
                time.sleep(0.5)
            elif key == "#" and charge != "":
                charge = int(charge) / unit_price
                self.lcd.clear()
                self.lcd.move_to(0, 1)
                self.lcd.putstr("   TAFADHALI WEKA")
                self.lcd.move_to(0, 2)
                self.lcd.putstr("        KADI")
                time.sleep(1)
                card = self.register_rfid(method=1, obj={"topUp": charge * 1000})
                if card:
                    self.lcd.clear()
                    self.lcd.move_to(0, 0)
                    self.lcd.putstr("   UMEONGEZA SALIO")
                    self.lcd.move_to(0, 2)
                    self.lcd.putstr("KADI : " + str(card))
                    self.lcd.move_to(0, 3)
                    self.lcd.putstr("SALIO: " + str(charge * 1000) + "L")
#                     self.print_receipt(
#                         card=card,
#                         amount=charge * unit_price,
#                         unit_price=unit_price,
#                         total_units=charge,
#                     )
                    time.sleep(2)
                break
            elif key == "*":
                if charge != "":
                    charge = str(charge)[:-1]
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("GHARAMA = " + charge + "TZS    ")
                    time.sleep(0.5)
                else:
                    break

    def settings_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Zaidi")
        time.sleep(1)
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("1. Badili Kipimo")
        self.lcd.move_to(0, 1)
        self.lcd.putstr("2. Badili gharama")
        self.lcd.move_to(0, 2)
        self.lcd.putstr("3. Funga/Fungua Mita")
        self.lcd.move_to(0, 3)
        self.lcd.putstr("4. Boresha Ufanisi")
        time.sleep(1)
        while 1:
            key = self.listen_keypad()
            if key == "1":
                self.change_calibration_factor()
                break
            elif key == "2":
                self.change_price_per_volume()
                break
            elif key == "3":
                self.lock_unlock_meter()
                break
            elif key == "4":
                self.clear_meter()
                break
            elif key == "5":
                self.change_password_screen()
                break
            elif key == "*":
                break

    def change_price_per_volume(self):
        self.lcd.clear()
        self.lcd.putstr("Gharama Za Maji")
        time.sleep(1)
        self.lcd.clear()
        self.lcd.move_to(0, 1)
        self.lcd.putstr("PPL = " + str(self.price_per_litter) + "/Unit")
        time.sleep(1)
        charge = ""
        while 1:
            key = self.listen_keypad()
            if key and key.isdigit():
                charge = charge + key
                self.lcd.move_to(0, 1)
                self.lcd.putstr("PPL = " + charge + "/Unit       ")
                time.sleep(0.5)
            elif key == "#" and charge != "":
                if "." in charge:
                    charge = float(charge)
                    self.lcd.clear()
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("   TAFADHALI WEKA")
                    self.lcd.move_to(0, 2)
                    self.lcd.putstr("        KADI")
                    time.sleep(1)
                    card = self.register_rfid(method=4, obj={"ppl": (charge / 1000)})
                    if card:
                        self.lcd.clear()
                        self.lcd.move_to(0, 1)
                        self.lcd.putstr("UMEBADILISHA GHARAMA")
                        self.lcd.move_to(0, 2)
                        self.lcd.putstr("Kwenda =" + str(charge) + "/Unit")
                        time.sleep(4)
                        return 0
                else:
                    charge = charge + "."
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("PPL = " + charge + "/Unit        ")
                    time.sleep(0.5)
            elif key == "*":
                if charge != "":
                    charge = charge[:-1]
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("PPL = " + charge + "/Unit       ")
                    time.sleep(0.5)
                else:
                    break

    def change_calibration_factor(self):
        self.lcd.clear()
        self.lcd.putstr("Badili Kipimo")
        time.sleep(1)
        self.lcd.clear()
        self.lcd.move_to(0, 1)
        self.lcd.putstr("CF = 0")
        time.sleep(1)
        charge = ""
        while 1:
            key = self.listen_keypad()
            if key and key.isdigit():
                charge = charge + key
                self.lcd.move_to(0, 1)
                self.lcd.putstr("CF = " + charge + "    ")
                time.sleep(0.5)
            elif key == "#" and charge != "":
                if "." in charge:
                    charge = float(charge)
                    self.lcd.clear()
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("   TAFADHALI WEKA")
                    self.lcd.move_to(0, 2)
                    self.lcd.putstr("        KADI")
                    time.sleep(1)
                    card = self.register_rfid(method=3, obj={"cf": charge})
                    if card:
                        self.lcd.clear()
                        self.lcd.move_to(0, 1)
                        self.lcd.putstr("UMEBADILISHA KIPIMO")
                        self.lcd.move_to(0, 2)
                        self.lcd.putstr("Kwenda =" + str(charge))
                        time.sleep(4)
                        return 0
                else:
                    charge = charge + "."
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("CF = " + charge + "    ")
                    time.sleep(0.5)
            elif key == "*":
                if charge != "":
                    charge = str(charge)[:-1]
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("CF = " + charge + "    ")
                    time.sleep(0.5)
                else:
                    break

    def lock_unlock_meter(self):
        self.lcd.clear()
        self.lcd.putstr("Funga/Fungua Mita")
        time.sleep(1)
        self.lcd.clear()
        self.lcd.move_to(0, 2)
        self.lcd.putstr("1. Zuia Huduma")
        self.lcd.move_to(0, 3)
        self.lcd.putstr("2. Ruhusu Huduma")
        time.sleep(2)
        while 1:
            key = self.listen_keypad()
            status = False
            if key == "1" or key == "2":
                self.lcd.clear()
                self.lcd.move_to(0, 1)
                self.lcd.putstr("   TAFADHALI WEKA")
                self.lcd.move_to(0, 2)
                self.lcd.putstr("        KADI")
                time.sleep(1)
                if key == 1:
                    status = True
                card = self.register_rfid(method=5, obj={"lock": status})
                if card:
                    self.lcd.clear()
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("     IMEFANIKIWA")
                    time.sleep(1)
                break
            elif key == "*":
                break

    def clear_meter(self):
        self.lcd.clear()
        self.lcd.putstr("Boresha ufanisi")
        time.sleep(1)
        self.lcd.clear()
        self.lcd.move_to(0, 3)
        self.lcd.putstr("1. Kuendelea")
        time.sleep(2)
        while 1:
            key = self.listen_keypad()
            if key == "1":
                self.lcd.clear()
                self.lcd.move_to(0, 1)
                self.lcd.putstr("   TAFADHALI WEKA")
                self.lcd.move_to(0, 2)
                self.lcd.putstr("        KADI")
                time.sleep(1)
                card = self.register_rfid(method=6, obj={"rst": True})
                if card:
                    self.lcd.clear()
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("     IMEFANIKIWA")
                    time.sleep(1)
                break
            elif key == "*":
                break

    def error_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Error")
        time.sleep(1)

    def calibration_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Calibration")
        time.sleep(1)

    def report_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Report")
        time.sleep(1)

    def meter_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Meter")
        time.sleep(1)

    def buzzer(self, duration=0.5):
        buzzer = Pin(self.buzzerPin, Pin.OUT)
        buzzer.on()
        time.sleep(duration)
        buzzer.off()
        time.sleep(duration)

    def success_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Success")
        time.sleep(1)

    def failure_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Failure")
        time.sleep(1)

    def print_receipt_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Printing Receipt")
        time.sleep(1)
        self.lcd.move_to(0, 1)
        self.lcd.putstr("Please wait...")
        time.sleep(1)

    def change_password_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Badili Nywila")
        time.sleep(1)
        isValid = self.login_screen()
        if isValid:
            input_pass = ""
            self.lcd.clear()
            self.lcd.move_to(0, 0)
            self.lcd.putstr("Nywila Mpya")
            time.sleep(1)
            self.lcd.clear()
            self.lcd.move_to(0, 1)
            self.lcd.putstr(" WEKA NAMBA YA SIRI")
            while 1:
                key = self.listen_keypad()
                if key and key.isdigit() and len(input_pass) < 6:
                    input_pass = input_pass + key
                    tmp = ""
                    for c in input_pass:
                        tmp += "*"
                    self.lcd.move_to(7, 3)
                    self.lcd.putstr(tmp + "          ")
                    time.sleep(0.3)
                elif key == "#" and len(input_pass) >= 6:
                    data = self.rj()
                    data["key"] = input_pass
                    self.wj(data)
                    self.lcd.clear()
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("     IMEFANIKIWA")
                    time.sleep(1)
                    break
            else:
                self.lcd.clear()
                self.lcd.move_to(0, 1)
                self.lcd.putstr("   IMESHINDIKANA")
                time.sleep(2)
            return 0

    def login_screen(self):
        self.lcd.clear()
        self.lcd.move_to(0, 1)
        self.lcd.putstr(" WEKA NAMBA YA SIRI")
        self.lcd.move_to(7, 3)
        self.lcd.putstr("")
        time.sleep(1)
        default = self.default_password
        input_pass = ""
        while 1:
            key = self.listen_keypad()
            if key and key.isdigit() and len(input_pass) < 6:
                input_pass = input_pass + key
                tmp = ""
                for c in input_pass:
                    tmp += "*"
                self.lcd.move_to(7, 3)
                self.lcd.putstr(tmp + "          ")
                time.sleep(0.3)
            elif key == "#" and len(input_pass) >= 4:
                if input_pass == default:
                    return True
                else:
                    input_pass = ""
                    self.lcd.clear()
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr("   IMESHINDIKANA")
                    time.sleep(2)
                    self.lcd.clear()
                    self.lcd.move_to(0, 1)
                    self.lcd.putstr(" WEKA NAMBA YA SIRI")
                    tmp = ""
                    for c in input_pass:
                        tmp += "*"
                    self.lcd.move_to(7, 3)
                    self.lcd.putstr(tmp + "          ")

            elif key == "*":
                if input_pass != "":
                    input_pass = input_pass[:-1]
                    tmp = ""
                    for c in input_pass:
                        tmp += "*"
                    self.lcd.move_to(7, 3)
                    self.lcd.putstr(tmp + "          ")
                    time.sleep(0.5)
                else:
                    break

    def print_receipt(self, card, amount, unit_price, total_units):
        self.printer.wake()
        self.printer.setSize("S")
        self.printer.justify("C")
        self.printer.println("")
        self.printer.println("Nyirenda's CO.Ltd")
        self.printer.println("P.O Box 77667, Dar-Es-Salaam")
        self.printer.println("Tel: +255789105606")
        self.printer.println("Prepaid Water Meter -  Sipungu")
        self.printer.println(".................................")
        self.printer.println(" ")
        self.printer.justify("L")
        self.printer.setSize("M")
        self.printer.println("Customer id    - " + str(card))
        self.printer.println("Amount         - " + str(amount) + "TZS")
        self.printer.println("Unit Price     - " + str(unit_price) + " TZS")
        self.printer.println("Total          - " + str(total_units) + " units")
        self.printer.println(".................................")
        self.printer.println("\n ")
        self.printer.sleep()

    def connect_wifi(self):
        self.station.active(True)
        while not self.station.isconnected():
            self.lcd.clear()
            self.lcd.move_to(0, 0)
            self.lcd.putstr(" connecting to wifi")
            self.lcd.move_to(0, 2)
            self.lcd.putstr("SSID: pos129988")
            self.lcd.move_to(0, 3)
            self.lcd.putstr("SSKY: *********")
            time.sleep(1)
            try:
                self.station.connect("pos129988", "pos129988")
            except:
                self.lcd.clear()
                self.lcd.move_to(0, 0)
                self.lcd.putstr(" failed to connect!")
                time.sleep(2)
        return 0

    def send_report_wifi(self, data={}):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Sending report")
        time.sleep(1)
        try:
            self.connect_wifi()
            self.lcd.clear()
            self.lcd.move_to(0, 0)
            self.lcd.putstr(" Connected to wifi")
            self.lcd.move_to(0, 2)
            self.lcd.putstr(" sending report")
            print("Connected!")
            print("My IP Address:", self.station.ifconfig()[0])
            time.sleep(1)
            data =  self.rj()
            api_key = data["api_key"]
            transactions = data["transactions"]
            settings = data["settings"]
            while self.station.isconnected():
                response = urequests.post(
                    "http://nyirendas-engine-2025.koyeb.app/api/v0.1/updown/pos/upload",
                    headers={"content-type": "application/json; charset=utf-8"},
                    data=json.dumps(
                        {"api_key": api_key, "transactions": transactions, "settings": settings}
                    ),
                )
                if response.status_code == 201:
                    data["transactions"] = []
                    data["settings"] = []
                    self.wj(data)
                    break
                else:
                    self.lcd.clear()
                    self.lcd.move_to(0, 0)
                    self.lcd.putstr("Failed to send!")
                    self.lcd.move_to(0, 2)
                    self.lcd.putstr("Retrying ..")
                    time.sleep(2)
            del data
            self.disconnect_wifi()
            self.lcd.clear()
            self.lcd.move_to(0, 0)
            self.lcd.putstr("Report sent!")
            time.sleep(1)
        except Exception as e:
            print(e)
            self.lcd.clear()
            self.lcd.move_to(0, 0)
            self.lcd.putstr("Failed to send!")
            time.sleep(2)

    def disconnect_wifi(self):
        self.station.active(False)

    def display_units(self):
        self.lcd.clear()
        self.lcd.move_to(0, 0)
        self.lcd.putstr("Units")
        time.sleep(1)
    


    def loading_animation(self):
        self.lcd.clear()
        spinner = ["|", "/", "-", "`"]
        while True:
            for symbol in spinner:
                self.lcd.move_to(0, 1)
                self.lcd.putstr(
                    "       " + symbol + symbol + symbol + symbol + symbol + symbol
                )
                time.sleep(0.2)


x = POS()
x.loading_screen(3, x.init_gpio)
x.login_screen()
x.loading_screen(3, x.stupid_function)
x.splash_screen()
x.main_screen()


