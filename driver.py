# win9x_driver_installer_driverscollection.py
# Requires Python 2.5.4 with ctypes (bundled), urlmon.dll (IE), and a CAB extractor (e.g. extract.exe) in PATH.

import ctypes, os, sys, re, zipfile

# --- Configuration ---
# Search URL template (we’ll append ?H=<HWID>)
SEARCH_URL_BASE = "https://driverscollection.com/?H="
# You may optionally add "&By=VendorName" if you parse vendor separately.

# Where to save temp HTML and downloaded archives/INFs
WINDIR = os.environ.get('WINDIR', r'C:\Windows')
INF_DIR = os.path.join(WINDIR, 'Inf')
TMP_SEARCH_HTML = os.path.join(INF_DIR, 'search.html')
TMP_PAGE_HTML   = os.path.join(INF_DIR, 'driverpage.html')

# --- Win9x API constants ---
CM_LOCATE_DEVNODE_NORMAL = 0x00000000
CM_DRP_HARDWAREID        = 0x00000001
CR_SUCCESS               = 0x00000000

# Load DLLs
cfgmgr = ctypes.windll.cfgmgr32
urlmon = ctypes.windll.urlmon

def fetch_url_to_file(url, local_path):
    """Download a URL to a file using URLDownloadToFileA."""
    # URLDownloadToFileA(NULL, url, local_path, 0, NULL)
    hr = urlmon.URLDownloadToFileA(
        None,
        ctypes.c_char_p(url),
        ctypes.c_char_p(local_path),
        0,
        None
    )
    return hr == 0

def enum_hwids():
    """Return a deduped list of all hardware IDs on the system."""
    ids = []
    root = ctypes.c_uint()
    if cfgmgr.CM_Locate_DevNodeA(ctypes.byref(root), None, CM_LOCATE_DEVNODE_NORMAL) != CR_SUCCESS:
        print >> sys.stderr, "ERROR: Could not locate root devnode."
        return ids

    def walk(node):
        # First query buffer size
        needed = ctypes.c_ulong(0)
        cfgmgr.CM_Get_DevNode_Registry_PropertyA(
            node, CM_DRP_HARDWAREID,
            None, None,
            ctypes.byref(needed), 0
        )
        if needed.value:
            buf = ctypes.create_string_buffer(needed.value)
            if cfgmgr.CM_Get_DevNode_Registry_PropertyA(
                node, CM_DRP_HARDWAREID,
                None, buf,
                ctypes.byref(needed), 0
            ) == CR_SUCCESS:
                raw = buf.raw[:needed.value]
                for part in raw.split('\0'):
                    if part:
                        ids.append(part)
        # Recurse into child
        child = ctypes.c_uint()
        if cfgmgr.CM_Get_Child(ctypes.byref(child), node, 0) == CR_SUCCESS:
            walk(child)
        # Recurse into sibling
        sib = ctypes.c_uint()
        if cfgmgr.CM_Get_Sibling(ctypes.byref(sib), node, 0) == CR_SUCCESS:
            walk(sib)

    walk(root)
    # Deduplicate
    return list(set(ids))

def find_driver_page(hwid):
    """Search DriversCollection.com for hwid, return the URL of the driver page or None."""
    # URL‑encode spaces and special chars minimally:
    query = hwid.replace(' ', '+')
    search_url = SEARCH_URL_BASE + query
    if not fetch_url_to_file(search_url, TMP_SEARCH_HTML):
        return None

    html = open(TMP_SEARCH_HTML, 'r').read()
    m = re.search(r'href="(/\\?file_cid=[^"]+)"', html)
    if not m:
        return None
    return "https://driverscollection.com" + m.group(1)

def get_direct_download_url(page_url):
    """Fetch the driver page and extract the real download URL from a JS redirect."""
    if not fetch_url_to_file(page_url, TMP_PAGE_HTML):
        return None

    html = open(TMP_PAGE_HTML, 'r').read()
    # look for: location.href = "http://.../driver123.zip"
    m = re.search(r'location\.href\s*=\s*"([^"]+)"', html)
    return m.group(1) if m else None

def download_and_install(hwid):
    """Search, download archive, extract .INF, and install; returns True on success."""
    print "  → Searching DriversCollection for", hwid
    page = find_driver_page(hwid)
    if not page:
        print "    [!] No entry found; skipping."
        return False

    print "    Found driver page:", page
    dl = get_direct_download_url(page)
    if not dl:
        print "    [!] Could not parse direct download URL; skipping."
        return False

    print "    Direct download URL:", dl
    archive_name = os.path.basename(dl)
    archive_path = os.path.join(INF_DIR, archive_name)
    if not fetch_url_to_file(dl, archive_path):
        print "    [!] Failed to download archive; skipping."
        return False

    print "    Downloaded archive to:", archive_path

    # Extract .INF
    inf_path = None
    if archive_path.lower().endswith('.zip'):
        try:
            z = zipfile.ZipFile(archive_path)
            for member in z.namelist():
                if member.lower().endswith('.inf'):
                    print "    Extracting INF:", member
                    z.extract(member, INF_DIR)
                    inf_path = os.path.join(INF_DIR, member)
                    break
            z.close()
        except Exception, e:
            print "    [!] ZIP extraction error:", e
            return False
    else:
        # Assume CAB: requires extract.exe (or EXPAND) in PATH
        print "    Extracting CAB using extract.exe"
        cmd = 'extract.exe "%s" "%s"' % (archive_path, INF_DIR)
        if os.system(cmd) != 0:
            print "    [!] CAB extraction failed."
            return False
        # Assume INF named <hwid>.inf
        inf_path = os.path.join(INF_DIR, hwid + '.inf')

    if not inf_path or not os.path.exists(inf_path):
        print "    [!] INF not found after extraction."
        return False

    print "    Installing INF:", inf_path
    # DIF_DEFINSTALL = 132
    cmd = 'rundll32.exe setupapi,InstallHinfSection DefaultInstall 132 "%s"' % inf_path
    if os.system(cmd) != 0:
        print "    [!] Installation failed."
        return False

    print "    [+] Driver installed successfully!"
    return True

def main():
    print "=== Win9x Driver Installer via DriversCollection ==="
    hwids = enum_hwids()
    if not hwids:
        print "No PnP devices found or enumeration failed."
        return 1

    for hw in hwids:
        print "\nDevice:", hw
        download_and_install(hw)

    print "\nAll done. Please reboot to complete driver setup."
    return 0

if __name__ == '__main__':
    sys.exit(main())
