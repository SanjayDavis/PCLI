# PCLI — Standalone Ubuntu Package Manager CLI

PackHub is a **self-contained command-line package manager** for Ubuntu that downloads package metadata and `.deb` files directly from official repositories — no `apt` backend required.  
It features **dependency resolution**, **local caching**, and **safe system protection** to prevent overwriting critical packages.

---

## Features
-  Fetches and parses official Ubuntu repository metadata (`Packages.gz`)
-  Search packages by name
-  View detailed package info (version, architecture, dependencies)
-  Install `.deb` packages and auto-resolve dependencies
-  Protects core system packages from accidental modification
-  Caches package metadata for fast, offline lookups
-  Supports progress bars (via `tqdm`)

---

## Installation
Clone the repository and make the script executable:
```bash
git clone https://github.com/<your-username>/packhub.git
cd packhub
chmod +x packhub.py
```

```bash
pip3 install tqdm requests
```

 Usage
Update Package Database:
```bash
python3 packhub.py update
```

Search Packages:
```bash
python3 packhub.py search gcc
```

Show Package Information:
```bash
python3 packhub.py info nmap
```

Install a Package:
```bash
python3 packhub.py install nmap
```

Force Database Update:
```bash
python3 packhub.py update --force
```

## System Safety
PackHub blocks installation or modification of system-critical packages such as:

libc6, dpkg, apt, bash, coreutils, systemd, base-files, etc.
This ensures the tool never corrupts your base system.

## Directory Structure
```bash
~/.cache/packhub/           # Cached package database
./debian_packages/          # Temporary downloaded .deb files
```
