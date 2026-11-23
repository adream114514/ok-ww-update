# ok-ww-update（带「角色代码」功能）

这是 [ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves)（鸣潮自动化工具 ok-ww）安装版的**更新源**，内容是官方正式版加上被移除的「角色代码」功能。

> **使用本工具存在封号风险。如果你不清楚自己在做什么，请不要使用。**

## 这个仓库做什么

上游在 [`d0a5929`](https://github.com/ok-oldking/ok-wuthering-waves/commit/d0a59291332b1feb438f90d57b370d7f4ec2d831)（2026-11-16）删除了「角色代码」（自定义角色代码 / 配队代码工坊）。

GitHub Actions（[`.github/workflows/sync.yml`](.github/workflows/sync.yml)）每 2 小时运行一次：

1. 读取官方更新仓库 [`ok-oldking/ok-ww-update`](https://github.com/ok-oldking/ok-ww-update) 的版本标签。
2. 对本仓库还没有的版本（≥ `v3.8.13`），用 [`tools/apply_charcode.py`](tools/apply_charcode.py) 把功能补回去：
   - 加回 `src/char/CustomCharLoader.py`、`src/gui/CharacterCodeTab.py`（[`charcode/overlay/`](charcode/overlay/)）
   - 在 `CharFactory.py`、`BaseCombatTask.py` 恢复调用，在 `config.py` 注册「角色代码」页
   - 合并翻译并重新编译 `i18n/*/ok.mo`
   - 把 `pyappify.yml` 的 `git_url` 改成本仓库
3. 生成同名版本标签（例如 `v3.8.13`）并推送；`release` 分支始终指向最新版本。

除上述文件外，其余文件与官方版本**逐字节相同**；脚本会自动校验，有任何意外改动就不会发布。

工坊下载源是 [`adream114514/ok-ww-char-code`](https://github.com/adream114514/ok-ww-char-code)。

## 安装版切换到本更新源

1. 完全退出 ok-ww 和启动器。
2. 打开 `<安装目录>\data\apps\ok-ww\working\pyappify.yml`，把 **两个** `git_url` 都改成：
   ```yaml
   git_url: "https://github.com/adream114514/ok-ww-update.git"
   ```
3. 启动启动器，检查更新 / 在版本列表里选择最新版本。

本仓库发布的版本里，`pyappify.yml` 已经指向本仓库，所以以后每次更新都会继续从这里拉取。

> 不要改 `data\apps\ok-ww\app.json`，启动器每次启动都会用 `pyappify.yml` 覆盖它。

## 补丁打不上时

上游改动了锚点代码时，Actions 会失败并发邮件，已发布的版本不受影响（安装版会停在上一个版本）。修复 `tools/apply_charcode.py` 后，在 Actions 页面手动运行 **Sync official releases + character code** 即可。

本地验证：

```bash
pip install polib
python tools/apply_charcode.py <官方版本解压目录> https://github.com/adream114514/ok-ww-update.git
```

## 许可

ok-ww 以 [AGPL-3.0](https://github.com/ok-oldking/ok-wuthering-waves/blob/master/LICENSE.txt) 发布，本仓库发布的版本同样遵循 AGPL-3.0，完整源码即为各版本标签的内容。
