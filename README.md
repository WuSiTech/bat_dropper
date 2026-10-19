# BAT 释放器生成器

一个带图形界面的工具，用于把任意文件以 Base64 形式嵌入到批处理文件（`.bat`）中，运行时自动释放（解码还原）到指定目录。支持 UAC 自提权、释放后运行目标文件、运行后删除等功能。

> **⚠️ 重要警告**
> 本项目生成的 BAT 会因 "Base64 附加 + `certutil -decode` 提取" 这一组合而**被绝大多数杀毒软件/EDR 高度关注甚至直接拦截**。
> 请**仅在自己完全可控的合法场景**下使用（如内部运维分发、教学演示、自我测试）。
> **严禁**用于传播恶意软件、逃避检测或任何违反法律法规的用途。作者不对任何滥用行为负责。

---

## 功能特性

| 特性 | 说明 |
|------|------|
| Base64 嵌入 | 每个文件单独 Base64 编码，附在 BAT 末尾，用 `::B64_START_i` / `::B64_END_i` 标记 |
| 智能提取 | 单文件用 `more` 提取，多文件用 PowerShell 按标记提取 |
| UAC 自提权 | 可选在 BAT 开头插入 VBScript 提权代码，以管理员权限运行整个脚本 |
| 释放后运行 | 可选择释放完成后自动（或弹窗询问后）运行某个目标文件 |
| 运行后清理 | 可选在目标运行 5 秒后自动删除释放出来的文件 |
| 临时文件清理 | 解码完成后自动删除 `__tmp.b64` 临时文件（可保留用于调试） |
| 文件名清洗 | 自动替换会破坏 BAT 语法的字符（`" & | ^ < > ( ) ! % '`） |
| 重名处理 | 同名文件自动加 `_1`、`_2` 后缀，避免互相覆盖 |
| 编码自适应 | 优先以 GBK 输出（兼容中文路径），失败则回退 UTF-8 |
| 后台生成 | 大文件编码在工作线程中完成，界面不卡顿 |

---

## 环境要求

- **Python**：3.8+（代码使用 `from __future__ import annotations` 与 `list[...]` 泛型注解）
- **依赖**：仅标准库（`tkinter`、`base64`、`pathlib` 等），**无需额外安装**
- **Tkinter**：部分 Linux 发行版需单独安装
  ```bash
  sudo apt install python3-tk        # Debian / Ubuntu
  sudo dnf install python3-tkinter   # Fedora
  ```
- **目标平台**：生成的 BAT 面向 **Windows**（依赖 `certutil`、`more`、`powershell`、`findstr`、`pushd`）

---

## 快速开始

```bash
python WuSi_BatDropper.py
```

启动后界面分为四个区域：

```
┌──────────────────────────────────────────────────────────────┐
│  要释放的文件                                                  │
│  [添加文件] [添加文件夹] [移除选中] [清空]                        │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 文件名 │ 大小 │ 原始路径                                │  │
│  └────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│  输出设置                                                      │
│  输出 .bat  : [_______________________] [浏览…]               │
│  释放目录   : [_______________________] [浏览…]  留空=脚本目录  │
│  完成后运行 : [（不运行） ▼]  [ ] 运行前弹窗询问                  │
│  [ ] 运行后删除释放的文件  [✓] BAT 自提权(UAC)                   │
│  [ ] 保留临时文件          [ ] 结束时暂停                       │
├──────────────────────────────────────────────────────────────┤
│  [生成 BAT 释放器]  就绪                                        │
├──────────────────────────────────────────────────────────────┤
│  日志                                                          │
└──────────────────────────────────────────────────────────────┘
```

### 操作步骤

1. **添加文件**：点「添加文件」选择单个/多个文件，或「添加文件夹」递归加入整个目录。
2. **配置输出**：
   - **输出 .bat**：生成的批处理保存位置（默认当前目录 `release.bat`）。
   - **释放目录**：目标文件解码后存放的位置。**留空表示释放到 BAT 自身所在目录**（`%~dp0`）。
   - **完成后运行**：从下拉框中选择一个文件作为"释放后自动运行"的目标；选「（不运行）」则只释放不运行。
3. **按需勾选选项**：
   - **运行前弹窗询问**：用 PowerShell 弹 MessageBox 让用户确认。
   - **运行后删除释放的文件**：目标运行 5 秒后自动删除。
   - **BAT 自提权（UAC）**：默认开启，运行 BAT 会请求管理员权限。
   - **保留临时文件**：保留 `__tmp.b64` 便于调试。
   - **结束时暂停**：BAT 结尾加 `pause`，方便看输出。
4. **点「生成 BAT 释放器」**，完成后会弹出提示并显示输出路径、大小与编码。

---

## 生成的 BAT 工作原理

以"单个文件 + UAC 提权 + 释放后弹窗运行"为例，生成的 BAT 结构如下：

```bat
@echo off
rem ---- UAC 自提权检查 ----
setlocal
set uac=~uac_permission_tmp_%random%
md "%SystemRoot%\system32\%uac%" 2>nul
if %errorlevel%==0 ( rd ... ) else (
    echo set uac = CreateObject^("Shell.Application"^)>"%temp%\%uac%.vbs"
    echo uac.ShellExecute "%~s0","","","runas",1 >>"%temp%\%uac%.vbs"
    ...
)
endlocal

setlocal
pushd "%~dp0"
set "DEST=%~dp0"
if not exist "%DEST%" mkdir "%DEST%" >nul 2>nul
set "SELF=%~f0"
set "TMPB64=%~dp0__tmp.b64"

rem ---- [1/1] 释放 target.exe ----
for /f "tokens=1 delims=:" %%a in ('findstr /n "^::B64_START_1" "%~f0"') do set /a "START=%%a"
more +%START% "%~f0" | findstr /v "^::" > "%TMPB64%"
certutil -f -decode "%TMPB64%" "%DEST%target.exe" >nul 2>nul
if errorlevel 1 goto :err_decode

rem ---- 清理临时文件 ----
del "%TMPB64%" >nul 2>nul

rem ---- 询问是否运行 ----
powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; ..."
if errorlevel 1 goto :the_end

rem ---- 启动 ----
start "" "%DEST%target.exe"
goto :the_end

:err_decode
echo 解码失败（certutil 报错）。
pause
:the_end
popd
echo 完成。
endlocal
exit /b 0

::B64_START_1
TVqQAAMAAAAEAAAA//8AALgAAAAAAAAAQAAA...
::B64_END_1
```

**关键点：**

- **定位数据**：`findstr /n "^::B64_START_1"` 找到标记所在行号 `START`。
- **截取数据**：`more +START` 从标记行之后开始输出，`findstr /v "^::"` 过滤掉 `::` 注释行（即标记本身）。
- **解码**：`certutil -f -decode` 把 Base64 还原为二进制。
- **提权**：借 VBScript 的 `ShellExecute ... "runas"` 以管理员身份重启自身。
- **多文件场景**：单文件用 `more`，多文件改用 PowerShell 按 `::B64_START_i` / `::B64_END_i` 精确截取（`more` 的方式在多个数据块间难以精确切分）。

---

## 输出设置详解

| 选项 | 作用 | 对应 BAT 代码 |
|------|------|---------------|
| 释放目录 | 文件落盘位置，留空 = `%~dp0` | `set "DEST=..."` + `mkdir` |
| 完成后运行 | 释放后 `start` 的目标 | `start "" "%DEST%<file>"` |
| 运行前弹窗询问 | 弹 MessageBox，取消则跳过运行 | PowerShell `MessageBox.Show(...,4,32)` |
| 运行后删除释放的文件 | 启动后延迟 5 秒删除 | PowerShell `Start-Sleep 5; Remove-Item` |
| BAT 自提权（UAC） | 请求管理员权限重启自身 | VBScript `ShellExecute "runas"` |
| 保留临时文件 | 不清除 `__tmp.b64` | 跳过 `del "%TMPB64%"` |
| 结束时暂停 | 末尾加 `pause` | `pause` |

---

## 常见问题（FAQ）

**Q: 生成的 BAT 一运行就报"解码失败（certutil 报错）"？**
A: 常见原因：
1. 杀软拦截了 `certutil` 或删除了 BAT 尾部数据；
2. 文件内容被邮件/传输工具截断（Base64 被换行或裁剪）；
3. 使用了非 Windows 环境或无 `certutil` 的系统。
建议开启「保留临时文件」，检查 `__tmp.b64` 是否为空。

**Q: 中文路径出现乱码？**
A: 工具会优先尝试 GBK 编码（Windows 中文默认代码页），如果失败回退 UTF-8。若仍乱码，请确保目标机器的控制台代码页为 `936`（GBK）。可在 BAT 开头手工加 `chcp 936 >nul`。

**Q: 为什么默认开启 UAC 自提权？**
A: 很多释放场景（写 `Program Files`、注册服务、修改系统目录）需要管理员权限。如不需要可取消勾选；注意即便目标文件本身无需提权，频繁的 UAC 弹窗也会引起用户警觉。

**Q: 释放多个文件时"完成后运行"能选哪些？**
A: 下拉框只会列出经过文件名清洗和去重后的**最终释放文件名**（即 `unique_name(sanitize(name))` 的结果），与磁盘上实际落盘的名字一致。

**Q: 支持释放子目录结构吗？**
A: 目前只保留文件名、不保留原始相对路径。文件夹递归添加时所有文件会被平铺到释放目录，重名会自动加后缀。

**Q: 生成的 BAT 是 GBK 还是 UTF-8？**
A: 生成时先尝试 GBK，`UnicodeEncodeError` 时回退 UTF-8。状态栏/日志会显示实际使用的编码。

---

## 代码结构

```
WuSi_BatDropper.py
├── sanitize(name)             # 清洗会破坏 BAT 语法的字符
├── unique_name(name, used)    # 重名加后缀
├── norm_dest(d)               # 规整释放目录（补尾部反斜杠）
├── build_bat(...)             # 核心：拼装 BAT 文本（含 UAC/提取/运行/清理）
└── App(tk.Tk)                 # Tkinter GUI
    ├── _build_ui()            # 构建界面
    ├── _update_run_options()  # 联动启用/禁用"弹窗询问""运行后删除"
    ├── add_files / add_folder / remove_selected / clear_files
    ├── _refresh_files()       # 刷新列表 + 重算下拉框候选
    ├── pick_output / pick_dest
    ├── log / log_clear / set_status
    ├── on_generate()          # 校验参数并启动工作线程
    ├── _worker(...)           # 后台编码 + 写文件
    └── _done / _fail          # 收尾回调
```

---

## 免责声明

1. 本工具仅面向**安全研究、教学演示、内部运维**等合法场景。
2. 生成的产物可能被反病毒软件判定为木马/释放器（dropper），这是**预期内的**技术特征，不构成规避检测的手段。
3. 使用者应自行确保对目标机器拥有合法操作权限，并遵守所在地区法律法规。
4. 作者不对因使用本工具造成的任何直接或间接损失承担责任。
