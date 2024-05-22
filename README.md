# buildings
Deal with building features.

## get_buildings.py
运行
```
python get_MS_buildings.py --city nyc
```
获得`region2info_building.json`, 格式为:
```
{
    'tract_id': {
        指标1：真实值,
        指标2：真实值,
        ...
        指标n：真实值,
        feature: [真实值标准归一化后的结果, n个值]
    }
}
```
其中，后续程序运行过程中只用到feature，指标数和feature长度不匹配也没问题，指标只用来让人看

获得`visual.html`, 用红线标注census tract，用蓝线标注建筑轮廓

### 数据
github只上传了必要的数据: 
1. census tract gov上下载的城市特征统计数据
2. 城市的census tract id; 

其他如: 
1. census tract的geojson地理信息, 
2. New York buildings数据
 
程序中会自动下载

## get_CN_buildings.py
获得中国的建筑输入信息
首先要设置端口号，梯子的设置中有相关信息
```
set http_proxy=http://127.0.0.1:1024
set https_proxy=http://127.0.0.1:1024
```
