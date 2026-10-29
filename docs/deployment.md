# 零成本公开部署

## 目标架构

`GitHub -> Streamlit Community Cloud -> Neon PostgreSQL`

公开环境只加载 `data/demo/` 中的完整代表性周，不加载 208 MB 原始 CSV。

## 1. GitHub

1. 在 GitHub 创建公开仓库 `metropt3-maintenance-analytics`。
2. 设置远程并推送 `main` 分支。
3. 确认仓库中不存在 `data/raw/`、`.streamlit/secrets.toml`、数据库 dump 或明文连接串。

## 2. Neon

1. 创建一个免费 PostgreSQL 项目。
2. 从连接详情复制带 `sslmode=require` 的连接串。
3. 将连接串仅保存到本机环境变量 `DEMO_DATABASE_URL`。
4. 在仓库根目录执行：

```powershell
py scripts/load_demo_db.py --dsn $env:DEMO_DATABASE_URL --confirm-reset
```

该命令只会向专用 Demo 数据库写入 `data/demo/` 中的代表性周，并在结束时校验行数与 E03。

## 3. Streamlit Community Cloud

1. 从公开 GitHub 仓库创建应用。
2. 入口文件设置为 `app.py`。
3. Python 版本选择 3.13。
4. 在 Secrets 中写入 `DATABASE_URL` 和 `METROPT_DEMO_MODE = "true"`。
5. 部署后检查首页提示、E03、事件追溯和周报下载。

## 4. 更新 README

将 `README.md` 的部署说明链接替换为 Streamlit 提供的公开 URL，并确认未登录用户可以访问。

## 5. 安全检查

- Neon 密码只存在于 Streamlit Secrets。
- `.streamlit/secrets.toml` 未被 Git 跟踪。
- 原始 CSV 未被 Git 跟踪。
- 公开 Demo 固定为一个完整周，并显示代表性子集提示。
