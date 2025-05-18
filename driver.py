# win9x_driver_installer_with_manifest.py
# Python 2.5.4 on Win9x. Requires ctypes (bundled) and urlmon.dll (IE)
import ctypes, os, sys

# --- CONFIGURATION ---
# Raw URL to your manifest on GitHub (must point to the plain .txt)
MANIFEST_URL = "https://raw.githubusercontent.com/username/driver-repo/master/driver_manifest.txt"
# Base URL for individual INFs (same as before)
BASE_URL     = "http://your.repo.example.com/drivers/"

# Constants from cfgmgr32.h
CM_LOCATE_DEVNODE_NORMAL = 0x00000000
CM_DRP_HARDWAREID        = 0x00000001
CR_SUCCESS               = 0x00000000

# Load DLLs
cfgmgr = ctypes.windll.cfgmgr32
urlmon = ctypes.windll.urlmon

def download_manifest():
    """Download the manifest TXT from GitHub and return a list of HWIDs."""
    local = os.path.join(os.environ.get('WINDIR','C:\\Windows'),
                         'Inf', 'driver_manifest.txt')
    hr = urlmon.URLDownloadToFileA(None,
                                  ctypes.c_char_p(MANIFEST_URL),
                                  ctypes.c_char_p(local),
                                  0, None)
    if hr != 0:
        print >> sys.stderr, "ERROR: Failed to download manifest:", MANIFEST_URL
        return None

    hwlist = []
    for line in file(local):
        l = line.strip()
        if l:
            hwlist.append(l)
    return hwlist

def enum_hwids():
    """Walk the PnP tree and return a deduped list of all HWIDs."""
    ids = []
    devroot = ctypes.c_uint()
    if cfgmgr.CM_Locate_DevNodeA(ctypes.byref(devroot),
                                 None,
                                 CM_LOCATE_DEVNODE_NORMAL) != CR_SUCCESS:
        print >> sys.stderr, "ERROR: Could not locate root devnode."
        return ids

    def walk(dn):
        # get required buffer size
        needed = ctypes.c_ulong(0)
        cfgmgr.CM_Get_DevNode_Registry_PropertyA(dn,
                                                 CM_DRP_HARDWAREID,
                                                 None, None,
                                                 ctypes.byref(needed), 0)
        if needed.value:
            buf = ctypes.create_string_buffer(needed.value)
            if cfgmgr.CM_Get_DevNode_Registry_PropertyA(dn,
                                                       CM_DRP_HARDWAREID,
                                                       None,
                                                       buf,
                                                       ctypes.byref(needed), 0) == CR_SUCCESS:
                raw = buf.raw[:needed.value]
                for part in raw.split('\0'):
                    if part:
                        ids.append(part)
        # children
        child = ctypes.c_uint()
        if cfgmgr.CM_Get_Child(ctypes.byref(child), dn, 0) == CR_SUCCESS:
            walk(child)
        # siblings
        sib = ctypes.c_uint()
        if cfgmgr.CM_Get_Sibling(ctypes.byref(sib), dn, 0) == CR_SUCCESS:
            walk(sib)

    walk(devroot)
    return list(set(ids))

def download_inf(hwid):
    """Download the INF for a given HWID via URLDownloadToFileA."""
    fname = hwid + ".inf"
    local = os.path.join(os.environ.get('WINDIR','C:\\Windows'),
                         'Inf', fname)
    url   = BASE_URL + hwid + ".inf"
    hr = urlmon.URLDownloadToFileA(None,
                                  ctypes.c_char_p(url),
                                  ctypes.c_char_p(local),
                                  0, None)
    if hr != 0:
        return None
    return local

def install_inf(path):
    """Invoke rundll32 to install the INF."""
    cmd = 'rundll32.exe setupapi,InstallHinfSection DefaultInstall 132 "%s"' % path
    return os.system(cmd) == 0

def main():
    print "=== Win9x Driver Installer (with GitHub manifest) ===\n"

    manifest = download_manifest()
    if manifest is None:
        print "Aborting."
        return 1

    print "Supported HWIDs loaded:", len(manifest), "\n"
    hwids = enum_hwids()
    if not hwids:
        print "No devices found or enumeration failed."
        return 1

    for hw in hwids:
        print "Device found:", hw
        if hw not in manifest:
            print "  -> Not in manifest; skipping.\n"
            continue

        inf = download_inf(hw)
        if not inf:
            print "  -> Failed to download INF; skipping.\n"
            continue
        print "  -> INF saved to", inf

        if install_inf(inf):
            print "  + Driver installed successfully.\n"
        else:
            print "  ! Installation failed.\n"

    print "All done. Please reboot to complete driver setup."
    return 0

if __name__ == '__main__':
    sys.exit(main())
