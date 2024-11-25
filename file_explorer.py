import os
import curses
import curses.ascii
import json
import math
import re

SEARCH_HIGHLIGHT = 6
KEY_HIGHLIGHT = 3


def list_files(stdscr, current_path, selected_file):
    stdscr.clear()
    rows, cols = stdscr.getmaxyx()
    stdscr.addstr(0, 0, f"Current directory: {current_path}\n"[:cols], curses.A_BOLD)
    paths = os.listdir(current_path)
    paths.sort()

    # 分离文件和文件夹
    folders = [f + '/' for f in paths if os.path.isdir(os.path.join(current_path, f))]
    files = [f for f in paths if os.path.isfile(os.path.join(current_path, f))]
    paths = ['../'] + folders + files

    # 显示所有路径
    row_per_page = rows - 3
    page = selected_file // row_per_page
    paths_in_page = paths[page * row_per_page : min((page + 1) * row_per_page, len(paths))]
    for idx, path in enumerate(paths_in_page):
        path = path[:cols]
        mode_select = curses.A_REVERSE if idx == selected_file % row_per_page else curses.A_NORMAL
        mode_folder = curses.A_UNDERLINE if os.path.isdir(os.path.join(current_path, path)) else curses.A_NORMAL
        stdscr.addstr(idx + 2, 0, path, mode_select)

    stdscr.addstr(1, 0, f"Page: {page + 1} / {math.ceil(len(paths) / row_per_page)}, {selected_file}", curses.A_BOLD)
    stdscr.addstr(rows - 1, 0, "[...] Press ESC to quit", curses.A_BOLD)
    stdscr.refresh()
    return paths


def split_str(s, n):
    result = []
    length = 0
    n = int(n)
    current_str = ''
    for char in s:
        char_length = 1 if ord(char) < 128 else 2  # 英文字符长度为1，中文字符长度为2
        if length + char_length <= n:
            current_str += char
            length += char_length
        else:
            result.append(current_str)
            current_str = char
            length = char_length
    result.append(current_str)
    return result


def add_colored_json(stdscr, row, col, str, search=None):
    def split_sub_str(pattern, item, color):
        (s, c) = item
        result_list = []              # 初始化结果列表
        last_index = 0           # 记录上一个匹配的结束位置
        # 查找所有匹配的子串
        for match in re.finditer(pattern, s):
            # 添加不满足条件的子串
            if last_index < match.start():
                non_match_part = s[last_index:match.start()]
                result_list.append((non_match_part, c))
            # 添加满足条件的子串
            match_part = match.group()
            result_list.append((match_part, color))
            last_index = match.end()
        # 添加最后一个不满足条件的子串（如果有）
        if last_index < len(s):
            non_match_part = s[last_index:]
            result_list.append((non_match_part, c))
        return result_list
    
    item_list = split_sub_str(r'\"[^\\]*?\":', (str, 1), KEY_HIGHLIGHT)
    if search:
        item_list_new = []
        for i, item in enumerate(item_list):
            item_list_new += split_sub_str(re.escape(search), item, SEARCH_HIGHLIGHT)
        item_list = item_list_new

    for i, item in enumerate(item_list):
        if i == 0:
            stdscr.addstr(row, col, item[0], curses.color_pair(item[1]))
        else:
            stdscr.addstr(item[0], curses.color_pair(item[1]))


def search_in_list(string_list, target_string):
    if not target_string:
        return 0
    # 遍历列表，找到目标字符串第一次出现的位置
    for index, string in enumerate(string_list, start=1):
        if target_string in string:
            return index  # 返回字符串所在的位置（第几个字符串）
    # 如果目标字符串未出现在任何字符串中
    return -1


def load_json_data(json_lines, selected_data, cols):
    try:
        json_content = json.loads(json_lines[selected_data])
        json_str = json.dumps(json_content, ensure_ascii=False, indent=2)
        json_str = json_str.replace("\\n", '\n')
    except json.JSONDecodeError:
        json_str = "Error: Invalid JSON content."
    except IndexError:
        json_str = "Error: Empty file."

    json_str_lines = json_str.split('\n')
    lines = []
    for line in json_str_lines:
        lines.extend(split_str(line, cols))
    return lines


def search_next(json_lines, selected_data, start_line, search_str, rows, cols):
    while selected_data < len(json_lines):
        lines = load_json_data(json_lines, selected_data, cols)
        line_diff = search_in_list(lines[start_line+1:], search_str)
        if line_diff != -1:
            next_line = start_line + line_diff
            return selected_data, next_line

        selected_data += 1
        start_line = 0
    return 0, 0


def read_jsonl(path):
    with open(path, 'r', encoding='utf-8') as f:
        json_lines = f.readlines()
    return json_lines


def read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        if isinstance(json_data, list):
            json_lines = [json.dumps(d) for d in json_data]
        else:
            json_lines = [json.dumps(json_data)]
        return json_lines
    except Exception as e:
        return [str(e)]
            


def display_data(stdscr, path):
    if path.endswith('.jsonl'):
        json_lines = read_jsonl(path)
    elif path.endswith('.json'):
        json_lines = read_json(path)
    else:
        return -1
    selected_data = 0
    selected_mode = 0
    start_line = 0
    search_str = ''
    jump_line_str = ''  # 用于记录输入行号
    key = ''
    mode_list = ["SEARCH", "JUMP"]
    mode = mode_list[selected_mode]

    while True:
        rows, cols = stdscr.getmaxyx()
        stdscr.clear()

        # 显示 json 内容
        try:
            lines = load_json_data(json_lines, selected_data, cols)
            for r, split_line in enumerate(lines[start_line:start_line+rows-5], start=2):
                add_colored_json(stdscr, r, 0, split_line, search=search_str)
        except Exception as e:
            stdscr.addstr(2, 0, str(e))

        # 显示文件名
        stdscr.addstr(0, 0, f"JSONL file: {path[:cols-12]}", curses.A_BOLD)
        # 显示数据编号
        stdscr.addstr(1, 0, f"Current line: {selected_data + 1} / {len(json_lines)}", curses.A_BOLD)
        # 显示搜索输入
        stdscr.addstr(rows - 3, 0, f"[...] Type WORDs to search, ENTER to next: {search_str}"[:cols-1], (curses.A_BOLD | curses.A_REVERSE) if mode == "SEARCH" else curses.A_BOLD)
        # 显示行号输入
        stdscr.addstr(rows - 2, 0, f"[...] Type NUMBERs to choose a line, ENTER to jump: {jump_line_str}"[:cols-1], (curses.A_BOLD | curses.A_REVERSE) if mode == "JUMP" else curses.A_BOLD)
        # 显示提示
        stdscr.addstr(rows - 1, 0, f"[...] Press UP/DOWN to scroll, LEFT/RIGHT to switch line, TAB to switch mode, ESC to quit."[:cols-1], curses.A_BOLD)

        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_RIGHT or key == 454:
            selected_data = min(selected_data + 1, max(len(json_lines) - 1, 0))
            start_line = 0
        elif key == curses.KEY_LEFT or key == 452:
            selected_data = max(selected_data - 1, 0)
            start_line = 0
        elif key == curses.KEY_DOWN or key == 456:
            start_line = (start_line + 1) % max(len(lines) - (rows - 6), 1)
        elif key == curses.KEY_UP or key == 450:
            start_line = (start_line - 1) % max(len(lines) - (rows - 6), 1)
        elif key == 27:  # ESC
            stdscr.clear()
            break
        elif key == curses.KEY_BTAB or key == 9:
            selected_mode = (selected_mode + 1) % len(mode_list)
            mode = mode_list[selected_mode]

        if mode == "SEARCH":
            if 32 <= key <= 126:  # 所有ascii可显示字符
                search_str += chr(key)  # 添加输入
            elif key == curses.KEY_BACKSPACE or key == 8:  # 处理删除
                search_str = search_str[:-1]  # 删除最后一个字符
            elif key == ord('\n'):  # 回车
                try:
                    stdscr.addstr(rows - 1, cols - 8, f"LOADING", curses.A_BOLD)
                    stdscr.refresh()
                    selected_data, start_line = search_next(json_lines, selected_data, start_line, search_str, rows, cols)
                except:
                    pass
        elif mode == "JUMP":
            if 48 <= key <= 57:  # 数字键（0-9）
                jump_line_str += chr(key)  # 添加输入
            elif key == curses.KEY_BACKSPACE or key == 8:  # 处理删除
                jump_line_str = jump_line_str[:-1]  # 删除最后一个字符
            elif key == ord('\n'):  # 回车
                try:
                    target_line = int(jump_line_str) - 1  # 转换为索引（从0开始）
                    if 0 <= target_line < len(json_lines):
                        selected_data = target_line
                        start_line = 0
                    jump_line_str = ''  # 清空输入
                except ValueError:
                    pass  # 无效输入时不做任何操作


def file_explorer(stdscr):
    # 初始化颜色
    curses.start_color()
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)  # 白色
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)    # 红色
    curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)  # 绿色
    curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)   # 蓝色
    curses.init_pair(5, curses.COLOR_YELLOW, curses.COLOR_BLACK) # 黄色
    curses.init_pair(6, curses.COLOR_BLACK, curses.COLOR_YELLOW) # 警告

    curses.curs_set(0)
    current_path = os.getcwd()
    stdscr.encoding = 'utf-8'
    selected_file = 0
    files = list_files(stdscr, current_path, selected_file)

    while True:
        key = stdscr.getch()
        if (key == curses.KEY_UP or key == 450):
            selected_file = (selected_file - 1) % len(files)
        elif (key == curses.KEY_DOWN or key == 456):
            selected_file = (selected_file + 1) % len(files)
        elif key == ord('\n'):
            new_path = os.path.normpath(os.path.join(current_path, files[selected_file]))
            if os.path.isdir(new_path):
                current_path = new_path
            elif os.path.isfile(new_path):
                if new_path.endswith('.jsonl') or new_path.endswith('.json'):
                    display_data(stdscr, new_path)
                    files = list_files(stdscr, current_path, selected_file)
            # selected_file = 0
        elif key == 27:
            break

        files = list_files(stdscr, current_path, selected_file)
        stdscr.refresh()


if __name__ == "__main__":
    curses.wrapper(file_explorer)
