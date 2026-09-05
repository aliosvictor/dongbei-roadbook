# 大兴安岭自驾游

这是 2026-09-26 至 2026-10-03 的 Quarto 在线路书。默认的稳健路线从齐齐哈尔出发，经蘑阿公路、阿尔山、莫日格勒河、卡线、根河和五大连池，于 10 月 3 日晚抵达哈尔滨；只有奇乾晨雾被列为必拍且道路、住宿与天气条件全部成立时，才切换到奇乾方案。

在线阅读：<https://aliosvictor.github.io/dongbei-roadbook/>

[![使用 EdgeOne Makers 部署](https://cdnstatic.tencentcs.com/edgeone/pages/deploy.svg)](https://edgeone.ai/pages/new?repository-url=https%3A%2F%2Fgithub.com%2Faliosvictor%2Fdongbei-roadbook%2Ftree%2Fgh-pages&project-name=dongbei-roadbook&output-directory=.%2F)

## 内容入口

- `index.qmd`：两套路线的选择规则与总览。
- `primary.qmd`：奇乾方案的每天时间线、摄影与器材安排。
- `option-skip-qiqian.qmd`：默认稳健方案的完整执行页。
- `sources.qmd`：天气、道路、景区、边境与无人机核验入口。
- `data/itinerary.json`：地点、拍摄点与高德路线核验规格。
- `data/amap-routes.json`：高德路线规划的日期化折线、里程与时间快照。
- `_variables.yml`、`includes/amap-route-links.md`：由同一快照自动生成的网页里程、时间、核验日期和高德链接。
- `scripts/update_amap_routes.py`：重新向高德路线规划核验并生成路线快照、网页指标和链接；若高德忽略或改变途经点顺序，按起终点、距离和经过顺序检查报错。
- `scripts/build_maps.py`：用高德折线和 OpenStreetMap 底图生成总览、每日路线与风险地图。
- `scripts/build_fonts.py`：从随项目分发的原字体重建 WOFF2 子集。
- `scripts/validate_project.py`、`tests/`：路线顺序、坐标变更、地图生成状态、文档引用与回归检查。
- `figures/maps/`：网站使用的 WebP 静态地图图片。
- `assets/fonts/web/`：网站使用的精简中文字体。
- `theme.scss`：关闭主题自带的外部字体请求，使用项目内的 WOFF2 字体。
- `requirements.txt`：地图、字体生成与校验脚本的 Python 依赖。

## 本地预览

```bash
quarto preview
```

## 更新地图

```bash
python3 -m pip install -r requirements.txt
python3 scripts/update_amap_routes.py
python3 scripts/build_maps.py
python3 scripts/build_fonts.py
python3 -B -m unittest discover -s tests -v
python3 -B scripts/validate_project.py
```

地图输出为适合网页加载的 WebP 图片。所有绘制的公路线路来自生成当天的高德推荐路线；原始高德坐标为 GCJ-02，绘图时转换为 WGS84 后叠加到 OpenStreetMap 底图。途经点过多的日期拆成多段高德请求再按共同端点拼接，并逐点检查折线是否实际经过；园内景交或未确认准确入口的支线只显示地点，不绘制虚构线路。

路线校验同时检查实际经过顺序、起终点和坐标版本，绘图保留高德原始分段边界。地图编号仅表示位置，不表示必须进镇。修改路线数据或绘图脚本后重建全部地图；`figures/maps/manifest.json` 记录输入及输出校验值，漏生成时发布检查会失败。修改文字后重建字体；不要手改生成的 HTML、地图、指标或链接。

乌苏浪子湖渔村宾馆使用统一名称搜索链接，湖景蓝点不能充当宾馆停车坐标；未核准的晨拍进出不画线、不计入高德里程。10 月 3 日默认使用温泊路线，黑龙山为确认恢复开放后的独立条件路线；白龙湖须先确认停车点再重算。

生成静态网站：

```bash
quarto render
python3 -B scripts/validate_project.py --site _site
```

网页输出位于 `_site/`。获得发布授权后，将网站内容、数据、生成链接、样式或构建配置推送到 `main`；GitHub Actions 会先运行离线校验与回归测试，渲染并检查 HTML，通过后才发布到 `gh-pages`。仅更新说明文档不触发发布；也可手动触发工作流。CI 不实时请求高德，以免构建时静默改变已审阅路线。

## 免费发布

1. 使用 GitHub 公共仓库保存源码。
2. 在 GitHub Pages 中发布 `gh-pages` 分支。
3. 可将同一个 `gh-pages` 分支连接到 EdgeOne Pages，作为国内主要访问地址。
4. 使用平台分配的网址，不购买自定义域名。
