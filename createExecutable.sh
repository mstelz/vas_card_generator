pyinstaller --onefile --name VASCardGenerator --add-data "fonts:fonts" --add-data "shipcard.html:." generate.py
mv ./dist/VASCardGenerator.exe .
rm -rf dist
rm -rf build