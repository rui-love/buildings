import os
import argparse
import subprocess
import warnings
import json

import numpy as np
import pandas as pd
import geopandas as gpd
import folium
import osmnx as ox
import rasterio
from rasterio.mask import mask
from shapely.geometry import Polygon
from pyproj import Geod
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
scaler = StandardScaler()
geod = Geod(ellps="WGS84")


def get_footprint_from_osmnx(gdf_region):
    """
    从OSM中获取建筑物的轮廓

    Input:
        gdf_region: 区域的GeoDataFrame

    Output:
        gdf_building: 建筑物的GeoDataFrame
    """
    tags = {"building": True}
    bounds = gdf_region.total_bounds
    bbox = [bounds[3], bounds[1], bounds[2], bounds[0]]
    gdf_building = ox.features.features_from_bbox(bbox=bbox, tags=tags)
    gdf_building = gdf_building[gdf_building["building"].notnull()]
    print("gdf_building nums:", gdf_building.shape)

    gdf_building = gdf_building[["building", "geometry"]]
    gdf_building = gdf_building.to_crs("EPSG:4326")

    def get_building_type(x):
        if x.geom_type in {"Polygon", "MultiPolygon"}:
            return 1
        return 0

    gdf_building["type"] = gdf_building["geometry"].apply(get_building_type)
    gdf_building = gdf_building[gdf_building["type"] == 1]
    gdf_building = gdf_building.drop("type", axis=1)
    gdf_building = gdf_building.reset_index()

    gdf_building.to_file(f"./data/data_{args.city}/buildings.geojson", driver="GeoJSON")

    return gdf_building


def download_tifs(regions):
    """
    下载CNBH10m的tifs, 用于获取建筑物的高度

    Input:
        regions: 区域的GeoDataFrame

    Output:
        tifs: tif文件的坐标

    File:
        CNBH10m_X{X}Y{Y}.tif
    """
    regions_bounds = regions.total_bounds
    regions_bounds = [
        regions_bounds[0] - 0.5,
        regions_bounds[1] - 0.5,
        regions_bounds[2] + 0.5,
        regions_bounds[3] + 0.5,
    ]
    bounds_int = [int(x) + 1 if int(x) % 2 == 0 else int(x) for x in regions_bounds]
    tifs = np.meshgrid(
        np.arange(bounds_int[0], bounds_int[2] + 1, 2),
        np.arange(bounds_int[1], bounds_int[3] + 1, 2),
    )
    for X, Y in zip(tifs[0].flatten(), tifs[1].flatten()):
        url = (
            f"https://zenodo.org/records/7923866/files/CNBH10m_X{X}Y{Y}.tif?download=1"
        )
        file = f"./data/data_CNBH/CNBH10m_X{X}Y{Y}.tif"
        if not os.path.exists(file):
            subprocess.run(["wget", url, "-O", file], check=True)
    print(f"Downloaded all {len(tifs[0].flatten())} tifs!")

    return tifs


def visualize_region(gdf_region, result_gdf):
    """
    可视化区域和建筑数据

    Input:
        gdf_region: 区域的GeoDataFrame
        result_gdf: 区域的建筑数据的GeoDataFrame
    """
    m = folium.Map(
        location=[
            gdf_region["geometry"][0].centroid.y,
            gdf_region["geometry"][0].centroid.x,
        ],
        zoom_start=10,
    )
    folium.GeoJson(gdf_region, name="geojson").add_to(m)
    folium.GeoJson(
        result_gdf,
        name="geojson",
        style_function=lambda x: {
            "fillColor": "red",
            "color": "red",
            "weight": 2,  # 设置边界线宽度
        },
    ).add_to(m)
    m.save(f"./data/data_{args.city}/visual.html")


def get_CN_building(gdf_region):
    """
    获得区域建筑信息
    """
    gdf_building = get_footprint_from_osmnx(gdf_region)
    tifs = download_tifs(gdf_region)
    gdfs = []
    for X, Y in zip(tifs[0].flatten(), tifs[1].flatten()):
        print(f"loading CNBH10m_X{X}Y{Y}.tif")
        chbn = rasterio.open(f"./data/data_CNBH/CNBH10m_X{X}Y{Y}.tif")
        chbn_polygon = Polygon.from_bounds(*(chbn.bounds))
        footprints = gdf_building.to_crs(chbn.crs)
        gdf = footprints[footprints["geometry"].intersects(chbn_polygon)]
        gdf["height"] = gdf["geometry"].apply(
            lambda x: np.max(np.nan_to_num(mask(chbn, [x], crop=True)[0]))
        )
        gdf["height"] = gdf["height"].astype(float)
        gdfs.append(gdf)
    gdf = pd.concat(gdfs)
    gdf = gdf[gdf["height"] > 0]
    gdf = gdf.to_crs("EPSG:4326")
    gdf = gpd.sjoin(
        gdf, gdf_region[["GEOID", "geometry"]], predicate="within", how="inner"
    )

    visualize_region(gdf_region, gdf)

    gdf["area"] = gdf["geometry"].apply(
        lambda x: abs(geod.geometry_area_perimeter(x)[0])
    )
    result_gdf = gdf[["area", "height", "GEOID"]]

    print("building nums =", result_gdf.shape[0])

    return result_gdf


def get_pop(gdf_region):
    """
    获得人口数据
    """
    world_pop = rasterio.open("./data/data_worldpop/chn_ppp_2020_UNadj.tif")

    def get_pop(x):
        """
        辅助函数，获取区域内的人口数据
        """
        data = mask(world_pop, [x], crop=True)[0]
        return data[data > 0].sum()

    gdf_region["pop_overall"] = gdf_region["geometry"].apply(get_pop)
    return gdf_region


def get_building_feature(gdf_region, result_gdf):
    """
    计算区域统计特征到gdf_region中
    """
    result_gdf["volume"] = result_gdf["area"] * result_gdf["height"]
    result_gdf_agg = (
        result_gdf.groupby("GEOID")
        .agg({"area": ["mean", "sum"], "height": "mean", "volume": "sum"})
        .reset_index()
    )
    result_gdf_agg.columns = ["_".join(col) for col in result_gdf_agg.columns.values]
    result_gdf_agg = result_gdf_agg.rename(columns={"GEOID_": "GEOID"})
    gdf_region = gdf_region.merge(result_gdf_agg, on="GEOID", how="left")
    gdf_region = gdf_region.fillna(0)
    gdf_region["building_density"] = gdf_region["area_sum"] / gdf_region["ALAND"]
    gdf_region["plot_ratio"] = gdf_region["volume_sum"] / gdf_region["ALAND"]
    return gdf_region


def dump_region2info(gdf_region):
    """
    保存数据
    """
    gdf_region_normal = gdf_region[
        [
            "GEOID",
            "ALAND",
            "pop_overall",
            "area_mean",
            "height_mean",
            "building_density",
            "plot_ratio",
        ]
    ]
    gdf_region_normal.iloc[:, 1:] = scaler.fit_transform(gdf_region_normal.iloc[:, 1:])

    region2info = {
        gdf_region["GEOID"].iloc[i]: {
            "ALAND": int(gdf_region["ALAND"].iloc[i]),
            "pop_overall": int(gdf_region["pop_overall"].iloc[i]),
            "area_mean": gdf_region["area_mean"].iloc[i],
            "height_mean": gdf_region["height_mean"].iloc[i],
            "building_density": gdf_region["building_density"].iloc[i],
            "plot_ratio": gdf_region["plot_ratio"].iloc[i],
            "feature": gdf_region_normal.iloc[i, 1:].values.tolist(),
        }
        for i in range(gdf_region_normal.shape[0])
    }

    with open(f"./data/data_{args.city}/region2info_building.json", "w") as f:
        json.dump(region2info, f)

    print("region2info_building.json saved!")


def main(city):
    # 读取区域的GeoDataFrame
    gdf_region = gpd.read_file(f"./data/data_{city}/region.geojson")
    print("gdf_region nums:", gdf_region.shape)

    # 获取区域的人口数据
    gdf_region = get_pop(gdf_region)

    # 获取区域的建筑数据
    result_gdf = get_CN_building(gdf_region)  # 包含可视化代码

    # 计算区域的建筑密度和容积率
    gdf_region = get_building_feature(gdf_region, result_gdf)

    # 保存数据
    dump_region2info(gdf_region)

    return gdf_region


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", type=str, default="bj", choices=["bj", "jn", "sz"])
    args = parser.parse_args()

    os.makedirs(f"./data/data_{args.city}", exist_ok=True)
    assert os.path.exists(
        f"./data/data_{args.city}/region.geojson"
    ), "Request data from the author"

    if not os.path.exists("./data/data_worldpop"):
        os.mkdir("./data/data_worldpop")
        world_pop_dir = "./data/data_worldpop/chn_ppp_2020_UNadj.tif"
        url = "https://data.worldpop.org/GIS/Population/Global_2000_2020/2020/CHN/chn_ppp_2020_UNadj.tif"
        subprocess.run(["wget", url, "-O", world_pop_dir], check=True)

    gdf_region = main(args.city)
