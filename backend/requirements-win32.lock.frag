# Windows 平台标记依赖手动入锁片段（v1.0.7 安全治理批）
# Linux 侧 pip-compile 对 marker 不满足的包不产条目；Windows 打包线按
# requirements-lock.txt --require-hashes 安装时需要它们。由
# .github/workflows/regression.yml 的 regen-locks job 在 pip-compile 后
# 幂等追加（requirements-win32.lock.frag）。版本升级时同步更新本文件
# 与 requirements.txt 的声明（版本号保持一致）。

colorama==0.4.6 ; sys_platform == "win32" \
    --hash=sha256:08695f5cb7ed6e0531a20572697297273c47b8cae5a63ffc6d6ed5c201be6e44 \
    --hash=sha256:4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6
    # via
    #   -r requirements.txt
    #   click
    #   qrcode

pywin32==312 ; sys_platform == "win32" \
    --hash=sha256:02ebca0f0242b75292e218065004310d6a477407c09fa449bfe4f6022bc0c0fc \
    --hash=sha256:17948aeadbdb091f0ced6ef0841620794e68327b94ee415571c1203594b7215c \
    --hash=sha256:3020656e34f1cf7faeb7bccd2b84653a607c6ff0c55ada85e6487d61716deabd \
    --hash=sha256:59aba5d5940842075343a5ddc6b11f1cdf0d1567fe745290359dfbcc7c2eb831 \
    --hash=sha256:5c1fbe4a937a73ae9297384a3da38518cbc694c68ad8a809b2e19acd350f03ed \
    --hash=sha256:5dbc35d2b5320dc07f25fa31269cfb767471002b17de5eb067d03da68c7cb2db \
    --hash=sha256:6017c58e12f6809fbb0555b75df144c2922a9ffd18e4b9b5afa863b6c1a9d950 \
    --hash=sha256:772235332b5d1024c696f11cea1ae4be7930f0a8b894bb43db14e3f435f1ff7e \
    --hash=sha256:7a27df850933d16a8eabfbaeb73d52b273e2da667f80d70b01a89d1f6828d02c \
    --hash=sha256:9fce94568364e0155e6dfb781ac5d95903be8baf28670632beab1b523f300daa \
    --hash=sha256:a4dd3a848290ef724347b19f301045831d8e802fa4464f491b98b1e0a081432e \
    --hash=sha256:a77a90fbb6881238d2ca9c6fd797b25817f3768fe78d214a90137ff055a75f5b \
    --hash=sha256:a8597d28f267b39074aef51fa593530082b39cbe5a074226096857b1fed2dfb9 \
    --hash=sha256:b2200a054ca6d6625c4842fc56a4976a4b47f96b73dbe5538c3f813a80359f47 \
    --hash=sha256:b457f6d628a47e8a7346ce22acb7e1a46a4a78b52e1d17e1af56871bd19a93bc \
    --hash=sha256:c2f03a0f73f804a13c2735b99392b0cd426bb4f2c4d0178e5ac966a0f21618d5 \
    --hash=sha256:c53e878d15a1c44788082bfe712a905433473aa38f86375b7cf8b45e3acbaaf9 \
    --hash=sha256:d11417d84412f859b722fad0841b3614459ed0047f7542d8362e77884f6b6e8a \
    --hash=sha256:d620900033cc7531e50727c3c8333091df5dd3ffe6d68cdca38c03f5821408d5 \
    --hash=sha256:dab4f65ac9c4e48400a2a0530c46c3c579cd5905ecd11b80692373915269208b \
    --hash=sha256:dc90147579a905b8635e1b0ec6514967dcb07e6e0d9c42f1477feef14cac23bb
    # via mcp

tzdata==2026.3 ; platform_system == "Windows" \
    --hash=sha256:4a1518b8993086a7982523e071643f3c0e5f213e75b21318e78bcabfff9d1415 \
    --hash=sha256:dc096730c87af6cab1b171c9d532be840741ff5d459015e7f6947bd7d7e54931
    # via
    #   -r requirements.txt
    #   tzlocal
