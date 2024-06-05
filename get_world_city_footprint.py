import os
import sys
import argparse
import warnings

import geopandas as gpd
import osmnx as ox

warnings.filterwarnings("ignore")

city_America = [
    "New York",
    "San Francisco",
    "Los Angeles",
    "Boston",
    "Toronto",
    "Vancouver",
    "Mexico City",
    "Sao Paulo",
    "Buenos Aires",
]
city_Europe = [
    "Amsterdam",
    "Athens",
    "Berlin",
    "Brussels",
    "Hamburg",
    "Istanbul",
    "Lisbon",
    "London",
    "Madrid",
    "Manchester",
    "Milan",
    "Munich",
    "Paris",
    "Rome",
    "Vienna",
    "Delft",
]
city_Eastern_Europe = ["Kiev", "Minsk", "Moscow", "Saint Petersburg", "Warsaw"]
city_Australia = ["Sydney", "Melbourne", "Canberra"]
city_East_Asia = [
    "Singapore",
    "Chennai",
    "Kampala",
    "Hong Kong",
    "Seoul",
    "Osaka",
    "Bangkok",
    "Guangzhou",
    "Shanghai",
    "Tokyo",
    "Beijing",
    "Wuhan",
    "Tianjin",
    "Changsha",
]

cities = {
    "America": city_America,
    "Europe": city_Europe,
    "Eastern_Europe": city_Eastern_Europe,
    "Australia": city_Australia,
    "East_Asia": city_East_Asia,
}


def download_building_footprint(gdf_region):
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


def download_city_footprint():
    for key, cities_list in cities.items():
        for i, city in enumerate(cities_list):
            print(f"{key}({i+1}/{len(cities_list)}):{city}")
            folder = f"./data/bldg/{key}/"
            os.makedirs(folder, exist_ok=True)
            file = folder + f"buildings_{city}.geojson"
            if os.path.exists(file):
                print("file exists:", file)
                continue
            try:
                gdf_building = ox.features_from_place(city, tags={"building": True})
            except KeyboardInterrupt:
                sys.exit()
            except Exception as e:
                print("#" * 10 + f"Error: {city}" + "#" * 10)
                with open("./data/bldg/error.log", "a") as f:
                    f.write("#" * 20 + f"Error: {city}" + "#" * 20 + "\n")
                    f.write(str(e) + "\n")
                continue
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

            gdf_building.to_file(file, driver="GeoJSON")
            print("builidings num:", gdf_building.shape[0])


def check_city_footprint():
    for key, cities_list in cities.items():
        count = 0
        for city in cities_list:
            folder = f"./data/bldg/{key}/"
            os.makedirs(folder, exist_ok=True)
            file = folder + f"buildings_{city}.geojson"
            if not os.path.exists(file):
                # print("deal with:", file)
                continue
            count += 1
        print(f"Finished: {key}: {count}/{len(cities_list)}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", type=str, choices=["download", "check"], default="download"
    )
    args = parser.parse_args()

    if args.mode == "download":
        download_city_footprint()
    elif args.mode == "check":
        check_city_footprint()
