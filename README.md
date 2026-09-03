# 大兴安岭自驾游

这是 2026-09-26 至 2026-10-03 的 Quarto 在线路书。默认路线从齐齐哈尔出发，经蘑阿公路、阿尔山、莫日格勒河、卡线、奇乾、根河和五大连池，于 10 月 3 日晚抵达哈尔滨。

在线阅读：<https://aliosvictor.github.io/dongbei-roadbook/>

[![使用 EdgeOne Makers 部署](https://cdnstatic.tencentcs.com/edgeone/pages/deploy.svg)](https://edgeone.ai/pages/new?repository-url=https%3A%2F%2Fgithub.com%2Faliosvictor%2Fdongbei-roadbook%2Ftree%2Fgh-pages&project-name=dongbei-roadbook&output-directory=.%2F)

## 内容入口

- `index.qmd`：三套路线的选择规则与总览。
- `primary.qmd`：主行程的每天时间线、摄影与器材安排。
- `option-skip-qiqian.qmd`：不进入奇乾的宽松方案。
- `option-reverse.qmd`：北部秋色明显更早时使用的反向方案。
- `sources.qmd`：天气、道路、景区、边境与无人机核验入口。
- `data/itinerary.json`：完整路线与每日地图控制点。
- `scripts/build_maps.py`：生成总览、每日路线与风险地图。
- `figures/maps/`：网站使用的静态地图图片。
- `requirements.txt`：地图生成脚本的 Python 依赖。

## 本地预览

```bash
quarto preview
```

## 更新地图

```bash
python3 -m pip install -r requirements.txt
python3 scripts/build_maps.py
```

生成静态网站：

```bash
quarto render
```

网页输出位于 `_site/`。推送到 GitHub 的 `main` 分支后，GitHub Actions 会自动渲染并发布到 `gh-pages` 分支。

## 免费发布

1. 使用 GitHub 公共仓库保存源码。
2. 在 GitHub Pages 中发布 `gh-pages` 分支。
3. 可将同一个 `gh-pages` 分支连接到 EdgeOne Pages，作为国内主要访问地址。
4. 使用平台分配的网址，不购买自定义域名。
