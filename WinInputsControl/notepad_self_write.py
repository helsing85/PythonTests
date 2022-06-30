#Windows
#Open Notepad and write some text using keyboard

import os
from time import sleep
import keyboard
import pyautogui

os.system(f"start notepad.exe")

fw = None

while fw == None:
    sleep(1)
    fw = pyautogui.getWindowsWithTitle('Notepad')

notepad_win = fw[0]
while True:
    notepad_win.activate()
    pyautogui.keyDown('ctrl')
    pyautogui.keyDown('a')
    pyautogui.keyUp('a')
    pyautogui.keyUp('ctrl')
    pyautogui.write(['delete'])
    sleep(1)
    pyautogui.write(
        'Neque porro quisquam est qui dolorem ipsum quia dolor sit amet, consectetur, adipisci velit...', 0.25)
    sleep(10)

print(fw)
