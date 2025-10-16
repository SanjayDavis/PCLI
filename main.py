#!/usr/bin/env python3

"""
PackHub Standalone CLI - No Backend Required
Downloads package metadata directly from Ubuntu repositories
and performs local installation with dependency resolution
"""

import os
import sys
import subprocess
import requests
import gzip
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass

# Try to import tqdm for progress bars
try:
    from tqdm import tqdm
    HAVE_TQDM = True
except ImportError:
    HAVE_TQDM = False
    print("Install tqdm for progress bars: pip3 install tqdm")

# Configuration
UBUNTU_VERSION = "noble"  # Change to jammy, focal, etc. as needed
CACHE_DIR = Path.home() / ".cache" / "packhub"
DOWNLOAD_DIR = Path("debian_packages")
PACKAGES_CACHE = CACHE_DIR / f"packages_{UBUNTU_VERSION}.db"

# Ubuntu Repository URLs
REPOS = [
    f"http://archive.ubuntu.com/ubuntu/dists/{UBUNTU_VERSION}/main/binary-amd64/Packages.gz",
    f"http://archive.ubuntu.com/ubuntu/dists/{UBUNTU_VERSION}/universe/binary-amd64/Packages.gz"
]

# ANSI Colors
BLUE = '\033[94m'
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BOLD = '\033[1m'
RESET = '\033[0m'

# System-critical packages
FORBIDDEN_PACKAGES = {
    'libc6', 'libc-bin', 'libgcc-s1', 'dpkg', 'apt', 'bash',
    'coreutils', 'systemd', 'init', 'base-files', 'ubuntu-minimal'
}


@dataclass
class Package:
    """Package information"""
    name: str
    version: str
    architecture: str
    filename: str
    depends: List[Tuple[str, str]] = None  # [(dep_name, version_constraint), ...]
    
    def __post_init__(self):
        if self.depends is None:
            self.depends = []


@dataclass
class InstalledPackage:
    """Installed package information"""
    name: str
    version: str
    architecture: str


class PackageDatabase:
    """Local package database"""
    
    def __init__(self):
        self.packages: Dict[str, Package] = {}
        self.last_update = None
        
    def needs_update(self) -> bool:
        """Check if database needs updating"""
        if not PACKAGES_CACHE.exists():
            return True
        
        # Update if cache is older than 24 hours
        cache_time = PACKAGES_CACHE.stat().st_mtime
        current_time = time.time()
        age_hours = (current_time - cache_time) / 3600
        
        return age_hours > 24
    
    def update(self, force=False):
        """Download and parse package metadata"""
        if not force and not self.needs_update():
            print(f"{GREEN}Package database is up to date{RESET}")
            self.load_from_cache()
            return
        
        print(f"{BLUE}Updating package database from Ubuntu {UBUNTU_VERSION}...{RESET}")
        
        all_packages = {}
        
        for repo_url in REPOS:
            repo_name = "main" if "main" in repo_url else "universe"
            print(f"\n{BLUE}Downloading {repo_name} repository...{RESET}")
            
            try:
                start_time = time.time()
                response = requests.get(repo_url, stream=True)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                
                # Download with progress
                compressed_data = b''
                if HAVE_TQDM and total_size > 0:
                    with tqdm(total=total_size, unit='B', unit_scale=True, desc=f"  {repo_name}") as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            compressed_data += chunk
                            pbar.update(len(chunk))
                else:
                    for chunk in response.iter_content(chunk_size=8192):
                        compressed_data += chunk
                
                download_time = time.time() - start_time
                print(f"  {GREEN}Downloaded in {download_time:.2f}s{RESET}")
                
                # Decompress and parse
                print(f"  {BLUE}Parsing packages...{RESET}")
                parse_start = time.time()
                decompressed = gzip.decompress(compressed_data).decode('utf-8')
                packages = self._parse_packages(decompressed)
                parse_time = time.time() - parse_start
                
                print(f"  {GREEN}Parsed {len(packages)} packages in {parse_time:.2f}s{RESET}")
                
                all_packages.update(packages)
                
            except Exception as e:
                print(f"  {RED}Error downloading {repo_name}: {e}{RESET}")
                continue
        
        self.packages = all_packages
        self._save_to_cache()
        
        print(f"\n{GREEN}✓ Database updated: {len(self.packages)} packages available{RESET}")
    
    def _parse_packages(self, content: str) -> Dict[str, Package]:
        """Parse Packages file format"""
        packages = {}
        
        entries = content.split('\n\n')
        for entry in entries:
            if not entry.strip():
                continue
            
            pkg_data = {}
            lines = entry.split('\n')
            
            for line in lines:
                if not line or not ':' in line:
                    continue
                
                key, value = line.split(':', 1)
                pkg_data[key.strip()] = value.strip()
            
            if 'Package' not in pkg_data:
                continue
            
            # Parse dependencies
            depends = []
            if 'Depends' in pkg_data:
                deps = pkg_data['Depends'].split(',')
                for dep in deps:
                    dep = dep.strip()
                    match = re.match(r'^([^\s(]+)(?:\s*\(([^)]+)\))?', dep)
                    if match:
                        dep_name = match.group(1)
                        version_constraint = match.group(2) or ''
                        depends.append((dep_name, version_constraint))
            
            pkg = Package(
                name=pkg_data['Package'],
                version=pkg_data.get('Version', ''),
                architecture=pkg_data.get('Architecture', 'amd64'),
                filename=pkg_data.get('Filename', ''),
                depends=depends
            )
            
            packages[pkg.name] = pkg
        
        return packages
    
    def _save_to_cache(self):
        """Save database to cache file"""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        import pickle
        with open(PACKAGES_CACHE, 'wb') as f:
            pickle.dump(self.packages, f)
        
        print(f"{GREEN}Cache saved to {PACKAGES_CACHE}{RESET}")
    
    def load_from_cache(self):
        """Load database from cache"""
        if not PACKAGES_CACHE.exists():
            return False
        
        try:
            import pickle
            with open(PACKAGES_CACHE, 'rb') as f:
                self.packages = pickle.load(f)
            
            cache_age = (time.time() - PACKAGES_CACHE.stat().st_mtime) / 3600
            print(f"{GREEN}Loaded {len(self.packages)} packages from cache (age: {cache_age:.1f}h){RESET}")
            return True
        except Exception as e:
            print(f"{YELLOW}Warning: Could not load cache: {e}{RESET}")
            return False
    
    def search(self, query: str) -> List[Package]:
        """Search packages by name"""
        query = query.lower()
        results = []
        
        for pkg in self.packages.values():
            if query in pkg.name.lower():
                results.append(pkg)
        
        # Sort by relevance
        results.sort(key=lambda p: (
            0 if p.name.lower() == query else
            1 if p.name.lower().startswith(query) else
            2
        ))
        
        return results
    
    def get_package(self, name: str) -> Optional[Package]:
        """Get package by exact name"""
        return self.packages.get(name)


class SystemPackageManager:
    """Manages installed system packages"""
    
    @staticmethod
    def get_installed_packages() -> Dict[str, InstalledPackage]:
        """Get all installed packages"""
        installed = {}
        try:
            result = subprocess.run(
                ['dpkg-query', '-W', '-f=${Package}|${Version}|${Architecture}\n'],
                capture_output=True,
                text=True,
                check=True
            )
            
            for line in result.stdout.strip().split('\n'):
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 3:
                        name, version, arch = parts[0], parts[1], parts[2]
                        installed[name] = InstalledPackage(name, version, arch)
        except:
            pass
        
        return installed
    
    @staticmethod
    def parse_version(version_str: str) -> tuple:
        """Parse version string for comparison"""
        if ':' in version_str:
            version_str = version_str.split(':', 1)[1]
        
        parts = re.split(r'[.-]', version_str)
        numeric_parts = []
        
        for part in parts:
            try:
                numeric_parts.append(int(part))
            except ValueError:
                numeric_parts.append(part)
        
        return tuple(numeric_parts)


class PackageInstaller:
    """Package installation manager"""
    
    def __init__(self, db: PackageDatabase):
        self.db = db
        self.installed = SystemPackageManager.get_installed_packages()
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    def search(self, query: str):
        """Search and display packages"""
        results = self.db.search(query)
        
        if results:
            print(f"\n{BOLD}Found {len(results)} package(s):{RESET}")
            for pkg in results[:20]:
                installed = f"{GREEN}[installed]{RESET} " if pkg.name in self.installed else ""
                forbidden = f"{RED}[blocked]{RESET} " if pkg.name in FORBIDDEN_PACKAGES else ""
                print(f"\n{forbidden}{installed}{BOLD}{pkg.name}{RESET} - {pkg.version}")
                print(f"  Arch: {pkg.architecture}")
            
            if len(results) > 20:
                print(f"\n...and {len(results) - 20} more")
        else:
            print(f"{RED}No packages found matching '{query}'{RESET}")
    
    def info(self, name: str):
        """Show package information"""
        pkg = self.db.get_package(name)
        
        if not pkg:
            print(f"{RED}Package '{name}' not found{RESET}")
            return
        
        print(f"\n{'='*70}")
        print(f"Package: {name}")
        print(f"{'='*70}\n")
        
        if name in FORBIDDEN_PACKAGES:
            print(f"{RED}BLOCKED: System-critical package{RESET}\n")
        
        if name in self.installed:
            installed_pkg = self.installed[name]
            print(f"{GREEN}Status: Installed{RESET}")
            print(f"Installed Version: {installed_pkg.version}")
        
        print(f"Available Version: {pkg.version}")
        print(f"Architecture: {pkg.architecture}")
        print(f"Filename: {pkg.filename}\n")
        
        if pkg.depends:
            print(f"Dependencies ({len(pkg.depends)}):")
            for dep_name, constraint in pkg.depends[:10]:
                status = f"{GREEN}✓{RESET}" if dep_name in self.installed else f"{RED}✗{RESET}"
                print(f"  {status} {dep_name} {constraint}")
            
            if len(pkg.depends) > 10:
                print(f"  ... and {len(pkg.depends) - 10} more")
    
    def install(self, name: str):
        """Install package with dependencies"""
        if name in FORBIDDEN_PACKAGES:
            print(f"{RED}Error: '{name}' is a protected system package{RESET}")
            return False
        
        pkg = self.db.get_package(name)
        if not pkg:
            print(f"{RED}Package '{name}' not found{RESET}")
            return False
        
        if name in self.installed:
            print(f"{YELLOW}'{name}' is already installed{RESET}")
            print(f"Installed version: {self.installed[name].version}")
            response = input("Reinstall anyway? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                return True
        
        # Resolve dependencies
        print(f"\n{BLUE}Analyzing dependencies for {name}...{RESET}")
        deps_to_install = self._resolve_dependencies(name)
        
        if deps_to_install:
            print(f"\n{YELLOW}Need to install {len(deps_to_install)} dependencies:{RESET}")
            for dep in deps_to_install:
                print(f"  - {dep}")
            
            response = input(f"\nContinue with installation? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                print("Installation cancelled")
                return False
            
            # Install dependencies
            print(f"\n{BLUE}Installing dependencies...{RESET}")
            for dep_name in deps_to_install:
                print(f"\n{BLUE}→ Installing dependency: {dep_name}{RESET}")
                if not self._install_single(dep_name):
                    print(f"{YELLOW}Warning: Failed to install {dep_name}{RESET}")
        else:
            print(f"{GREEN}All dependencies satisfied{RESET}")
            response = input(f"\nInstall {name} ({pkg.version})? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                return False
        
        # Install main package
        print(f"\n{BLUE}→ Installing main package: {name}{RESET}")
        return self._install_single(name)
    
    def _resolve_dependencies(self, name: str, visited: Optional[Set[str]] = None) -> List[str]:
        """Recursively resolve dependencies"""
        if visited is None:
            visited = set()
        
        if name in visited:
            return []
        
        visited.add(name)
        to_install = []
        
        pkg = self.db.get_package(name)
        if not pkg:
            return []
        
        for dep_name, constraint in pkg.depends:
            if dep_name in FORBIDDEN_PACKAGES:
                continue
            
            if dep_name in self.installed:
                continue
            
            # Check if t64 version exists
            if dep_name + 't64' in self.installed:
                print(f"  {GREEN}✓ Using {dep_name}t64 (system){RESET}")
                continue
            
            # Recursively resolve
            sub_deps = self._resolve_dependencies(dep_name, visited)
            for sub_dep in sub_deps:
                if sub_dep not in to_install:
                    to_install.append(sub_dep)
            
            if dep_name not in to_install:
                to_install.append(dep_name)
        
        return to_install
    
    def _install_single(self, name: str) -> bool:
        """Install a single package"""
        pkg = self.db.get_package(name)
        if not pkg:
            print(f"  {RED}Package not found in database{RESET}")
            return False
        
        try:
            # Download
            url = f"http://archive.ubuntu.com/ubuntu/{pkg.filename}"
            deb_path = DOWNLOAD_DIR / os.path.basename(pkg.filename)
            
            print(f"  {BLUE}Downloading{RESET} {name}...")
            
            start_time = time.time()
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            if HAVE_TQDM and total_size > 0:
                with open(deb_path, 'wb') as f:
                    with tqdm(total=total_size, unit='B', unit_scale=True, desc=f"    {name}") as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                            pbar.update(len(chunk))
            else:
                with open(deb_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
            
            download_time = time.time() - start_time
            print(f"  {GREEN}Downloaded in {download_time:.2f}s{RESET}")
            
            # Install
            print(f"  {BLUE}Installing{RESET} {name}...")
            install_start = time.time()
            
            result = subprocess.run(
                ['sudo', 'dpkg', '-i', str(deb_path)],
                capture_output=True,
                text=True
            )
            
            install_time = time.time() - install_start
            
            if result.returncode == 0:
                print(f"  {GREEN}✓ Installed successfully in {install_time:.2f}s{RESET}")
                self.installed = SystemPackageManager.get_installed_packages()
                
                # Clean up
                if deb_path.exists():
                    os.remove(deb_path)
                
                return True
            else:
                print(f"  {RED}✗ Installation failed{RESET}")
                if result.stderr:
                    for line in result.stderr.split('\n')[:3]:
                        if line.strip():
                            print(f"  {YELLOW}{line.strip()}{RESET}")
                
                if deb_path.exists():
                    os.remove(deb_path)
                
                return False
                
        except Exception as e:
            print(f"  {RED}Error: {e}{RESET}")
            return False


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='PackHub Standalone CLI - No Backend Required',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s update                    # Update package database
  %(prog)s search gcc                # Search for packages
  %(prog)s info nmap                 # Show package details
  %(prog)s install nmap              # Install package with dependencies
        """
    )
    
    parser.add_argument('command', choices=['update', 'search', 'info', 'install'],
                       help='Command to execute')
    parser.add_argument('package', nargs='?', help='Package name')
    parser.add_argument('--force', action='store_true', help='Force database update')
    
    args = parser.parse_args()
    
    if len(sys.argv) == 1:
        parser.print_help()
        return
    
    # Initialize database
    db = PackageDatabase()
    
    try:
        if args.command == 'update':
            db.update(force=args.force)
        
        else:
            # Load database
            if not db.load_from_cache():
                print(f"{YELLOW}Package database not found. Running update...{RESET}")
                db.update()
            
            installer = PackageInstaller(db)
            
            if args.command == 'search':
                if not args.package:
                    print(f"{RED}Error: Package name required{RESET}")
                    return
                installer.search(args.package)
            
            elif args.command == 'info':
                if not args.package:
                    print(f"{RED}Error: Package name required{RESET}")
                    return
                installer.info(args.package)
            
            elif args.command == 'install':
                if not args.package:
                    print(f"{RED}Error: Package name required{RESET}")
                    return
                installer.install(args.package)
    
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}Cancelled{RESET}")
    except Exception as e:
        print(f"{RED}Error: {e}{RESET}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
