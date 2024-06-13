::  執行虛擬空間
call D:\pythonProject\台股網格自動化交易書\.venv\Scripts\activate.bat

:: 切換路徑
D:
cd "D:\pythonProject\台股網格自動化交易書"

:: 執行策略推播程式
call python.exe -i 8_1_網格交易實單程式_元富版本.py

