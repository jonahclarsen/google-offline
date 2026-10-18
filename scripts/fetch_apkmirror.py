"""Resolve APKMirror's normal two-step download flow for a fixed APK page."""
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from curl_cffi import requests


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.append(dict(attrs))


def fetch_apkmirror(url):
    def checked_url(link):
        parsed = urlparse(link)
        if parsed.scheme != "https" or not (parsed.hostname == "apkmirror.com" or (parsed.hostname or "").endswith(".apkmirror.com")):
            raise ValueError("Unexpected download host")
        return link

    with requests.Session(impersonate="chrome") as session:
        response = session.get(checked_url(url), timeout=60)
        response.raise_for_status()
        button = next(link["href"] for link in Links(response.text).links if "downloadButton" in link.get("class", ""))
        response = session.get(checked_url(urljoin(url, button)), timeout=60)
        response.raise_for_status()
        button = next(link["href"] for link in Links(response.text).links if link.get("id") == "download-link")
        response = session.get(checked_url(urljoin(url, button)), timeout=120)
        response.raise_for_status()
        checked_url(response.url)
        data = response.content
        if not data.startswith(b"PK"):
            raise ValueError("APKMirror returned a page instead of an APK")
        return data
