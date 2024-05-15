import urllib.request
from multiprocessing import Pool
import argparse
import os

import pandas as pd


def download_all(file):
    if file.endswith(".zip"):
        print(file)
        urllib.request.urlretrieve(
            f"https://www2.census.gov/geo/tiger/TIGER{args.year}/TRACT/" + file,
            f"census_tract_{args.year}/" + file,
        )


def download_city(year, city):
    print(city)
    urllib.request.urlretrieve(
        f"https://www2.census.gov/geo/tiger/TIGER{year}/TRACT/tl_{year}_{city}_tract.zip",
        f"census_tract_{year}/tl_{year}_{city}_tract.zip",
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--year", "-y", type=int, default=2015, help="Year of the census tract data"
    )
    parser.add_argument(
        "--processes", "-p", type=int, default=5, help="Number of download processes"
    )
    parser.add_argument(
        "--city", "-c", type=int, default=-1, help="download individual city data"
    )
    args = parser.parse_args()

    os.makedirs(f"census_tract_{args.year}/", exist_ok=True)

    if args.city != -1:
        download_city(args.year, args.city)
    else:
        url = f"https://www2.census.gov/geo/tiger/TIGER{args.year}/TRACT/"
        # 读取网页上的文件列表
        df = pd.read_html(url)[0]
        # 5个进程
        pool = Pool(args.processes)
        pool.map(download_all, df["Name"].astype(str))
        pool.close()
        pool.join()
