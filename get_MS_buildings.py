# env: windows, elec
import json
import os
import subprocess
import argparse
import warnings
import urllib.request

from shapely.geometry import shape
import pandas as pd
import geopandas as gpd
import mercantile
import folium
from pyproj import Geod
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")
scaler = StandardScaler()
geod = Geod(ellps="WGS84")


def download_city(state_id, year):
    """
    Download the census tract data for a city, given the state_id, year
    """
    print("downloading census tract data, state id =", state_id)
    os.makedirs(f"data/data_census_tract/census_tract_{year}", exist_ok=True)
    urllib.request.urlretrieve(
        f"https://www2.census.gov/geo/tiger/TIGER{year}/TRACT/tl_{year}_{state_id}_tract.zip",
        f"data/data_census_tract/census_tract_{year}/tl_{year}_{state_id}_tract.zip",
    )


def get_gdf_region(city):
    # 获取区域的geojson数据
    area_id = json.load(open(f"./data/data_{city}/regs.json"))
    state_id = set([a[:2] for a in area_id])
    df_list = []
    for idx in state_id:
        census_tract_path = f"data/data_census_tract/census_tract_{args.year}/tl_{args.year}_{idx}_tract.zip"
        if not os.path.exists(census_tract_path):
            download_city(idx, args.year)
        df = gpd.read_file(census_tract_path)
        df_list.append(df)
    df = pd.concat(df_list, ignore_index=True)
    df = df[df["GEOID"].isin(area_id)].reset_index(drop=True)
    df = df[["GEOID", "ALAND", "INTPTLAT", "INTPTLON", "geometry"]]
    df = df.to_crs("EPSG:4326")

    return df


def get_statistics(gdf_region):
    population = pd.read_csv(
        "./data/data_census_gov/ACSST5Y2016.S0101-Data.csv", header=1
    )
    population["Geography"] = population["Geography"].apply(lambda x: x[9:])
    population = population.iloc[:, [0, 2, 146]]
    population.columns = ["GEOID", "pop_overall", "population_over18"]
    # 将population_over18中的-替换为80% population_overall
    population["population_over18"] = population.apply(
        lambda x: (
            x["pop_overall"] * 0.8
            if x["population_over18"] == "-"
            else x["population_over18"]
        ),
        axis=1,
    )
    gdf_region = gdf_region.merge(population, on="GEOID", how="left")

    employment = pd.read_csv(
        "./data/data_census_gov/ACSST5Y2016.S2401-Data.csv", header=1
    )
    employment["Geography"] = employment["Geography"].apply(lambda x: x[9:])
    employment = employment.iloc[:, [0, 2]]
    employment.columns = ["GEOID", "pop_employment"]
    gdf_region = gdf_region.merge(employment, on="GEOID", how="left")

    return gdf_region


def visualize_region(gdf_region, result_gdf):
    m = folium.Map(location=[gdf_region["INTPTLAT"][0], gdf_region["INTPTLON"][0]])
    geojson_data = gdf_region.to_json()
    folium.GeoJson(
        geojson_data,
        style_function=lambda feature: {
            "color": "red",  # 设置边界颜色为红色
            "fillColor": "none",  # 不填充
            "weight": 2,  # 设置边界线宽度
        },
    ).add_to(m)
    geojson_data = result_gdf.to_json()
    folium.GeoJson(
        geojson_data,
        style_function=lambda feature: {
            "color": "blue",  # 设置边界颜色为红色
            "fillColor": "none",  # 不填充
            "weight": 2,  # 设置边界线宽度
        },
    ).add_to(m)
    m.save(f"./data/data_{args.city}/visual.html")


def get_nyc_building(gdf_region):
    if not os.path.exists("./data/data_nyc/building.geojson"):
        subprocess.run(
            [
                "wget",
                "https://data.cityofnewyork.us/api/geospatial/nqwf-w8eh?method=export&format=GeoJSON",
                "-O",
                "./data/data_nyc/building.geojson",
            ]
        )

    building_json = json.load(open("./data/data_nyc/building.geojson", "r"))
    print("building json file data loaded!")
    gdf_building = pd.DataFrame(building_json["features"])
    gdf_building["geometry"] = gdf_building["geometry"].apply(shape)
    gdf_building = gpd.GeoDataFrame(gdf_building, crs="4326")
    gdf_building["type"] = gdf_building["properties"].apply(lambda x: x["feat_code"])
    gdf_building = gdf_building[gdf_building["type"] == "2100"]
    result_gdf = gpd.sjoin(gdf_building, gdf_region, predicate="within", how="inner")

    visualize_region(gdf_region, result_gdf)

    result_gdf["area"] = result_gdf["geometry"].apply(
        lambda x: abs(geod.geometry_area_perimeter(x)[0])
    )
    result_gdf["height"] = result_gdf["properties"].apply(lambda x: x["heightroof"])
    result_gdf["height"] = result_gdf["height"].fillna(0)
    result_gdf["height"] = result_gdf["height"].astype(float) * 0.3048
    result_gdf = result_gdf[["area", "height", "GEOID"]]
    print("building nums =", result_gdf.shape[0])

    return result_gdf


def get_MS_building(gdf_region):
    min_lon, min_lat, max_lon, max_lat = gdf_region["geometry"].total_bounds
    tiles = list(mercantile.tiles(min_lon, min_lat, max_lon, max_lat, zooms=9))
    quad_keys = list(set([int(mercantile.quadkey(tile)) for tile in tiles]))
    print("quad_keys:", quad_keys)
    # Download the data
    df = pd.read_csv(
        "https://minedbuildings.blob.core.windows.net/global-buildings/dataset-links.csv"
    )
    print("df url loaded!")
    df_list = []

    for _, row in df.iterrows():
        if int(row.QuadKey) in quad_keys:
            url = row["Url"]
            df = pd.read_json(url, lines=True)
            print(f"get {int(row.QuadKey)} finished!")
            df_list.append(df)

    df = pd.concat(df_list, ignore_index=True)
    df["geometry"] = df["geometry"].apply(shape)
    gdf_building = gpd.GeoDataFrame(df, crs="4326")
    result_gdf = gpd.sjoin(gdf_building, gdf_region, predicate="within", how="inner")

    visualize_region(gdf_region, result_gdf)

    result_gdf["area"] = result_gdf["geometry"].apply(
        lambda x: abs(geod.geometry_area_perimeter(x)[0])
    )
    result_gdf["height"] = result_gdf["properties"].apply(lambda x: x["height"])
    result_gdf = result_gdf[["area", "height", "GEOID"]]
    print("building nums =", result_gdf.shape[0])

    return result_gdf


def get_building_feature(gdf_region, result_gdf):
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
    gdf_region_normal = gdf_region[
        [
            "GEOID",
            "ALAND",
            "pop_overall",
            "population_over18",
            "pop_employment",
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
            "population_over18": gdf_region["population_over18"].iloc[i],
            "pop_employment": int(gdf_region["pop_employment"].iloc[i]),
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
    # 获取区域的geojson数据
    gdf_region = get_gdf_region(city)

    # 获取区域的统计数据，也就是人口等数据
    gdf_region = get_statistics(gdf_region)

    # 获取区域的建筑数据
    if city == "nyc":
        result_gdf = get_nyc_building(gdf_region)  # 包含可视化程序
    else:
        result_gdf = get_MS_building(gdf_region)  # 包含可视化程序

    # 计算区域的建筑密度和容积率
    gdf_region = get_building_feature(gdf_region, result_gdf)

    # 保存数据
    dump_region2info(gdf_region)

    return gdf_region


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", type=str, default="nyc", choices=["DC", "BM", "nyc"])
    parser.add_argument(
        "--year", "-y", type=int, default=2015, help="Year of the census tract data"
    )
    args = parser.parse_args()

    gdf_region = main(args.city)
