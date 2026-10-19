#!/usr/bin/env python3
"""Keep at most one previous iOS artifact before uploading the next one."""
import json
import os
import urllib.request


def request(path, method='GET'):
    req = urllib.request.Request('https://api.github.com/' + path, method=method,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28'})
    with urllib.request.urlopen(req, timeout=20) as response:
        body = response.read()
        return json.loads(body) if body else None


repo = os.environ['GITHUB_REPOSITORY']
items, page = [], 1
while True:
    batch = request(f'repos/{repo}/actions/artifacts?per_page=100&page={page}')['artifacts']
    items.extend(row for row in batch if row['name'] == 'ios-unsigned' and not row['expired'])
    if len(batch) < 100:
        break
    page += 1
items.sort(key=lambda row: row['created_at'], reverse=True)
for row in items[1:]:
    request(f'repos/{repo}/actions/artifacts/{row["id"]}', method='DELETE')
print('iOS artifact retention maintained; next upload keeps at most two versions.')
