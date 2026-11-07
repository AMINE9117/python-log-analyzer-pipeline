from ingestion import read
from processing import extract_transform


if __name__ == "__main__":
    rows = read.ingest('./data')
    if rows:
        extract_transform.extract(rows[1])
