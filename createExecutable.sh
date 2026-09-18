pyinstaller --onefile --name VASCardGenerator \
    --add-data "fonts:fonts" \
    --add-data "shipcard.html:." \
    --exclude-module PyQt5 \
    --exclude-module PyQt5_sip \
    --exclude-module PySide6 \
    --exclude-module matplotlib \
    --exclude-module scipy \
    --exclude-module IPython \
    --exclude-module tkinter \
    --exclude-module astropy \
    --exclude-module skimage \
    --exclude-module torch \
    --exclude-module numba \
    --exclude-module sqlalchemy \
    --exclude-module openpyxl \
    --exclude-module tables \
    generate.py

if [ -f "./dist/VASCardGenerator.exe" ]; then
    mv ./dist/VASCardGenerator.exe .
elif [ -f "./dist/VASCardGenerator" ]; then
    mv ./dist/VASCardGenerator .
fi
rm -rf dist
rm -rf build