# 隧道传输事故：paramiko 转发慢 200 倍，固定改 OpenSSH 原生转发

**日期：** 2026-10-21（离婚后 EP01 文戏生产中定位）
**结论：** vm106 上的 paramiko Python 转发器禁止承载生产流量；固定使用
OpenSSH 原生 `ssh -L` 转发。规矩已写入 `.cursor/rules/h3-gpu-vm106.mdc`。

## 症状

- 文戏每条生成只要约 242–297s，但条与条之间 Comfy 队列空转约 6 分钟，
  UI 上像任务停了。实际是 runner 在给下一条上传 7 张参考图（约 13MB）。
- 连接统计：WSL→vm106 的 TCP 连接 `rwnd_limited 89%`，即本地一直在等
  vm106 侧把数据排进 SSH 通道；已发 13.5MB 与生成耗时完全不成比例。

## 实测（同一文件、同一卡、同一 Comfy `/upload/image`）

文件 `id0-char-001-w01.png`（2,187,736 B）：

| 路径 | 耗时 | 速率 |
|---|---|---|
| 8191 paramiko 转发（`/tmp/comfy_ssh_forward_8191.py`） | 49.66s | 44KB/s |
| 8193 OpenSSH 原生转发（`ssh -N -L`） | 0.24s | 9.1MB/s |

差约 200 倍。瓶颈在 paramiko 转发的窗口/包处理（32KB 包、Python 逐包
转发），不在显卡、Comfy、飞牛或局域网。

## 处置

1. vm106 无 sshpass，未装包；改用密钥：vm106 生成转发专用密钥
   `/tmp/.comfy_fwd_key`，经 paramiko（passfile 一次性）把公钥装到卡的
   `~/.ssh/authorized_keys`。
2. 先在 8193 起 OpenSSH 转发验证（`ssh -i /tmp/.comfy_fwd_key
   -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -N
   -L 0.0.0.0:8193:127.0.0.1:8188 root@<卡> -p <port>`），
   `/system_stats` 与上传实测均正常。
3. 生产切换安排在集与集之间：EP01 仍用旧隧道跑完（切换时 U03 在跑），
   EP01 结束、队列为空时把 8191 也换成 OpenSSH 转发，验
   `/system_stats` 为 `RTX 5090 : native` 后再起 EP02。切换守候脚本
   会先确认 EP02 未被旧 runner 提交，避免孤儿 prompt。
4. runner 侧同时去重：`scripts/run_lihun_wenxi.py` 对相同
   （文件名， 大小）的参考图只上传一次，同集 42 次上传降到约 9 次。
5. 切换时踩的坑：在 `ssh vm106 "... ssh -N -L ... &"` 里以后台方式起的
   OpenSSH 转发，会在该 ssh 会话结束时被 SIGHUP 带走（8191 一度无监听，
   接管脚本验卡失败自停，未丢任何 prompt；当时 U03 已完整归档）。
   固定起法：`setsid ssh ... < /dev/null &` 完全脱离会话再验监听。
   卡和 Comfy 本体全程无事，8193 的先行转发可作对照。

## 今后口径

- 新卡开机建隧道：一律 OpenSSH 原生转发（见规则文件命令模板）。
- paramiko 转发只作应急诊断，不跑生产；发现条间空档异常先测
  `/upload/image` 速率再怀疑生成。
- 转发切换只在队列为空时做，换后立刻验 `/system_stats`。
