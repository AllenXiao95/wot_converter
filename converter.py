import os
import re
import subprocess
import requests
import polib
import deepl
import config
import shutil
import time

# 全局变量用于统计API请求数
api_request_count = 0

def convert_mo_to_po(mo_file, po_file):
    # 读取.mo文件
    mo_data = polib.mofile(mo_file)
    # 保存为.po文件
    mo_data.save_as_pofile(po_file)

def merge_po_files(trans_po, src_po, merged_po):
    # 读取第一个.po文件
    po1 = polib.pofile(trans_po)
    # 读取第二个.po文件
    po2 = polib.pofile(src_po)

    # 合并文件
    for entry in po2:
        if not po1.find(entry.msgid):
            po1.append(entry)

    # 保存合并后的.po文件
    po1.save(merged_po)

def convert_po_to_mo(po_file, mo_file):
    # 读取.po文件
    po_data = polib.pofile(po_file)
    # 保存为.mo文件
    po_data.save_as_mofile(mo_file)

def extract_and_replace_expressions(text):
    expression_pattern = re.compile(r'%\(\w+\)')
    expressions = expression_pattern.findall(text)
    if not expressions:
        return text, None  # 如果没有表达式，返回原始文本和None

    placeholders = []
    for i, expr in enumerate(expressions):
        placeholder = f"{{PLACEHOLDER_{i}}}"
        text = text.replace(expr, placeholder)
        placeholders.append((placeholder, expr))
    return text, placeholders

def restore_expressions(translated_text, placeholders):
    if placeholders is None:
        return translated_text  # 如果没有占位符，直接返回翻译文本

    for placeholder, expr in placeholders:
        translated_text = translated_text.replace(placeholder, expr)
    return translated_text

def merge_previous_mo_translation(merged_po_file):
    previous_mo_file = os.path.join(config.PREVIOUS_TRANSLATIONS_FOLDER, os.path.basename(merged_po_file).replace('.po', '.mo'))
    if os.path.exists(previous_mo_file):
        previous_po_file = previous_mo_file.replace('.mo', '_previous.po')
        convert_mo_to_po(previous_mo_file, previous_po_file)
        merge_po_files(previous_po_file, merged_po_file, merged_po_file)
        os.remove(previous_po_file)  # 清理转换后的临时.po文件

def contains_russian(text):
    if text == '?empty?':
        return False

    russian_chars = set("абвгдежзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")
    return any(char in russian_chars for char in text)

def contains_chinese_or_special(text):
    if 'Obj. ' in text:
        return text

    for character in text:
        if '\u4e00' <= character <= '\u9fff' or \
           '\u3400' <= character <= '\u4dbf':
            return True
    return False

def init_translators():
    deepl_translator = deepl.Translator(config.DEEPL_API_KEY)
    return deepl_translator

def split_text_smartly(text, max_length):
    """智能分割文本，优先考虑句子的完整性和最大长度限制"""
    sentences = re.split(r'([.!?。！？])', text)
    segments = []
    current_segment = ''

    for i in range(0, len(sentences), 2):
        sentence = sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else '')
        if len(current_segment) + len(sentence) > max_length:
            # 如果当前段落加上新句子会超过最大长度，先保存当前段落
            segments.append(current_segment)
            current_segment = sentence
        else:
            current_segment += sentence

    # 添加最后一段
    if current_segment:
        segments.append(current_segment)

    return segments

def translate_text(text, deepl_translator, max_retries=5):
    global api_request_count
    use_deepl = True
    translated_parts = []
    text_parts = split_text_smartly(text, max_length=999)

    for part in text_parts:
        for attempt in range(max_retries):
            try:
                if use_deepl:
                    api_request_count += 1
                    result = deepl_translator.translate_text(part, target_lang="ZH")
                    translated_parts.append(result.text)
                    break
                else:
                    api_request_count += 1
                    response = requests.post("https://translation.googleapis.com/language/translate/v2", params={
                        "key": config.GOOGLE_API_KEY,
                        "q": part,
                        "target": "zh"
                    })
                    response.raise_for_status()
                    translated_parts.append(response.json()['data']['translations'][0]['translatedText'])
                    break
            except Exception as e:
                print(f"Error during translation of part '{part}': {e}")
                if attempt == max_retries - 1:
                    translated_parts.append(f"[Error translating this part: {part}]")

                if use_deepl:
                    use_deepl = False

    return ''.join(translated_parts)


def process_file(file, folder_russia, output_folder, translators):
    mo_file_russia = os.path.join(folder_russia, file)
    po_file_russia = os.path.join(output_folder, file.replace('.mo', '.po'))
    previous_mo_file = os.path.join(config.PREVIOUS_TRANSLATIONS_FOLDER, file)
    previous_po_file = previous_mo_file.replace('.mo', '_previous.po')
    merged_po_file = os.path.join(output_folder, 'merged_' + file.replace('.mo', '.po'))
    output_mo_file = os.path.join(output_folder, file)

    if os.path.exists(output_mo_file):
        return

    convert_mo_to_po(mo_file_russia, po_file_russia)

    if not os.path.exists(po_file_russia):
        shutil.copy(mo_file_russia, output_mo_file)
        return

    if os.path.exists(previous_mo_file):
        # 将previous中的.mo文件转换为.po文件
        convert_mo_to_po(previous_mo_file, previous_po_file)
        # 合并previous和russia中的.po文件
        merge_po_files(previous_po_file, po_file_russia, merged_po_file)
        cleanup_files([previous_po_file])  # 清理临时文件
    else:
        # 如果previous中没有对应文件，只复制russia的.po文件作为合并文件
        shutil.copy(po_file_russia, merged_po_file)

    # 对合并后的.po文件进行翻译
    translate_po_file(merged_po_file, translators)
    convert_po_to_mo(merged_po_file, output_mo_file)
    cleanup_files([po_file_russia, merged_po_file])

def translate_po_file(po_file, translators):
    po = polib.pofile(po_file)
    def process_translation(text):
        if contains_chinese_or_special(text):
            return text

        if contains_russian(text):
            processed_text, placeholders = extract_and_replace_expressions(text)
            translated_text = translate_text(processed_text, translators)
            return restore_expressions(translated_text, placeholders)

        return text

    for entry in po:
        if entry.msgstr_plural:
            for idx in entry.msgstr_plural:
                entry.msgstr_plural[idx] = process_translation(entry.msgstr_plural[idx])
        else:
            entry.msgstr = process_translation(entry.msgstr)

    po.save(po_file)

def cleanup_files(files):
    for file in files:
        if os.path.exists(file):
            os.remove(file)

def main():
    start_time = time.time()  # 开始计时
    os.makedirs(config.OUTPUT_FOLDER, exist_ok=True)
    translators = init_translators()
    for file in os.listdir(config.FOLDER_RUSSIA):
        if file.endswith('.mo'):
            process_file(file, config.FOLDER_RUSSIA, config.OUTPUT_FOLDER, translators)
    end_time = time.time()  # 结束计时
    total_time = end_time - start_time
    print(f"Total processing time: {total_time} seconds.")
    print(f"Total API requests made: {api_request_count}")

if __name__ == "__main__":
    main()
