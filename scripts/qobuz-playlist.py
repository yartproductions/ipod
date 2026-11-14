#!/usr/bin/env python3
"""Retrieve playlist metadata using an authorized Qobuz application."""
import argparse
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ENDPOINT = "https://www.qobuz.com/api.json/0.2/playlist/get"
HOSTS = {"qobuz.com", "www.qobuz.com", "open.qobuz.com", "play.qobuz.com"}


def playlist_id(value):
    if re.fullmatch(r"[0-9]+", value):
        return value
    url = urlsplit(value)
    match = re.search(r"/playlist/([0-9]+)/?$", url.path)
    if url.scheme == "https" and url.hostname in HOSTS and match:
        return match[1]
    raise ValueError("Enter a Qobuz playlist URL or numeric playlist ID.")


def get_page(identifier, offset, app_id, token):
    query = urlencode({
        "playlist_id": identifier, "extra": "tracks", "limit": 500,
        "offset": offset, "app_id": app_id,
    })
    headers = {"X-User-Auth-Token": token} if token else {}
    with urlopen(Request(f"{ENDPOINT}?{query}", headers=headers), timeout=30) as response:
        return json.load(response)


def extract(identifier, get_page):
    tracks = []
    while True:
        page = get_page(len(tracks))
        if not isinstance(page, dict) or page.get("status") == "error":
            raise ValueError("Qobuz did not return a playlist.")
        collection = page.get("tracks")
        if not isinstance(collection, dict) or not isinstance(collection.get("items"), list):
            raise ValueError("Qobuz did not return playlist tracks.")
        items = collection["items"]
        total = collection.get("total", page.get("tracks_count"))
        if type(total) is not int or total < 0:
            raise ValueError("Qobuz did not return a valid track count.")
        if collection.get("offset", len(tracks)) != len(tracks):
            raise ValueError("Qobuz returned an unexpected playlist page.")
        if not tracks:
            name = page.get("name") or "Qobuz Playlist"
        tracks.extend(items)
        if len(tracks) == total:
            break
        if not items or len(tracks) > total:
            raise ValueError("Qobuz returned an incomplete or changing playlist.")
    metadata = []
    for row in tracks:
        track = row.get("track", row) if isinstance(row, dict) else None
        if not isinstance(track, dict):
            raise ValueError("Qobuz returned an invalid track.")
        album = track.get("album")
        performer = track.get("performer") or track.get("artist")
        metadata.append({
            "title": track.get("title"),
            "artist": performer.get("name") if isinstance(performer, dict) else performer,
            "album": album.get("title") if isinstance(album, dict) else album,
            "version": track.get("version"),
            "duration": track.get("duration"),
            "isrc": track.get("isrc"),
        })
    return {
        "name": name,
        "provider": "Qobuz",
        "source": f"https://open.qobuz.com/playlist/{identifier}",
        "tracks": {"total": len(tracks), "offset": 0, "items": metadata},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("playlist", help="Qobuz playlist URL or ID")
    args = parser.parse_args()
    app_id = os.environ.get("QOBUZ_APP_ID")
    if not app_id:
        parser.error("Set QOBUZ_APP_ID to your authorized Qobuz application ID.")
    token = os.environ.get("QOBUZ_USER_AUTH_TOKEN")
    try:
        identifier = playlist_id(args.playlist)
        playlist = extract(identifier, lambda offset: get_page(identifier, offset, app_id, token))
    except HTTPError as error:
        parser.exit(1, f"Qobuz returned HTTP {error.code}. Check playlist access and API credentials.\n")
    except (URLError, ValueError, TimeoutError):
        parser.exit(1, "Qobuz playlist retrieval failed. Check the link and try again.\n")
    json.dump(playlist, sys.stdout, ensure_ascii=True)
    print()


if __name__ == "__main__":
    main()
