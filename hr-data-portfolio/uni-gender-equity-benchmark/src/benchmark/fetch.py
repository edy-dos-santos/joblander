"""Download the WGEA public data files and cut a small higher-education extract.

The national files are large (about 170 MB zipped, over 1 GB unzipped), so only
the rows for ANZSIC class 'Higher Education' are kept and committed to the repo.
Column names changed between the 2022-23 file and later years; they are
harmonised here so every later step sees one schema.

Usage:  python -m benchmark.fetch [--cache DIR]
"""
import argparse
import io
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from . import config as c

RENAME_2023 = {"primary_abn": "employer_abn", "primary_employer_name": "employer_name",
               "primary_class_name": "anzsic_class", "submission_group_size": "employer_size"}
KEEP = ["reporting_year", "employer_abn", "employer_name", "employer_size"]
DIMS = {"composition": ["manager_category", "occupation", "employment_status", "employment_type", "gender"],
        "management_statistics": ["movement_type", "manager_category", "manager_type", "employment_status",
                                  "employment_type", "gender"]}


def download(url, cache):
    path = cache / url.rsplit("/", 1)[-1]
    if not path.exists():
        print(f"  downloading {path.name}")
        urllib.request.urlretrieve(url, path)
    return path


def read_member(zf, keyword):
    name = next(n for n in zf.namelist() if f"workforce_{keyword}" in n and n.endswith(".csv"))
    with zf.open(name) as fh:
        return pd.read_csv(io.TextIOWrapper(fh, encoding="utf-8-sig"), low_memory=False)


def harmonise(df, kind):
    df = df.rename(columns=RENAME_2023)
    df = df[df["anzsic_class"] == c.INDUSTRY_CLASS].copy()
    df["employer_abn"] = df["employer_abn"].astype("int64")
    df["employer_name"] = df["employer_name"].str.strip()
    df["employer_size"] = df["employer_size"].str.replace(" employees", "").str.replace(" ", "")
    # 'Manager' / 'Managers' and 'Non-manager' / 'Non-managers' are used interchangeably across files.
    df["manager_category"] = df["manager_category"].str.replace(r"s$", "", regex=True)
    if "movement_type" in df:
        df["movement_type"] = df["movement_type"].replace(
            {"Promtions from non-manager to manager": "Promotions from non-manager to manager"})
    cols = KEEP + DIMS[kind]
    return df.groupby(cols, as_index=False, dropna=False)["n_employees"].sum()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(c.ROOT / "data" / "cache"), help="where to keep the downloaded zips")
    cache = Path(ap.parse_args().cache)
    cache.mkdir(parents=True, exist_ok=True)
    comp, move = [], []
    for year, url in c.SOURCES.items():
        print(year)
        with zipfile.ZipFile(download(url, cache)) as zf:
            comp.append(harmonise(read_member(zf, "composition"), "composition"))
            move.append(harmonise(read_member(zf, "management_statistics"), "management_statistics"))
    c.EXTRACT.mkdir(parents=True, exist_ok=True)
    pd.concat(comp).to_csv(c.COMPOSITION, index=False)
    pd.concat(move).to_csv(c.MOVEMENTS, index=False)
    print(f"Wrote {sum(map(len, comp)):,} composition rows and {sum(map(len, move)):,} movement rows to data/extract/")


if __name__ == "__main__":
    main()
