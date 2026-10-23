---
name: comfy-h3-feiniu
description: >-
  Use when listing, copying, or archiving H3 packs and finished units on the
  Feiniu NAS (飞牛, fnos, H3_comfyUI_5090, inbox, or the ai短剧同步文件夹 share).
---

# 飞牛（H3 资产与成片）

密码只放在本机文件里。不要打印，不要写进 git、argv、日志或 skill。

## 连接

| 项 | 值 |
| --- | --- |
| 网页 | `http://192.168.60.103:5666`，账号 `ai` |
| 密码文件 | `/home/linux_dev/.config/fnos/ai.pass`，mode 600 |
| SMB | `192.168.60.103:445` |
| 共享名 | `ai短剧同步文件夹` |
| 账号 | `ai` |

用 impacket 的 `SMBConnection`（SMB3）。pysmb 协商不上。不要 `sudo`，不要 `mount.cifs`。解释器用仓库 `.worktrees/feat-orch/.venv` 里已装的 impacket，不要假设系统 `python3` 有这个包。

```python
smb = SMBConnection(host, host, sess_port=445)
smb.login("ai", password_from_file)
smb.listPath(share, path + "/*")
smb.getFile(share, remote, chunk_callback)          # callback 收到 bytes 块
smb.createDirectory(share, parent)                  # 先建父目录
smb.putFile(share, remote, buffer.read)            # 必须是 read(size)，不能直接塞 bytes
```

`putFile` 的第三个参数是 `read(size)`。把内容放进 `io.BytesIO`，把 `.read` 传进去。

## 目录

共享根下只用 `H3_comfyUI_5090/`。说明在 `H3_comfyUI_5090/说明.txt`。

```text
H3_comfyUI_5090/inbox/                 用户放入资产包。列出即可，不自动改、不自动挪。
H3_comfyUI_5090/archive/<批次>/<集>/<单元>/
                                       成片直接放这里，不打 zip。
```

每个单元目录放该条的 mp4、latent、提示词和 run meta。本地中转是 `/mnt/c/Users/lxy/Downloads/<批次>/`，再按同样的集/单元结构拷到 archive。远端文件大小已经一致就跳过。

不要移动、改写或当数据源使用共享根上的历史目录 `测试H3资产包`。共享根上若还有同名 zip 副本，以 inbox 里的那份为准。

## 何时用

- 用户说飞牛上有新包：只列 `inbox/` 的名字、大小、时间，不下载、不拆，直到用户说拆。
- 成片要给用户看：拷到对应批次的 archive，不压缩。
- 拆解和入队仍走 `comfy-h3-pack-prompt-audit`。飞牛这里不入队。
