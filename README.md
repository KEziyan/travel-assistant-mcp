# ✈ AI 旅游规划助手

基于**高德 MCP 服务**的智能旅游行程规划工具。输入目的地城市和出行天数，自动生成包含景点、美食、住宿的完整旅行方案。

## 功能特性

- 🗺 **智能行程规划** — 自动搜索城市景点，使用贪心 TSP 算法优化游览路线
- 🌤 **天气查询** — 获取出行期间天气预报，提供穿衣/出行建议
- 🍽 **美食推荐** — 推荐当地评分高的餐厅
- 🏨 **住宿推荐** — 推荐优质酒店/宾馆
- 🚗 **导航直达** — 每天行程生成高德地图驾车导航链接，一键打车
- 💡 **出行贴士** — 根据天气自动生成防暑、防寒、防雨等建议

## 技术栈

- **后端**: Python / Flask
- **前端**: 原生 HTML + CSS + JavaScript
- **地图服务**: 高德地图 MCP API (`maps_geo`, `maps_text_search`, `maps_around_search`, `maps_search_detail`, `maps_weather`)
- **路线优化**: 贪心 TSP 算法（Haversine 距离）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 获取高德 API Key

前往 [高德开放平台](https://lbs.amap.com/) 注册并创建应用，获取 API Key。

### 3. 启动服务

```bash
python app.py
```

访问 `http://localhost:5000`

### 4. 使用

1. 在页面输入高德 API Key 并点击「测试连接」
2. 输入目的地城市、出行日期、天数和每天景点数
3. 点击「生成旅行方案」

## 项目结构

```
├── app.py              # Flask 主应用，路由 & API 接口
├── amap_client.py      # 高德 MCP 客户端封装 + TSP 算法
├── requirements.txt    # Python 依赖
├── templates/
│   └── index.html      # 前端页面
├── static/
│   └── bg.jpg          # 背景图片
└── opencode.json       # opencode MCP 配置
```
