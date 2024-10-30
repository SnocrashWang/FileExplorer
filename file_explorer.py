import os
import curses
import curses.ascii
import json
import math


def list_files(stdscr, current_path, selected):
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
    page = selected // row_per_page
    paths_in_page = paths[page * row_per_page : min((page + 1) * row_per_page, len(paths))]
    for idx, path in enumerate(paths_in_page):
        path = path[:cols]
        mode_select = curses.A_REVERSE if idx == selected % row_per_page else curses.A_NORMAL
        mode_folder = curses.A_UNDERLINE if os.path.isdir(os.path.join(current_path, path)) else curses.A_NORMAL
        stdscr.addstr(idx + 2, 0, path, mode_select)

    stdscr.addstr(1, 0, f"Page: {page + 1} / {math.ceil(len(paths) / row_per_page)}, {selected}", curses.A_BOLD)
    stdscr.addstr(rows - 1, 0, "[...] Press ESC to quit")
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


def display_jsonl(stdscr, jsonl_path):
    stdscr.clear()
    stdscr.addstr(0, 0, f"Viewing JSONL file: {jsonl_path}")

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        json_lines = f.readlines()

    selected = 0
    start_line = 0
    jump_line_str = ''  # 用于记录输入行号
    key = ''

    while True:
        stdscr.clear()
        stdscr.addstr(0, 0, f"JSONL file: {jsonl_path}")
        stdscr.addstr(1, 0, f"Current line: {selected + 1} / {len(json_lines)}")

        try:
            json_content = json.loads(json_lines[selected])
            json_str = json.dumps(json_content, ensure_ascii=False, indent=2)
            json_str = json_str.replace("\\n", '\n')
        except json.JSONDecodeError:
            json_str = "Error: Invalid JSON content."
        except IndexError:
            json_str = "Error: Empty file."

        rows, cols = stdscr.getmaxyx()
        json_str_lines = json_str.split('\n')
        row_idx = 2
        try:
            for i, line in enumerate(json_str_lines[start_line:]):
                lines = split_str(line, cols)
                for split_line in lines:
                    if row_idx < rows - 1:
                        stdscr.addstr(row_idx, 0, split_line)
                        row_idx += 1
        except:
            stdscr.addstr(2, 0, "Error: Invalid JSON content.")

        # 显示提示
        stdscr.addstr(rows - 1, 0, "[...] Press UP/DOWN to scroll, LEFT/RIGHT to switch, ESC to quit.")
        # 显示行号输入
        stdscr.addstr(rows - 2, 0, f"[...] Press NUMBERs to choose a line, ENTER to jump: {jump_line_str}")

        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_RIGHT or key == 454:
            selected = min(selected + 1, max(len(json_lines) - 1, 0))
            start_line = 0
        elif key == curses.KEY_LEFT or key == 452:
            selected = max(selected - 1, 0)
            start_line = 0
        elif key == curses.KEY_DOWN or key == 456:
            start_line = min(start_line + 1, len(json_str_lines) - 1)
        elif key == curses.KEY_UP or key == 450:
            start_line = max(start_line - 1, 0)
        elif key == 27:  # ESC
            stdscr.clear()
            break
        elif 48 <= key <= 57:  # 数字键（0-9）
            jump_line_str += chr(key)  # 添加输入
        elif key == curses.KEY_BACKSPACE or key == 8:  # 处理删除
            jump_line_str = jump_line_str[:-1]  # 删除最后一个字符
        elif key == ord('\n'):  # 回车
            try:
                target_line = int(jump_line_str) - 1  # 转换为索引（从0开始）
                if 0 <= target_line < len(json_lines):
                    selected = target_line
                    start_line = 0
                jump_line_str = ''  # 清空输入
            except ValueError:
                pass  # 无效输入时不做任何操作



def file_explorer(stdscr):
    curses.curs_set(0)
    current_path = os.getcwd()
    stdscr.encoding = 'utf-8'
    selected = 0
    files = list_files(stdscr, current_path, selected)

    while True:
        key = stdscr.getch()
        if (key == curses.KEY_UP or key == 450):
            selected = (selected - 1) % len(files)
        elif (key == curses.KEY_DOWN or key == 456):
            selected = (selected + 1) % len(files)
        elif key == ord('\n'):
            new_path = os.path.normpath(os.path.join(current_path, files[selected]))
            if os.path.isdir(new_path):
                current_path = new_path
            elif os.path.isfile(new_path):
                if new_path.endswith('.jsonl'):
                    display_jsonl(stdscr, new_path)
                    files = list_files(stdscr, current_path, selected)
            selected = 0
        elif key == 27:
            break

        files = list_files(stdscr, current_path, selected)
        stdscr.refresh()


if __name__ == "__main__":
    curses.wrapper(file_explorer)
