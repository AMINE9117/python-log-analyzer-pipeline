import gzip
import os
import os.path as pt
from pathlib import Path
""" 
in:data
out:list of rows
 """


def ingest(path: str):
    try:
        files = os.listdir(path)
        for file in files:
            file_path = pt.join(path, file)
            openner = gzip.open(file_path, mode='rt', encoding="utf-8") if file.endswith(
                '.gz') else open(file_path)  # operateur térnel
            with openner as f:
                return f.readlines()
    except Exception as e:
        print(e)
        return


if __name__ == "__main__":
    data = ingest('./data')
    if data:
        print(data[:10])
