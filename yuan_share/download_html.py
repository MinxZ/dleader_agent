import requests


def download_patent_html(patent_id, output_file):
    url = f"https://patents.google.com/patent/{patent_id}/en"
    response = requests.get(url, timeout=10)
    response.raise_for_status()  # 如果失败会抛出异常
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(response.text)
    print(f"Downloaded {patent_id} to {output_file}")


if __name__ == "__main__":
    patent_id = "EP2321414B1"
    output_file = f"{patent_id}.html"
    download_patent_html(patent_id, output_file)
