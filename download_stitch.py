import urllib.request
import os

screens = {
    "signup.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sX2NiNzhiMmMwZDBjMjQ0OWU5YjliOGM2MDE1NGNiNjMzEgsSBxDb-Iq06AIYAZIBIwoKcHJvamVjdF9pZBIVQhM0MjU0NDU0NTU5NDE5Mzc4NjQ3&filename=&opi=96797242",
    "user_complaints.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sX2VhMTdiZDI3YTBmMjQxN2Q4NDMwZTg3NWIxOTIzNjRlEgsSBxDb-Iq06AIYAZIBIwoKcHJvamVjdF9pZBIVQhM0MjU0NDU0NTU5NDE5Mzc4NjQ3&filename=&opi=96797242",
    "user_tracking.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzNkYWJjY2QwZGE1MzRiZTNiYjE5ZTAwOWJkZTcxYmYxEgsSBxDb-Iq06AIYAZIBIwoKcHJvamVjdF9pZBIVQhM0MjU0NDU0NTU5NDE5Mzc4NjQ3&filename=&opi=96797242",
    "user_profile.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sX2E2ZWUwZWFjYjNkZjQzMDk5YjU4MjFlNzM2NmZjMGQxEgsSBxDb-Iq06AIYAZIBIwoKcHJvamVjdF9pZBIVQhM0MjU0NDU0NTU5NDE5Mzc4NjQ3&filename=&opi=96797242",
    "admin_dashboard.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sX2E3NTU2MDQyZDYxNDRlMTc4MTMzZWI5YmRkMzdlODhhEgsSBxDb-Iq06AIYAZIBIwoKcHJvamVjdF9pZBIVQhM0MjU0NDU0NTU5NDE5Mzc4NjQ3&filename=&opi=96797242",
    "login.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzJjNzUyNzBkOWI3OTRhYzU5NTc0YTFmMmQ1NGM2ZmMyEgsSBxDb-Iq06AIYAZIBIwoKcHJvamVjdF9pZBIVQhM0MjU0NDU0NTU5NDE5Mzc4NjQ3&filename=&opi=96797242",
    "employee_dashboard.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzBlMTI2YWNjZTEwYzQ4ZjdhMGY4YjA1YTU3NmIzZGE5EgsSBxDb-Iq06AIYAZIBIwoKcHJvamVjdF9pZBIVQhM0MjU0NDU0NTU5NDE5Mzc4NjQ3&filename=&opi=96797242",
    "user_files.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzM3NWJjN2QzNjcxYTRmZjNhYTE3ZDczODNiOGVkNjY1EgsSBxDb-Iq06AIYAZIBIwoKcHJvamVjdF9pZBIVQhM0MjU0NDU0NTU5NDE5Mzc4NjQ3&filename=&opi=96797242",
    "user_dashboard.html": "https://contribution.usercontent.google.com/download?c=CgthaWRhX2NvZGVmeBJ7Eh1hcHBfY29tcGFuaW9uX2dlbmVyYXRlZF9maWxlcxpaCiVodG1sXzEwY2EwMzU4MjA2ZDQ2ZWE5NjVlNmRmZDFmM2E3ZTA0EgsSBxDb-Iq06AIYAZIBIwoKcHJvamVjdF9pZBIVQhM0MjU0NDU0NTU5NDE5Mzc4NjQ3&filename=&opi=96797242",
}

for name, url in screens.items():
    path = os.path.join(r"c:\Users\bakki\Music\New folder\jesh\OSN Serpent-Secure-System\templates\mobile", name)
    print(f"Downloading {name}...")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8')
            with open(path, "w", encoding='utf-8') as f:
                f.write(html)
        print(f"Saved {name}")
    except Exception as e:
        print(f"Failed {name}: {e}")
