# Census tract 数据下载

## 重要说明
下载全部census tract还可以使用浏览器插件，Donwload them All! 能够替代本程序。

## 功能说明
下载America Census tract数据, 在当前文件夹下自动生成census_tract_year文件夹，census tract保存在该文件夹下。

如果指定了city, 只下载对应城市数据。

## 使用方式
```python download.py --year 2015 --processes 5```

并发数为5的条件下，下载美国2015年census tract数据

```python download.py --year 2015 --city 36```

下载纽约2015年census tract数据
