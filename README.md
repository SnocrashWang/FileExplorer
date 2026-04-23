# README

## Install
1. Download this `file_explorer.py` file anywhere.
2. If you want to use this script anywhere quickly, apply this:
    ```
    echo 'alias fe="python /path/to/file_explorer.py"' >> ~/.bashrc
    ```

## Usage
This is a terminal-based file explorer for browsing directories and viewing data files.
Supported data file formats include: jsonl, json, txt. Note that txt here is a special format of jsonl used in pretrain data.

### File Mode
In this mode, you can browse directories and files, and open supported data files (jsonl, json, txt) for a convenient viewing.

|Command|Usage|
|-|-|
| UP/DOWN Arrows | Move selection up/down |
| LEFT/RIGHT Arrows | Page up/down |
| ENTER | Open selected directory/file, enter Data Mode |
| BACKSPACE | Go to parent directory |
| ESC | Exit the explorer |
| **Search Tool** | |
| Type any text | Search files by name (ignore case) |
| BACKSPACE | Delete last character in search |

### Data Mode
In this mode, you can view the content of jsonl/json format data file, with varies of functionalities to help you explore the data.

|Command|Usage|
|-|-|
| UP/DOWN Arrows | Scroll up/down the content |
| LEFT/RIGHT Arrows | View previous/next data entry |
| PAGE UP/DOWN | Jump to previous/next key in current data entry |
| TAB | Switch between Search and Jump tool |
| SHIFT+TAB | Switch whether to display the value of json |
| CTRL+A | Refresh current data file |
| CTRL+B | Clear data cache |
| ESC | Return to File Mode |
| **Search Tool** | |
| Type any text | Search for the text in current data file|
| BACKSPACE | Delete last character in search|
| ENTER | Jump to next occurrence|
| **Jump Tool** | |
| Type line number | Choose specified data entry (1-based) |
| BACKSPACE | Delete last character in line number |
| ENTER | Jump to specified data entry |

### Debug Mode
1. Add lines like `log.write(...)` where you want to print something in the script.
2. Add `-d` or `--debug` param when executing, the script would create a temporary log file `.file_explorer.log` where you execute it.


## Note
1. In most operation systems, `KEY_BACKSPACE` is `127`. But in certain terminals or os, it might be `8` instead. If you meet a problem with backspace, you could test the code of the key and specify `curses.KEY_BACKSPACE = ?` at the beginning of the script.

## Existing Problems
1. There exist a rare condition in search tool, data mode, that would cause the script dumped. But I haven't had time to detect it. If you find the bug, please open an issue.