# 窑温判批

陶瓷厂烧成质检员可用本地工作台处理烧成单，复查连续保温段并与独立清单逐笔核对。

线性插值定位达温和掉温时刻，缺测跨距切断连续保温，按最长连续段判批。同一烧成单可按分区、按主备探头分别报送温程：各区取共同连续达温的最长时段判批，主备交接须有两支探头同刻读数作证，否则交接两侧不拼接，掉温不会被当成连续保温。跨区或交接的单共同保温不足、与外部账不符时进入「待补证」，复核不能确认。旧版单探头烧成单照常复算。

## 启动

```sh
docker compose up --build
```

打开 http://127.0.0.1:18300 并运行随附样例。可以在「导入来源与外部账」上传自己的 CSV，也可以编辑表单中的样例。数据保存于 Compose 卷 `ledger`。使用 `APP_PORT` 可覆盖宿主端口。

## 工作步骤

1. 检查「温程采信」与「测点契约」，定位导入坏行与字段归一结果。
2. 在「异常窑单」区分冲突、业务拒绝、重传与旧版本。
3. 打开「保温判批」并点击任意记录的「查看依据」。
4. 在「窑批勾稽」检查金额或用量差异。通过「烧成批次」复算原文件，通过「签批证据」提交意见并下载证据。

接口定义见 `/openapi.json`。字段、允许区间及算例见 [数据字典](docs/DATA-DICTIONARY.md)，模块和回归测试见 [测试登记](docs/DEPTH.md)。

## 验证

```sh
docker compose config --quiet
docker compose exec -T app pytest -q
```

`sample_data/shift.csv` 是班次数据，`sample_data/external.csv` 是独立账样例。`sample_data/zones.csv` 与 `sample_data/zones_external.csv` 是分区主备样例，覆盖续算、无旁证、判断矛盾、共同达温与账差。`cases.csv` 固定业务反例，`legacy.csv` 和 `truncated.csv` 用于验证历史格式与断行。
