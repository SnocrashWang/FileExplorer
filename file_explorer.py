import os
import curses
import curses.ascii
import json
import math
import re
import traceback
from typing import Dict, Tuple, List, Any

SEARCH_HIGHLIGHT = 6
KEY_HIGHLIGHT = 3

class TypeDisplayJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        # 对于类型对象，返回一个特殊的字典结构
        if isinstance(obj, type):
            return {"__class__": obj.__name__}
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        return super().default(obj)
    
    def encode(self, obj):
        # 先调用父类的 encode 生成标准 JSON
        json_str = super().encode(obj)
        
        # 使用正则表达式替换特殊标记
        # 将 {"__class__": "str"} 替换为 str
        json_str = re.sub(r'\{[\s\n]*"__class__"\s*:\s*"(\w+)"[\s\n]*\}', r'\1', json_str)
        return json_str

class JSONDataCache:
    """JSON数据缓存，避免重复序列化"""
    
    def __init__(self, max_size=100):
        self.max_size = max_size
        self.full_cache: Dict[int, List[str]] = {}  # {data_index: lines}
        self.skeleton_cache: Dict[int, List[str]] = {}  # {data_index: lines}
        self.access_order: List[int] = []  # 访问顺序，用于LRU
    
    def get_lines(self, data_index: int, cols: int, json_line: str) -> Tuple[List[str], List[str]]:
        """获取缓存的行，如果没有则计算并缓存"""
        cache_key = data_index
        
        # 更新访问顺序
        if cache_key in self.access_order:
            self.access_order.remove(cache_key)
        self.access_order.append(cache_key)
        
        # 如果缓存超过最大大小，移除最久未使用的
        while len(self.access_order) > self.max_size:
            old_key = self.access_order.pop(0)
            self.full_cache.pop(old_key, None)
            self.skeleton_cache.pop(old_key, None)
        
        # 如果缓存中存在，直接返回
        if cache_key in self.full_cache and cache_key in self.skeleton_cache:
            return self.full_cache[cache_key], self.skeleton_cache[cache_key]
        
        # 否则计算并缓存
        full_lines, skeleton_lines = self._compute_lines(json_line, cols)
        
        self.full_cache[cache_key] = full_lines
        self.skeleton_cache[cache_key] = skeleton_lines
        
        return full_lines, skeleton_lines
    
    def _compute_lines(self, json_line: str, cols: int) -> Tuple[List[str], List[str]]:
        """计算JSON数据的行"""
        try:
            full_json_data = json.loads(json_line)
            full_json_str = json.dumps(full_json_data, ensure_ascii=False, indent=2)
            full_json_str = re.sub(r'(?<!\\)\\n', '\n', full_json_str)

            def replace_non_dict_with_none(data):
                """
                递归地将字典中所有非字典的值替换为None
                """
                if isinstance(data, dict):
                    for key in data:
                        if isinstance(data[key], dict) or isinstance(data[key], list):
                            replace_non_dict_with_none(data[key])
                        else:
                            data[key] = type(data[key])
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) or isinstance(item, list):
                            replace_non_dict_with_none(item)
                        else:
                            item = type(item)
                return data

            skeleton_json_data = replace_non_dict_with_none(full_json_data.copy())
            skeleton_json_str = json.dumps(skeleton_json_data, cls=TypeDisplayJSONEncoder, ensure_ascii=False, indent=2)
            skeleton_json_str = re.sub(r'(?<!\\)\\n', '\n', skeleton_json_str)
        except json.JSONDecodeError:
            full_json_str = "Error: Invalid JSON data."
            skeleton_json_str = "Error: Invalid JSON data."
        except Exception as e:
            full_json_str = f"Error: {str(e)}"
            skeleton_json_str = f"Error: {str(e)}"

        full_lines, skeleton_lines = [], []
        for line in full_json_str.split('\n'):
            full_lines.extend(self.split_str(line, cols))
        for line in skeleton_json_str.split('\n'):
            skeleton_lines.extend(self.split_str(line, cols))
        
        return full_lines, skeleton_lines
    
    @staticmethod
    def split_str(s, n):
        """分割字符串，考虑中英文字符宽度"""
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
    
    def clear(self):
        """清空缓存"""
        self.full_cache.clear()
        self.skeleton_cache.clear()
        self.access_order.clear()
    
    def get_cache_info(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "cache_size": len(self.full_cache),
            "max_size": self.max_size,
            "memory_usage_estimate": sum(len(''.join(lines)) for lines in self.full_cache.values()) // 1024  # KB
        }


class FileCache:
    def __init__(self):
        self.cache = {}  # {path: (timestamp, [file_list])}
    
    def get_files(self, path):
        current_time = os.path.getmtime(path)
        
        if path in self.cache:
            cached_time, files = self.cache[path]
            if cached_time == current_time:
                return files
        
        # 重新读取文件列表
        try:
            paths = os.listdir(path)
            paths.sort()
            
            # 分离文件和文件夹
            folders = [f + '/' for f in paths if os.path.isdir(os.path.join(path, f))]
            files = [f for f in paths if os.path.isfile(os.path.join(path, f))]
            result = ['../'] + folders + files
            
            # 更新缓存
            self.cache[path] = (current_time, result)
            return result
        except (OSError, PermissionError):
            return ['../']
    
    def clear(self):
        self.cache.clear()


def list_files(stdscr, current_path, selected_file, search_str="", file_cache=None, original_files=None, key=""):
    stdscr.clear()
    rows, cols = stdscr.getmaxyx()
    
    # 使用缓存获取文件列表
    if original_files is None:
        original_files = file_cache.get_files(current_path) if file_cache else []
    
    paths = original_files.copy()
    
    # 如果有搜索词，筛选路径
    if search_str:
        filtered_paths = []
        for path in paths:
            if search_str.lower() in path.lower():
                filtered_paths.append(path)
        paths = filtered_paths
        # 如果筛选后没有文件，保持选中位置为0
        if not paths:
            paths = []
            selected_file = 0

    # 显示所有路径
    row_per_page = rows - 3
    page = selected_file // row_per_page if paths else 0
    paths_in_page = paths[page * row_per_page : min((page + 1) * row_per_page, len(paths))]
    
    for idx, path in enumerate(paths_in_page):
        display_path = path[:cols]
        mode_select = curses.A_REVERSE if idx == selected_file % row_per_page else curses.A_NORMAL
        mode_folder = curses.A_UNDERLINE if path.endswith('/') else curses.A_NORMAL
        
        # 如果有搜索词，高亮匹配的部分
        if search_str and search_str.lower() in path.lower():
            # 找到所有匹配的位置
            start_positions = []
            lower_path = path.lower()
            lower_search = search_str.lower()
            pos = lower_path.find(lower_search)
            while pos != -1:
                start_positions.append(pos)
                pos = lower_path.find(lower_search, pos + 1)
            
            # 分段显示并高亮
            current_col = 0
            last_pos = 0
            for start_pos in start_positions:
                end_pos = start_pos + len(search_str)
                # 显示非高亮部分
                if last_pos < start_pos:
                    normal_part = path[last_pos:start_pos]
                    if current_col + len(normal_part) < cols:
                        stdscr.addstr(idx + 2, current_col, normal_part, mode_select)
                        current_col += len(normal_part)
                
                # 显示高亮部分
                highlight_part = path[start_pos:end_pos]
                if current_col + len(highlight_part) < cols:
                    stdscr.addstr(idx + 2, current_col, highlight_part, curses.color_pair(SEARCH_HIGHLIGHT))
                    current_col += len(highlight_part)
                
                last_pos = end_pos
            
            # 显示剩余部分
            if last_pos < len(path):
                remaining_part = path[last_pos:]
                if current_col + len(remaining_part) < cols:
                    stdscr.addstr(idx + 2, current_col, remaining_part, mode_select)
        else:
            # 没有搜索词时的正常显示
            stdscr.addstr(idx + 2, 0, display_path, mode_select)

    # 显示页面信息和提示
    stdscr.addstr(0, 0, f"Current directory: {current_path}\n"[:cols], curses.A_BOLD)
    if search_str:
        stdscr.addstr(1, 0, f"Page: {page + 1} / {math.ceil(len(paths) / row_per_page) if paths else 1}, Pos: {selected_file + 1}, Found {len(paths)} / {len(original_files)} items"[:cols], curses.A_BOLD)
        stdscr.addstr(rows - 1, 0, f"[...] Type to search: {search_str}"[:cols-1], curses.A_BOLD)
    else:
        stdscr.addstr(1, 0, f"Page: {page + 1} / {math.ceil(len(paths) / row_per_page) if paths else 1}, Pos: {selected_file + 1}"[:cols], curses.A_BOLD)
        stdscr.addstr(rows - 1, 0, "[...] Supported file extensions: jsonl, json, txt. Type to search. Press ESC to quit."[:cols-1], curses.A_BOLD)
    # 显示key值
    stdscr.addstr(0, cols - 10, f"{key}", curses.A_BOLD)
    
    stdscr.refresh()
    return paths, original_files  # 返回筛选后的文件和原始文件列表


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


def load_json_data(json_lines, selected_data, cols, json_cache=None):
    """使用缓存加载JSON数据"""
    if json_cache is None:
        # 如果没有缓存，回退到原始方法
        return _load_json_data_original(json_lines, selected_data, cols)
    
    try:
        json_line = json_lines[selected_data]
        full_lines, skeleton_lines = json_cache.get_lines(selected_data, cols, json_line)
        return full_lines, skeleton_lines
    except IndexError:
        return ["Error: Empty file."], ["Error: Empty file."]
    except Exception as e:
        return [f"Error: {str(e)}"], [f"Error: {str(e)}"]


def _load_json_data_original(json_lines, selected_data, cols):
    """原始的数据加载方法（备用）"""
    try:
        full_json_data = json.loads(json_lines[selected_data])
        full_json_str = json.dumps(full_json_data, ensure_ascii=False, indent=2)
        full_json_str = re.sub(r'(?<!\\)\\n', '\n', full_json_str)

        def replace_non_dict_with_none(data):
            """
            递归地将字典中所有非字典的值替换为None
            """
            if isinstance(data, dict):
                for key in data:
                    if isinstance(data[key], dict) or isinstance(data[key], list):
                        replace_non_dict_with_none(data[key])
                    else:
                        data[key] = type(data[key])
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) or isinstance(item, list):
                        replace_non_dict_with_none(item)
                    else:
                        item = type(item)
            return data

        skeleton_json_data = replace_non_dict_with_none(full_json_data.copy())
        skeleton_json_str = json.dumps(skeleton_json_data, cls=TypeDisplayJSONEncoder, ensure_ascii=False, indent=2)
        skeleton_json_str = re.sub(r'(?<!\\)\\n', '\n', skeleton_json_str)
    except json.JSONDecodeError:
        full_json_str = "Error: Invalid JSON data."
        skeleton_json_str = "Error: Invalid JSON data."
    except IndexError:
        full_json_str = "Error: Empty file."
        skeleton_json_str = "Error: Empty file."

    full_lines, skeleton_lines = [], []
    for line in full_json_str.split('\n'):
        full_lines.extend(split_str(line, cols))
    for line in skeleton_json_str.split('\n'):
        skeleton_lines.extend(split_str(line, cols))
    return full_lines, skeleton_lines


def search_next(json_lines, selected_data, lines, start_line, search_str):
    while selected_data < len(json_lines):
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


def read_txt(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            json_data = [l.split('\t')[1] for l in f.readlines()]
        return json_data
    except Exception as e:
        return [str(e)]


def display_data(stdscr, path):
    # 创建JSON数据缓存
    json_cache = JSONDataCache(max_size=50)  # 缓存50条数据
    
    while True:
        if path.endswith('.jsonl'):
            json_lines = read_jsonl(path)
        elif path.endswith('.json'):
            json_lines = read_json(path)
        elif path.endswith('.txt'):
            json_lines = read_txt(path)
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
        show_values = True

        while True:
            rows, cols = stdscr.getmaxyx()
            stdscr.clear()

            # 显示 json 内容
            try:
                full_lines, skeleton_lines = load_json_data(json_lines, selected_data, cols, json_cache)
                lines = full_lines if show_values else skeleton_lines
            except:
                lines = []
                for line in traceback.format_exc().split('\n'):
                    lines.extend(split_str(line, cols))
            finally:
                for r, split_line in enumerate(lines[start_line:start_line+rows-5], start=2):
                    add_colored_json(stdscr, r, 0, split_line, search=search_str)

            # 显示文件名
            stdscr.addstr(0, 0, f"JSONL file: {path[:cols-12]}", curses.A_BOLD)
            # 显示数据编号
            stdscr.addstr(1, 0, f"Current line: {selected_data + 1} / {len(json_lines)}", curses.A_BOLD)
            # 显示key值
            stdscr.addstr(0, cols - 10, f"{key}", curses.A_BOLD)
            # 显示搜索输入
            stdscr.addstr(rows - 3, 0, f"[...] Type WORDs to search, ENTER to next: {search_str}"[:cols-1], (curses.A_BOLD | curses.A_REVERSE) if mode == "SEARCH" else curses.A_BOLD)
            # 显示行号输入
            stdscr.addstr(rows - 2, 0, f"[...] Type NUMBERs to choose a line, ENTER to jump: {jump_line_str}"[:cols-1], (curses.A_BOLD | curses.A_REVERSE) if mode == "JUMP" else curses.A_BOLD)
            # 显示提示
            stdscr.addstr(rows - 1, 0, f"[...] Press UP/DOWN to scroll, LEFT/RIGHT to switch data, TAB to switch mode, INSERT to conceal values, Ctrl+A to refresh, Ctrl+Z to clear cache, ESC to quit."[:cols-1], curses.A_BOLD)

            stdscr.refresh()

            key = stdscr.getch()
            if key == curses.KEY_RIGHT or key == 454:
                selected_data = min(selected_data + 1, max(len(json_lines) - 1, 0))
                start_line = 0
            elif key == curses.KEY_LEFT or key == 452:
                selected_data = max(selected_data - 1, 0)
                start_line = 0
            elif key == curses.KEY_DOWN or key == 456:
                if start_line >= max(len(lines) - (rows - 6), 1):
                    start_line = len(lines) - (rows - 6) - 1
                else:
                    start_line = (start_line + 1) % max(len(lines) - (rows - 6), 1)
            elif key == curses.KEY_UP or key == 450:
                if start_line >= max(len(lines) - (rows - 6), 1):
                    start_line = len(lines) - (rows - 6) - 1
                else:
                    start_line = (start_line - 1) % max(len(lines) - (rows - 6), 1)
            elif key == 27:  # ESC
                stdscr.clear()
                return 0
            elif key == (ord('a') & 0x1f) or key == 1:  # Ctrl+A
                break
            elif key == (ord('z') & 0x1f) or key == 26:  # Ctrl+Z - 清除缓存
                json_cache.clear()
                # 重新加载当前数据以刷新显示
                full_lines, skeleton_lines = load_json_data(json_lines, selected_data, cols, json_cache)
                if show_values:
                    lines = full_lines
                else:
                    lines = skeleton_lines
            elif key == curses.KEY_BTAB or key == 9:
                selected_mode = (selected_mode + 1) % len(mode_list)
                mode = mode_list[selected_mode]
            elif key == curses.KEY_IC or key == 506:
                show_values = not show_values
                start_line = 0  # 重置到顶部以便立即看到变化

            if mode == "SEARCH":
                if 32 <= key <= 126:  # 所有ascii可显示字符
                    search_str += chr(key)  # 添加输入
                elif key == curses.KEY_BACKSPACE or key == 8:  # 处理删除
                    search_str = search_str[:-1]  # 删除最后一个字符
                elif key == ord('\n'):  # 回车
                    try:
                        stdscr.addstr(rows - 1, cols - 8, f"LOADING", curses.A_BOLD)
                        stdscr.refresh()
                        selected_data, start_line = search_next(json_lines, selected_data, lines, start_line, search_str)
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
    search_str = ""  # 搜索字符串
    file_cache = FileCache()  # 创建文件缓存实例
    
    # 新增：保存每个目录的原始文件列表和选中位置
    path_history = {}  # {path: {"original_files": [], "selected_index": 0}}
    
    files, original_files = list_files(stdscr, current_path, selected_file, search_str, file_cache)
    path_history[current_path] = {"original_files": original_files, "selected_index": selected_file}

    while True:
        key = stdscr.getch()
        rows, cols = stdscr.getmaxyx()

        # 处理搜索输入
        if 32 <= key <= 126:  # 所有ascii可显示字符
            search_str += chr(key)  # 添加输入
            selected_file = 0  # 重置选中位置到第一个
        elif key == curses.KEY_BACKSPACE or key == 8:  # 处理删除
            if search_str:
                # 有搜索字符串时，删除搜索字符
                search_str = search_str[:-1]  # 删除最后一个字符
                selected_file = 0  # 重置选中位置到第一个
            else:
                # 没有搜索字符串时，返回上级目录
                # 保存当前目录的选中位置（使用原始文件列表的索引）
                if current_path in path_history:
                    current_history = path_history[current_path]
                    # 找到当前选中文件在原始文件列表中的位置
                    if files and 0 <= selected_file < len(files):
                        selected_filename = files[selected_file]
                        if selected_filename in current_history["original_files"]:
                            original_index = current_history["original_files"].index(selected_filename)
                            current_history["selected_index"] = original_index
                
                current_path = os.path.normpath(os.path.join(current_path, "../"))
                # 恢复上级目录的选中位置
                if current_path in path_history:
                    selected_file = path_history[current_path]["selected_index"]
                else:
                    selected_file = 0
                search_str = ""  # 清除搜索
        elif key == 27:  # ESC
            exit()  # 退出程序
        elif key == curses.KEY_RIGHT or key == 454:
            selected_file = (selected_file + (rows - 3)) % len(files)
        elif key == curses.KEY_LEFT or key == 452:
            selected_file = (selected_file - (rows - 3)) % len(files)
        elif (key == curses.KEY_UP or key == 450):
            selected_file = (selected_file - 1) % len(files)
        elif (key == curses.KEY_DOWN or key == 456):
            selected_file = (selected_file + 1) % len(files)
        elif key == ord('\n'):
            if files:  # 确保文件列表不为空
                new_path = os.path.normpath(os.path.join(current_path, files[selected_file]))
                if os.path.isdir(new_path):
                    # 保存当前目录的选中位置（使用原始文件列表的索引）
                    if current_path in path_history:
                        current_history = path_history[current_path]
                        # 找到当前选中文件在原始文件列表中的位置
                        if files and 0 <= selected_file < len(files):
                            selected_filename = files[selected_file]
                            if selected_filename in current_history["original_files"]:
                                original_index = current_history["original_files"].index(selected_filename)
                                current_history["selected_index"] = original_index
                    
                    current_path = new_path
                    if files[selected_file] == "../":
                        if current_path in path_history:
                            selected_file = path_history[current_path]["selected_index"]
                        else:
                            selected_file = 0
                    else:
                        selected_file = 0
                    search_str = ""  # 进入新目录时清除搜索
                elif os.path.isfile(new_path):
                    if new_path.endswith('.jsonl') or new_path.endswith('.json') or new_path.endswith('.txt'):
                        display_data(stdscr, new_path)
                        # 重新获取当前目录的文件列表
                        files, original_files = list_files(stdscr, current_path, selected_file, search_str, file_cache, key=key)
                        if current_path not in path_history:
                            path_history[current_path] = {"original_files": original_files, "selected_index": selected_file}

        # 更新显示
        files, original_files = list_files(stdscr, current_path, selected_file, search_str, file_cache, key=key)
        
        # 更新路径历史
        if current_path not in path_history:
            path_history[current_path] = {"original_files": original_files, "selected_index": selected_file}
        else:
            path_history[current_path]["original_files"] = original_files
        
        stdscr.refresh()


if __name__ == "__main__":
    curses.wrapper(file_explorer)
