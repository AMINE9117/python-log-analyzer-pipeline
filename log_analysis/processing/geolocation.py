import requests as http

from requests import Response


def geo_location(ip):
    response = http.get("https://ipinfo.io/"+ip+"/json")
    if response.status_code == 200:
        print(response.json())


if __name__ == '__main__':
    print(geo_location("88.147.152.239"))
