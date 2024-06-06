import os
import sys
import argparse
import warnings
import json
from io import BytesIO

import requests
import numpy as np
import geopandas as gpd
import osmnx as ox
import rasterio
from rasterio.features import geometry_mask
from pyproj import Geod
import folium
from tqdm import tqdm

warnings.filterwarnings("ignore")
geod = Geod(ellps="WGS84")


def download_city_bounds(city, bounds_file):
    try:
        boundings = ox.geocode_to_gdf(city)
        boundings = boundings.to_crs("EPSG:4326")
        boundings.to_file(bounds_file, driver="GeoJSON")
        return boundings
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print("#" * 10 + f"Error@geocode_to_gdf: {city}" + "#" * 10)
        with open("./data/bldg/error.log", "a") as f:
            f.write("#" * 20 + f"Error@geocode_to_gdf: {city}" + "#" * 20 + "\n")
            f.write(str(e) + "\n")
        return None


def download_one_city_building_footprint(city, bounds_gdf, buildings_file):
    try:
        if city == None:
            raise Exception("city is None")
        gdf_building = ox.features_from_place(city, tags={"building": True})
    except KeyboardInterrupt:
        sys.exit()
    except Exception as e:
        print("#" * 10 + f"Error@features_from_place: {city}" + "#" * 10)
        with open("./data/bldg/error.log", "a") as f:
            f.write("#" * 20 + f"Error@features_from_place: {city}" + "#" * 20 + "\n")
            f.write(str(e) + "\n")

        try:
            gdf_building = ox.features_from_polygon(
                bounds_gdf.geometry[0], tags={"building": True}
            )
        except KeyboardInterrupt:
            sys.exit()
        except Exception as e:
            print("#" * 10 + f"Error@features_from_polygon: {city}" + "#" * 10)
            with open("./data/bldg/error.log", "a") as f:
                f.write(
                    "#" * 20 + f"Error@features_from_polygon: {city}" + "#" * 20 + "\n"
                )
                f.write(str(e) + "\n")
            return None

    gdf_building = gdf_building[gdf_building["building"].notnull()]
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

    gdf_building.to_file(buildings_file, driver="GeoJSON")
    print("builidings num:", gdf_building.shape[0])

    return gdf_building


def visualize_city_footprint(bounds_gdf, buildings_gdf, visual_file):
    """
    可视化区域和建筑数据

    Input:
        bounds_gdf: 区域的GeoDataFrame
        buildings_gdf: 区域的建筑数据的GeoDataFrame
    """
    if os.path.exists(visual_file):
        print("visual file exists:", visual_file)
        return
    left, bottom, right, top = bounds_gdf.total_bounds
    lon = (left + right) / 2
    lat = (bottom + top) / 2
    m = folium.Map(location=[lat, lon], zoom_start=12)
    geojson_data = bounds_gdf.to_json()
    folium.GeoJson(
        geojson_data,
        style_function=lambda feature: {
            "color": "red",  # 设置边界颜色为红色
            "fillColor": "none",  # 不填充
            "weight": 2,  # 设置边界线宽度
        },
    ).add_to(m)
    geojson_data = buildings_gdf.to_json()
    folium.GeoJson(
        geojson_data,
        style_function=lambda feature: {
            "color": "blue",  # 设置边界颜色为红色
            "fillColor": "none",  # 不填充
            "weight": 2,  # 设置边界线宽度
        },
    ).add_to(m)
    m.save(visual_file)


def download_worldpop_raster(
    city,
    bounds_gdf,
    buildings_gdf,
    worldpop_file,
    buildings_meta_file,
    save_tif=True,
    chunk_size=1024,
):
    if os.path.exists(buildings_meta_file):
        print("buildings_meta file exists:", buildings_meta_file)
        return
    base_url = "https://worldpop.arcgis.com/arcgis/rest/services/WorldPop_Total_Population_100m/ImageServer/exportImage?f=image&format=tiff&noData=0&"

    try:
        if not os.path.exists(worldpop_file):
            left, bottom, right, top = bounds_gdf.total_bounds
            url = base_url + f"bbox={left},{bottom},{right},{top}"
            response = requests.get(url, stream=True, timeout=100)
            response.raise_for_status()
            if save_tif:
                # with open(
                #     worldpop_file,
                # ) as f:
                #     for chunk in response.iter_content(chunk_size=chunk_size):
                #         f.write(chunk)
                pass
            tiff_data = BytesIO(response.content)
            raster = rasterio.open(tiff_data)
        else:
            print("worldpop file exists:", worldpop_file)
            raster = rasterio.open(worldpop_file)

        height, width = raster.height, raster.width
        raster_transform = raster.transform
        buildings_meta = np.zeros((height, width), dtype=np.float32)
        buildings_gdf["area"] = buildings_gdf["geometry"].apply(
            lambda x: abs(geod.geometry_area_perimeter(x)[0])
        )
        buildings_gdf = buildings_gdf.to_crs(raster.crs)

        for _, building in tqdm(buildings_gdf.iterrows(), total=buildings_gdf.shape[0]):
            geom = [building.geometry]
            mask_ = geometry_mask(
                geom,
                transform=raster_transform,
                invert=True,
                out_shape=(height, width),
            )
            buildings_meta[mask_] += building.area

        buildings_gdf.drop("area", axis=1, inplace=True)
        buildings_gdf = buildings_gdf.to_crs("EPSG:4326")
        print(
            "buildings_meta:",
            buildings_meta.shape,
            buildings_meta.sum(),
            np.mean(buildings_meta),
        )
        np.save(buildings_meta_file, buildings_meta)

    except KeyboardInterrupt:
        sys.exit()
    except Exception as e:
        print("#" * 10 + f"Error@world pop: {city}" + "#" * 10)
        with open("./data/bldg/error.log", "a") as f:
            f.write("#" * 20 + f"Error@world pop: {city}" + "#" * 20 + "\n")
            f.write(str(e) + "\n")


def check_city_footprint(cities):
    for key, cities_list in cities.items():
        count_bounds = 0
        count_buildings = 0
        count_aggs = 0
        for city in cities_list:
            folder = f"./data/bldg/{key}/"
            os.makedirs(folder, exist_ok=True)
            bounds_file = folder + f"bounds_{city}.geojson"
            buildings_file = folder + f"buildings_{city}.geojson"
            buildings_meta_file = folder + f"agg_cell_buildings_area_{city}.npy"

            if os.path.exists(bounds_file):
                count_bounds += 1
            if os.path.exists(buildings_file):
                count_buildings += 1
            if os.path.exists(buildings_meta_file):
                count_aggs += 1
        print(
            f"{key}: bounds({count_bounds}/{len(cities_list)}), buildings({count_buildings}/{len(cities_list)}), aggs({count_aggs}/{len(cities_list)})"
        )


def main():
    cities = json.load(open("./data/bldg/cities.json"))

    for key, cities_list in cities.items():
        for i, city in enumerate(cities_list):
            print(f"{key}({i+1}/{len(cities_list)}):{city}")
            folder = f"./data/bldg/{key}/"
            os.makedirs(folder, exist_ok=True)
            bounds_file = folder + f"bounds_{city}.geojson"

            if not os.path.exists(bounds_file):
                bounds_gdf = download_city_bounds(city, bounds_file)
                if bounds_gdf is None:
                    continue
            else:
                print("bounds file exists:", bounds_file)
                bounds_gdf = gpd.read_file(bounds_file)

            buildings_file = folder + f"buildings_{city}.geojson"

            if not os.path.exists(buildings_file):
                buildings_gdf = download_one_city_building_footprint(
                    city, bounds_gdf, buildings_file
                )
                if buildings_gdf is None:
                    continue
            else:
                print("buildings file exists:", buildings_file)
                buildings_gdf = gpd.read_file(buildings_file)

            visual_file = folder + f"visual_{city}.html"
            visualize_city_footprint(bounds_gdf, buildings_gdf, visual_file)

            worldpop_file = folder + f"worldpop_{city}.tif"
            buildings_meta_file = folder + f"agg_cell_buildings_area_{city}.npy"
            download_worldpop_raster(
                city,
                bounds_gdf,
                buildings_gdf,
                worldpop_file,
                buildings_meta_file,
            )

    check_city_footprint(cities)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", type=str, choices=["download", "check"], default="download"
    )
    args = parser.parse_args()

    if args.mode == "download":
        main()
    elif args.mode == "check":
        check_city_footprint(json.load(open("./data/bldg/cities.json")))
