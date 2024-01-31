import os
import subprocess
import polib
import config
import shutil

# 待检测字符数组
characters_to_check = [""] # 添加需要检测的字符

def convert_mo_to_po(mo_file, po_file):
    # 读取.mo文件
    mo_data = polib.mofile(mo_file)
    # 保存为.po文件
    mo_data.save_as_pofile(po_file)

def check_po_file_for_characters(po_file, characters):
    po = polib.pofile(po_file)
    found = False
    for entry in po:
        for char in characters:
            if char in entry.msgstr:
                print(f"文件: {po_file}, 位置: {entry.linenum}, 匹配字符: {char}")
                found = True
    return found

def process_files(folder, output_folder):
    for file in os.listdir(folder):
        if file.endswith('.mo'):
            mo_file = os.path.join(folder, file)
            po_file = os.path.join(folder, file.replace('.mo', '.po'))
            convert_mo_to_po(mo_file, po_file)

            if not os.path.exists(po_file):
                continue

            if check_po_file_for_characters(po_file, characters_to_check):
                output_po_file = os.path.join(output_folder, "matched_" + file.replace('.mo', '.po'))
                shutil.copy(po_file, output_po_file)

                # 如果找到字符，则将对应的ru文件夹中的.mo文件转换为.po文件
                ru_mo_file = os.path.join(config.FOLDER_RUSSIA, file)
                output_po_file = os.path.join(output_folder, file.replace('.mo', '.po'))
                convert_mo_to_po(ru_mo_file, output_po_file)
            os.remove(po_file)

def main():
    os.makedirs(config.OUTPUT_CHECK_FOLDER, exist_ok=True)
    process_files(config.PREVIOUS_TRANSLATIONS_FOLDER, config.OUTPUT_CHECK_FOLDER)

if __name__ == "__main__":
    main()
