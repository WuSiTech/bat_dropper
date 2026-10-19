#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
—— 带图形界面的 BAT 文件释放器生成器（Base64 附加 + more 提取 + UAC 自提权）

特性：
  1) 每个文件单独 Base64 编码，附在 BAT 末尾，用 ::B64_START_i / ::B64_END_i 标记
  2) 单文件用 more 提取，多文件用 PowerShell 按标记提取
  3) 可选在 BAT 开头插入 VBScript 自提权代码，整个脚本以管理员权限运行
  4) 释放完成后可选弹窗询问是否运行目标文件
  5) 可选运行后删除释放的文件
警告：
    生成的 BAT 会被杀软高度关注，请仅用于自己可控的合法场景。
"""

from __future__ import annotations

import base64
import os
import textwrap
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

B64_WIDTH = 76
NO_RUN = "（不运行）"
TMP_B64 = "__tmp.b64"


# 工具函数

def sanitize(name: str) -> str:
    """去掉会破坏 BAT 语法的字符。"""
    bad = '"&|^<>()!%\''
    for ch in bad:
        name = name.replace(ch, "_")
    name = name.strip()
    if name in ("", ".", ".."):
        name = "_"
    return name


def unique_name(name: str, used: set[str]) -> str:
    """避免同名文件互相覆盖。"""
    if name not in used:
        used.add(name)
        return name
    stem, ext = os.path.splitext(name)
    i = 1
    while f"{stem}_{i}{ext}" in used:
        i += 1
    out = f"{stem}_{i}{ext}"
    used.add(out)
    return out


def norm_dest(d: str) -> str:
    """把释放目录规整成以反斜杠结尾的形式。"""
    d = (d or "").strip()
    if not d or d == "%~dp0":
        return "%~dp0"
    if d.endswith(("\\", "/")):
        return d
    if d.endswith(":"):
        return d + "\\"
    return d + "\\"


# ============================================================ 生成 BAT

def build_bat(files, dest="%~dp0", run_after=None,
              ask=True, cleanup=True, delete_released=False,
              pause_at_end=False, self_elevate=False) -> str:
    """
    files           : [(src_path, arcname), ...]
    dest            : 释放目录（BAT 变量）
    run_after       : 释放后要运行的文件名，None 表示不运行
    ask             : 运行前是否弹窗询问
    cleanup         : 是否删除 __tmp.b64 临时文件
    delete_released : 是否在运行后删除释放出来的文件
    pause_at_end    : 结束时是否 pause
    self_elevate    : 是否在 BAT 开头插入 VBScript 自提权代码
    """
    # 每个文件单独 base64 编码
    encoded: list[tuple[str, str]] = []
    for src, arc in files:
        data = Path(src).read_bytes()
        b64 = base64.b64encode(data).decode("ascii") if data else ""
        encoded.append((arc, b64))

    d = norm_dest(dest)
    L: list[str] = []
    a = L.append

    a("@echo off")

    # ---------- 可选：UAC 自提权代码块 ----------
    if self_elevate:
        a("rem ---- UAC 自提权检查 ----")
        a("setlocal")
        a("set uac=~uac_permission_tmp_%random%")
        a('md "%SystemRoot%\\system32\\%uac%" 2>nul')
        a('if %errorlevel%==0 ( rd "%SystemRoot%\\system32\\%uac%" >nul 2>nul ) else (')
        a('    echo set uac = CreateObject^("Shell.Application"^)>"%temp%\\%uac%.vbs"')
        a('    echo uac.ShellExecute "%~s0","","","runas",1 >>"%temp%\\%uac%.vbs"')
        a('    echo WScript.Quit >>"%temp%\\%uac%.vbs"')
        a('    "%temp%\\%uac%.vbs" /f')
        a('    del /f /q "%temp%\\%uac%.vbs" & exit )')
        a("endlocal")
        a("")

    a("setlocal")
    a('pushd "%~dp0"')
    a("")
    a(f'set "DEST={d}"')
    a('if not exist "%DEST%" mkdir "%DEST%" >nul 2>nul')
    a('set "SELF=%~f0"')
    a('set "TMPB64=%~dp0__tmp.b64"')
    a("")

    total = len(encoded)
    for i, (arc, b64) in enumerate(encoded, 1):
        a(f"rem ---- [{i}/{total}] 释放 {arc} ----")
        if b64:
            if total == 1:
                a(f'for /f "tokens=1 delims=:" %%a in (\'findstr /n "^::B64_START_1" "%~f0"\') do set /a "START=%%a"')
                a(f'more +%START% "%~f0" | findstr /v "^::" > "%TMPB64%"')
            else:
                a(f'powershell -NoProfile -Command "$c = Get-Content \'%~f0\'; '
                  f'$s = [array]::IndexOf($c, \'::B64_START_{i}\') + 1; '
                  f'$e = [array]::IndexOf($c, \'::B64_END_{i}\'); '
                  f'$c[$s..($e-1)] | Out-File -Encoding ascii \'%TMPB64%\'"')
            a(f'certutil -f -decode "%TMPB64%" "%DEST%{arc}" >nul 2>nul')
            a("if errorlevel 1 goto :err_decode")
        else:
            a(f'type nul > "%DEST%{arc}"')
        a("")

    if cleanup:
        a("rem ---- 清理临时文件 ----")
        a(f'del "%TMPB64%" >nul 2>nul')
        a("")

    if run_after:
        run_after = sanitize(run_after)
        if ask:
            a("rem ---- 询问是否运行 ----")
            a('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms;'
              ' $r=[System.Windows.Forms.MessageBox]::Show(\'文件已释放完成，是否立即运行？\','
              '\'释放器\',4,32); if($r -eq 6){exit 0}else{exit 1}"')
            a("if errorlevel 1 goto :the_end")
            a("")

        a("rem ---- 启动 ----")
        a(f'start "" "%DEST%{run_after}"')

        if delete_released:
            a("rem ---- 运行后 5 秒删除释放的文件 ----")
            a('start "" /b powershell -NoProfile -WindowStyle Hidden '
              f'-Command "Start-Sleep -Seconds 5; '
              f'Remove-Item -LiteralPath \'%DEST%{run_after}\' '
              '-Force -Recurse -ErrorAction SilentlyContinue"')
        a("")

    a("goto :the_end")
    a("")
    a(":err_decode")
    a("echo 解码失败（certutil 报错）。")
    a("pause")
    a("")
    a(":the_end")
    a("popd")
    a("echo 完成。")
    a("endlocal")
    if pause_at_end:
        a("pause")
    a("exit /b 0")

    # 把 base64 数据附在 BAT 末尾
    for i, (arc, b64) in enumerate(encoded, 1):
        if b64:
            a("")
            a(f"::B64_START_{i}")
            for ln in textwrap.wrap(b64, B64_WIDTH):
                a(ln)
            a(f"::B64_END_{i}")

    return "\r\n".join(L) + "\r\n"


# ============================================================ GUI

class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("BAT 释放器生成器（Base64 附加 + more 提取 + UAC 自提权）")
        self.geometry("880x760")
        self.minsize(780, 660)

        self.files: list[Path] = []
        self.var_out = tk.StringVar(value=str(Path.cwd() / "release.bat"))
        self.var_dest = tk.StringVar(value="")
        self.var_run = tk.StringVar(value=NO_RUN)
        self.var_ask = tk.BooleanVar(value=True)
        self.var_keep = tk.BooleanVar(value=False)
        self.var_del = tk.BooleanVar(value=False)
        self.var_pause = tk.BooleanVar(value=False)
        self.var_elevate = tk.BooleanVar(value=True)  # 默认开启 UAC 自提权

        self._build_ui()
        self._update_run_options()

    # ------------------------------------------------ 界面

    def _build_ui(self):
        lf_files = ttk.LabelFrame(self, text="要释放的文件（Base64 会附在 BAT 末尾）")
        lf_files.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        bar = ttk.Frame(lf_files)
        bar.pack(side="bottom", fill="x", padx=6, pady=(0, 6))
        ttk.Button(bar, text="添加文件", command=self.add_files).pack(side="left")
        ttk.Button(bar, text="添加文件夹", command=self.add_folder).pack(side="left", padx=4)
        ttk.Button(bar, text="移除选中", command=self.remove_selected).pack(side="left", padx=4)
        ttk.Button(bar, text="清空", command=self.clear_files).pack(side="left", padx=4)

        wrap = ttk.Frame(lf_files)
        wrap.pack(side="top", fill="both", expand=True, padx=6, pady=6)

        cols = ("name", "size", "path")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("name", text="文件名")
        self.tree.heading("size", text="大小")
        self.tree.heading("path", text="原始路径")
        self.tree.column("name", width=200, anchor="w")
        self.tree.column("size", width=100, anchor="e")
        self.tree.column("path", width=480, anchor="w")

        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # ---- 输出设置 ----
        sf = ttk.LabelFrame(self, text="输出设置")
        sf.pack(fill="x", padx=10, pady=4)
        sf.columnconfigure(1, weight=1)

        ttk.Label(sf, text="输出 .bat：").grid(row=0, column=0, sticky="w", padx=(8, 4), pady=6)
        ttk.Entry(sf, textvariable=self.var_out).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Button(sf, text="浏览…", command=self.pick_output).grid(row=0, column=2, padx=(4, 8), pady=6)

        ttk.Label(sf, text="释放目录：").grid(row=1, column=0, sticky="w", padx=(8, 4), pady=6)
        ttk.Entry(sf, textvariable=self.var_dest).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(sf, text="浏览…", command=self.pick_dest).grid(row=1, column=2, padx=(4, 8), pady=6)
        ttk.Label(sf, text="留空 = 释放到 .bat 所在目录", foreground="#777").grid(
            row=1, column=3, sticky="w", padx=(0, 8))

        ttk.Label(sf, text="完成后运行：").grid(row=2, column=0, sticky="w", padx=(8, 4), pady=6)
        self.cmb_run = ttk.Combobox(sf, textvariable=self.var_run,
                                    values=[NO_RUN], state="readonly")
        self.cmb_run.grid(row=2, column=1, sticky="ew", pady=6)
        self.cmb_run.bind("<<ComboboxSelected>>", lambda e: self._update_run_options())

        self.cb_ask = ttk.Checkbutton(sf, text="运行前弹窗询问", variable=self.var_ask)
        self.cb_ask.grid(row=2, column=2, sticky="w", padx=(4, 8))

        opts = ttk.Frame(sf)
        opts.grid(row=3, column=1, columnspan=3, sticky="w", padx=(4, 8), pady=(0, 4))

        self.cb_del = ttk.Checkbutton(
            opts, text="运行后删除释放的文件",
            variable=self.var_del)
        self.cb_del.pack(side="left")

        # ★ UAC 自提权复选框
        ttk.Checkbutton(
            opts, text="BAT 自提权（UAC）",
            variable=self.var_elevate).pack(side="left", padx=10)

        ttk.Checkbutton(opts, text="保留临时文件", variable=self.var_keep).pack(side="left", padx=10)
        ttk.Checkbutton(opts, text="结束时暂停", variable=self.var_pause).pack(side="left", padx=10)

        # ---- 生成按钮 ----
        bf = ttk.Frame(self)
        bf.pack(fill="x", padx=10, pady=4)
        self.btn_gen = ttk.Button(bf, text="生成 BAT 释放器", command=self.on_generate)
        self.btn_gen.pack(side="left")
        self.lbl_status = ttk.Label(bf, text="就绪")
        self.lbl_status.pack(side="left", padx=12)

        # ---- 日志 ----
        lf_log = ttk.LabelFrame(self, text="日志")
        lf_log.pack(fill="x", padx=10, pady=(4, 10))

        self.txt = tk.Text(lf_log, height=9, state="disabled", wrap="word",
                           font=("Consolas", 9))
        sb2 = ttk.Scrollbar(lf_log, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb2.set)
        self.txt.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        sb2.pack(side="right", fill="y", pady=6, padx=(0, 6))

    # ------------------------------------------------ 选项联动

    def _update_run_options(self):
        has_run = self.var_run.get() not in ("", NO_RUN)
        state = "normal" if has_run else "disabled"
        self.cb_ask.config(state=state)
        self.cb_del.config(state=state)
        if not has_run:
            self.var_ask.set(False)
            self.var_del.set(False)

    # ------------------------------------------------ 文件操作

    def add_files(self):
        paths = filedialog.askopenfilenames(title="选择要释放的文件")
        if not paths:
            return
        for p in paths:
            fp = Path(p)
            if fp not in self.files:
                self.files.append(fp)
        self._refresh_files()

    def add_folder(self):
        d = filedialog.askdirectory(title="选择文件夹（会递归加入其中的文件）")
        if not d:
            return
        root = Path(d)
        added = 0
        for fp in sorted(root.rglob("*")):
            if fp.is_file() and fp not in self.files:
                self.files.append(fp)
                added += 1
        self._refresh_files()
        self.log(f"从 {root} 加入了 {added} 个文件")

    def remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        idxs = sorted((int(i) for i in sel), reverse=True)
        for i in idxs:
            del self.files[i]
        self._refresh_files()

    def clear_files(self):
        self.files.clear()
        self._refresh_files()

    def _refresh_files(self):
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(self.files):
            try:
                size = p.stat().st_size
                stxt = self._human(size)
            except OSError:
                stxt = "?"
            self.tree.insert("", "end", iid=str(i),
                             values=(p.name, stxt, str(p)))

        used: set[str] = set()
        names = []
        for p in self.files:
            safe = sanitize(p.name) or "_"
            names.append(unique_name(safe, used))
        self.cmb_run["values"] = [NO_RUN] + names
        if self.var_run.get() not in self.cmb_run["values"]:
            self.var_run.set(NO_RUN)
        self._update_run_options()

    @staticmethod
    def _human(n: int) -> str:
        for u in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
            n /= 1024
        return f"{n:.1f} TB"

    # ------------------------------------------------ 路径选择

    def pick_output(self):
        p = filedialog.asksaveasfilename(
            title="保存 .bat",
            defaultextension=".bat",
            filetypes=[("批处理文件", "*.bat"), ("所有文件", "*.*")],
            initialfile=Path(self.var_out.get()).name or "release.bat",
        )
        if p:
            self.var_out.set(p)

    def pick_dest(self):
        d = filedialog.askdirectory(title="选择释放目录")
        if d:
            self.var_dest.set(d)

    # ------------------------------------------------ 日志

    def log(self, msg: str):
        self.txt.configure(state="normal")
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def log_clear(self):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")

    def set_status(self, s: str):
        self.lbl_status.config(text=s)

    # ------------------------------------------------ 生成

    def on_generate(self):
        if not self.files:
            messagebox.showwarning("提示", "请先添加要释放的文件")
            return

        out = self.var_out.get().strip()
        if not out:
            messagebox.showwarning("提示", "请填写输出路径")
            return
        if not out.lower().endswith(".bat"):
            out += ".bat"
            self.var_out.set(out)

        dest = self.var_dest.get().strip()
        run = self.var_run.get()
        if run in ("", NO_RUN):
            run = None

        ask = self.var_ask.get()
        keep = self.var_keep.get()
        delete_released = self.var_del.get() and bool(run)
        pause = self.var_pause.get()
        self_elevate = self.var_elevate.get()

        self.btn_gen.config(state="disabled")
        self.set_status("正在生成…")
        self.log_clear()

        threading.Thread(
            target=self._worker,
            args=(list(self.files), out, dest, run, ask, keep,
                  delete_released, pause, self_elevate),
            daemon=True,
        ).start()

    def _worker(self, files, out, dest, run, ask, keep,
                delete_released, pause, self_elevate):
        try:
            entries: list[tuple[Path, str]] = []
            used: set[str] = set()
            total = 0

            for i, p in enumerate(files, 1):
                safe = sanitize(p.name) or f"file_{i}"
                name = unique_name(safe, used)
                entries.append((p, name))
                size = p.stat().st_size
                total += size
                self.after(0, self.log,
                           f"[{i}/{len(files)}] {p.name}  →  {name}   "
                           f"({size:,} 字节)")

            self.after(0, self.log, "生成 BAT…")
            bat = build_bat(entries, dest=dest or "%~dp0",
                            run_after=run, ask=ask, cleanup=not keep,
                            delete_released=delete_released,
                            pause_at_end=pause,
                            self_elevate=self_elevate)

            try:
                raw = bat.encode("gbk")
                enc = "GBK"
            except UnicodeEncodeError:
                raw = bat.encode("utf-8")
                enc = "UTF-8"

            out_path = Path(out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(raw)

            self.after(0, self._done, str(out_path), total,
                       out_path.stat().st_size, enc,
                       bool(run), delete_released, self_elevate)
        except Exception as e:
            self.after(0, self._fail, e)

    def _done(self, out, total, size, enc, has_run,
              delete_released, self_elevate):
        self.btn_gen.config(state="normal")
        self.set_status("完成")
        self.log("")
        self.log(f"输入合计 : {total:,} 字节")
        self.log(f"输出文件 : {out}  ({size:,} 字节, {enc})")
        if self_elevate:
            self.log("已启用 UAC 自提权：运行 BAT 时会先请求管理员权限。")
        if has_run:
            self.log("释放完成后会弹窗询问是否运行目标文件。")
        else:
            self.log("未指定「完成后运行」的文件，BAT 只释放不运行。")
        if delete_released:
            self.log("运行后 5 秒会自动删除释放出来的文件。")
        self.log("")
        self.log("⚠️ Base64 + certutil 属于常见 dropper 特征，可能被杀软拦截。")
        messagebox.showinfo("完成", f"已生成：\n{out}")

    def _fail(self, e):
        self.btn_gen.config(state="normal")
        self.set_status("失败")
        self.log(f"[错误] {e}")
        messagebox.showerror("生成失败", str(e))


# ============================================================

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
