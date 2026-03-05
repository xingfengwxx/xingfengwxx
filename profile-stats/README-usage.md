# Profile Stats Card 使用说明

该方案不依赖 `github-readme-stats.vercel.app`，通过 GitHub Actions 定时生成 `profile-stats.svg`。

## 1) 放置文件

- `profile-stats/generate_profile_stats.py`
- `.github/workflows/profile-stats-card.yml`

## 2) 工作流会做什么

- 每 12 小时触发一次（也支持手动触发）
- 调用 GitHub API 统计：
  - Total Stars
  - Total Commits（近一年）
  - Total PRs（近一年）
  - Total Issues（近一年）
  - Contributed to（近一年）
- 生成 `profile-stats.svg`
- 推送到 `output` 分支根目录

## 3) README 引用方式

在 GitHub Profile README 中添加：

![GitHub Stats](https://raw.githubusercontent.com/xingfengwxx/xingfengwxx/output/profile-stats.svg)

## 4) 注意事项

- 请确保该 workflow 放在 **个人主页仓库**：`xingfengwxx/xingfengwxx`
- 默认分支若为 `master`，无需改动；workflow 会自动推送到 `output` 分支
- 若想改用户名，修改 workflow 里 `USERNAME` 环境变量
