import time
from watchdog.observers import Observer # type: ignore
from watchdog.events import FileSystemEventHandler # type: ignore
import mpy_cross # type: ignore
import os
import json
import time
from Crypto.Cipher import AES # type: ignore
from base64 import b64encode
from Crypto.Util.Padding import pad # type: ignore

obj = {}
with open("config.json", "r") as file:
    obj = json.loads(file.read())


def encrypt(text):
    text = text + "~"
    cipher = AES.new(obj["db"]["key"].encode(), AES.MODE_CBC, obj["db"]["iv"].encode())
    ct_bytes = cipher.encrypt(pad(text.encode(), AES.block_size))
    ct = b64encode(ct_bytes).decode("utf-8")
    return ct_bytes


def decrypt(cyphers):
    try:
        cipher = AES.new(
            obj["db"]["key"].encode(), AES.MODE_CBC, obj["db"]["iv"].encode()
        )
        pt = cipher.decrypt(cyphers)
        pt = pt.decode()
        if "~" in pt:
            return pt.split("~")[0]
        return pt
    except (ValueError, KeyError):
        return {"error": "Failed to decrypt"}


class OnMyWatch:
    def __init__(self):
        self.observer = Observer()
        self.dir = os.listdir(obj["directories"]["src"])
        for file in self.dir:
            if file == "main.py":
                print("Compiling     ===>  % s" % file)
                os.system(
                    "cp "
                    + obj["directories"]["src"]
                    + "/"
                    + file
                    + " "
                    + obj["directories"]["target"]
                    + "/"
                    + file
                )
                print(" success* ")
                print(" ")

            if file == "database.json":
                print(" encrypting database.json to database.bin")
                hashed = None
                with open(
                    obj["directories"]["src"] + "/" + "database.json", "r"
                ) as db_json:
                    hashed = encrypt(db_json.read())

                with open(
                    obj["directories"]["target"] + "/" + "database.bin", "wb"
                ) as db_bin:
                    db_bin.write(hashed)
                    print("database hashed to ===> database.bin")
                    print(" success* ")
                    print(" ")

            if (
                file != "database.json"
                and file != "main.py"
                and file.split(".")[1] == "py"
            ):
                print("Compiling     ===>  % s" % file)
                mpy_cross.run(obj["directories"]["src"] + "/" + file)
                time.sleep(0.1)
                os.rename(
                    obj["directories"]["src"] + "/" + file.split(".")[0] + ".mpy",
                    obj["directories"]["target"] + "/" + file.split(".")[0] + ".mpy",
                )
                print(" success* ")
                print(" ")

        print("Watching for changes ******")
        print(" ")

    def run(self):
        event_handler = Handler()
        self.observer.schedule(event_handler, obj["directories"]["src"], recursive=True)
        self.observer.start()
        try:
            while True:
                time.sleep(5)
        except:
            self.observer.stop()
            print("Observer Stopped")

        self.observer.join()


class Handler(FileSystemEventHandler):
    @staticmethod
    def on_any_event(event):
        file = file = event.src_path.split("/")
        if event.is_directory:
            return None

        elif event.event_type == "created":
            if file[-1] == "main.py":
                os.system(
                    "cp "
                    + obj["directories"]["src"]
                    + "/"
                    + file[-1]
                    + " "
                    + obj["directories"]["target"]
                    + "/"
                    + file[-1]
                )

            if file[-1] == "database.json":
                print(" encrypting database.json to database.bin")
                hashed = None
                with open(
                    obj["directories"]["src"] + "/" + "database.json", "r"
                ) as db_json:
                    hashed = encrypt(db_json.read())

                with open(
                    obj["directories"]["target"] + "/" + "database.bin", "wb"
                ) as db_bin:
                    db_bin.write(hashed)
                    print("database hashed to ===> database.bin")
                    print(" success* ")
                    print(" ")

            elif file[-1].split(".")[1] == "py":
                print("Created new file ===>  % s" % file[-1])
                print("Compiling        ===>  % s" % file[-1])
                file = file
                mpy_cross.run(obj["directories"]["src"] + "/" + file[-1])
                time.sleep(0.1)
                os.rename(
                    obj["directories"]["src"] + "/" + file[-1].split(".")[0] + ".mpy",
                    obj["directories"]["target"]
                    + "/"
                    + file[-1].split(".")[0]
                    + ".mpy",
                )
                print("Output           ===>  % s" % file[-1].split(".")[0] + ".mpy")
                print(" success* ")
                print(" ")

        elif event.event_type == "modified":
            if file[-1] == "main.py":
                print("Modified file ===>  % s" % file[-1])
                print("Compiling     ===>  % s" % file[-1])
                os.system(
                    "cp "
                    + obj["directories"]["src"]
                    + "/"
                    + file[-1]
                    + " "
                    + obj["directories"]["target"]
                    + "/"
                    + file[-1]
                )
                print(" success* ")
                print(" ")

            if file[-1] == "database.json":
                print(" encrypting database.json to database.bin")
                hashed = None
                with open(
                    obj["directories"]["src"] + "/" + "database.json", "r"
                ) as db_json:
                    hashed = encrypt(db_json.read())

                with open(
                    obj["directories"]["target"] + "/" + "database.bin", "wb"
                ) as db_bin:
                    db_bin.write(hashed)
                    print(" database hashed to ===> database.bin")
                    print(" success* ")
                    print(" ")

            elif file[-1].split(".")[1] == "py" and file[-1] != "main.py":
                print("Modified file ===>  % s" % file[-1])
                print("Compiling     ===>  % s" % file[-1])
                mpy_cross.run(obj["directories"]["src"] + "/" + file[-1])
                time.sleep(0.1)
                os.rename(
                    obj["directories"]["src"] + "/" + file[-1].split(".")[0] + ".mpy",
                    obj["directories"]["target"]
                    + "/"
                    + file[-1].split(".")[0]
                    + ".mpy",
                )
                print("Output        ===>  % s" % file[-1].split(".")[0] + ".mpy")
                print(" success* ")
                print(" ")


if __name__ == "__main__":
    watch = OnMyWatch()
    watch.run()
